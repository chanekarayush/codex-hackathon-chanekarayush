"""Hybrid Qdrant search Lambda for codex_project."""

from __future__ import annotations

import json
import logging
import math
import os
import re
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

import boto3
from qdrant_client import QdrantClient, models

from common import decimal_to_native, error_response, options_response, response


logger = logging.getLogger()
logger.setLevel(logging.INFO)

TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9]+(?:'[a-zA-Z0-9]+)?", flags=re.UNICODE)
STOPWORDS_PATH = Path(__file__).with_name("english_stopwords.json")
VOCAB_PATH = Path(__file__).with_name("vocab_idf.json")


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


STOPWORDS = set(_load_json(STOPWORDS_PATH, []))
BM25 = _load_json(VOCAB_PATH, {"vocab": {}, "idf": {}, "avgdl": 1.0, "k1": 1.5, "b": 0.75})


def _query_param(event: dict[str, Any], name: str, default: str = "") -> str:
    params = event.get("queryStringParameters") or {}
    return str(params.get(name) or default).strip()


def _tokenize(text: str, *, remove_stopwords: bool = True) -> list[str]:
    tokens = [token.lower() for token in TOKEN_PATTERN.findall(text or "")]
    if remove_stopwords:
        tokens = [token for token in tokens if token not in STOPWORDS]
    return tokens


def _should_skip_sparse(raw_query: str) -> bool:
    content_words = _tokenize(raw_query, remove_stopwords=True)
    if not content_words:
        return True
    return len(content_words) > 12


def _build_sparse_query(query: str) -> models.SparseVector | None:
    vocab = BM25.get("vocab") or {}
    idf = BM25.get("idf") or {}
    if not vocab or not idf:
        return None

    tokens = _tokenize(query)
    counts = Counter(token for token in tokens if token in vocab)
    if not counts:
        return None

    avgdl = float(BM25.get("avgdl") or 1.0)
    k1 = float(BM25.get("k1") or 1.5)
    b = float(BM25.get("b") or 0.75)
    doc_len = len(tokens) or 1

    indices: list[int] = []
    values: list[float] = []
    for token, tf in counts.items():
        denominator = tf + k1 * (1 - b + b * (doc_len / max(avgdl, 1e-9)))
        score = float(idf.get(token, 0.0)) * ((tf * (k1 + 1)) / denominator)
        if score > 0:
            indices.append(int(vocab[token]))
            values.append(score)

    if not indices:
        return None
    return models.SparseVector(indices=indices, values=values)


def _extract_embedding(payload: Any) -> list[float]:
    if isinstance(payload, dict):
        if "embedding" in payload:
            return _extract_embedding(payload["embedding"])
        if "error" in payload:
            raise RuntimeError(f"Hugging Face embedding error: {payload['error']}")

    if not isinstance(payload, list) or not payload:
        raise RuntimeError("Unexpected embedding response from Hugging Face.")

    if all(isinstance(value, (int, float)) for value in payload):
        return [float(value) for value in payload]

    if len(payload) == 1 and isinstance(payload[0], list):
        return _extract_embedding(payload[0])

    if all(isinstance(row, list) for row in payload):
        rows = [[float(value) for value in row] for row in payload if row]
        if not rows:
            raise RuntimeError("Embedding response had no numeric rows.")
        dimensions = len(rows[0])
        return [sum(row[index] for row in rows) / len(rows) for index in range(dimensions)]

    raise RuntimeError("Unexpected embedding response shape from Hugging Face.")


def _hf_max_attempts() -> int:
    try:
        return max(1, min(int(os.environ.get("HF_MAX_ATTEMPTS", "2")), 4))
    except ValueError:
        return 2


def _hf_timeout_seconds() -> float:
    try:
        return max(3.0, min(float(os.environ.get("HF_TIMEOUT_SECONDS", "8")), 20.0))
    except ValueError:
        return 8.0


def _hf_backoff(attempt: int) -> float:
    return min(0.75 * (2**attempt), 6.0)


def _read_hf_embedding_payload(query: str, model_name: str, hf_api_key: str) -> Any:
    url = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{model_name}"
    request = urllib.request.Request(
        url,
        data=json.dumps({"inputs": query, "options": {"wait_for_model": True}}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {hf_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=_hf_timeout_seconds()) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _dense_embedding(query: str) -> list[float]:
    hf_api_key = os.environ.get("HF_API_KEY")
    if not hf_api_key:
        raise RuntimeError("HF_API_KEY is required for dense query embeddings.")

    model_name = os.environ.get("HF_EMBEDDING_MODEL", "BAAI/bge-m3")
    payload: Any = None
    last_error: Exception | None = None
    retryable_http_statuses = {408, 409, 425, 429, 500, 502, 503, 504}

    for attempt in range(_hf_max_attempts()):
        try:
            payload = _read_hf_embedding_payload(query, model_name, hf_api_key)
            last_error = None
            break
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore")
            last_error = RuntimeError(f"Hugging Face embedding request failed: {exc.code} {details}")
            if exc.code not in retryable_http_statuses or attempt >= _hf_max_attempts() - 1:
                raise last_error from exc
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            last_error = RuntimeError(f"Hugging Face embedding request failed: {exc}")
            if attempt >= _hf_max_attempts() - 1:
                raise last_error from exc

        time.sleep(_hf_backoff(attempt))

    if last_error:
        raise last_error
    if payload is None:
        raise RuntimeError("Hugging Face embedding request returned no payload.")

    vector = _extract_embedding(payload)
    norm = math.sqrt(sum(value * value for value in vector))
    if norm > 0:
        vector = [value / norm for value in vector]
    return vector


def _point_to_hit(point: Any) -> dict[str, Any]:
    return {
        "id": str(point.id),
        "score": float(point.score or 0.0),
        "payload": point.payload or {},
    }


def _video_ids_from_hits(hits: list[dict[str, Any]]) -> list[str]:
    video_ids: list[str] = []
    for hit in hits:
        payload = hit.get("payload") or {}
        video_id = payload.get("video_id")
        if video_id and video_id not in video_ids:
            video_ids.append(str(video_id))
    return video_ids


def _load_video_metadata(video_ids: list[str]) -> dict[str, dict[str, Any]]:
    table_name = os.environ.get("DYNAMODB_TABLE")
    if not table_name or not video_ids:
        return {}

    table = boto3.resource("dynamodb").Table(table_name)
    lookup: dict[str, dict[str, Any]] = {}
    for video_id in video_ids[:25]:
        try:
            item = table.get_item(Key={"video_id": video_id}).get("Item")
        except Exception:
            logger.exception("Failed to load metadata for video_id=%s", video_id)
            continue
        if item:
            lookup[video_id] = decimal_to_native(item)
    return lookup


def _enrich_hits(hits: list[dict[str, Any]], metadata_lookup: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for hit in hits:
        payload = dict(hit.get("payload") or {})
        video_id = str(payload.get("video_id") or "")
        metadata = metadata_lookup.get(video_id) or {}
        for key in ("title", "summary", "topics", "target_audience", "difficulty_level", "queries"):
            if metadata.get(key) is not None and payload.get(key) in (None, "", []):
                payload[key] = metadata[key]
        enriched.append({**hit, "payload": payload})
    return enriched


def _fallback_related_queries(raw_query: str) -> list[str]:
    tokens = _tokenize(raw_query)
    if "discipline" in tokens or "consistent" in tokens:
        return [
            "How do I stay consistent with workouts?",
            "How can I build discipline when motivation drops?",
            "What routine helps beginners keep training?",
        ]
    if "fat" in tokens or "weight" in tokens:
        return [
            "What helps beginners lose fat safely?",
            "How should I combine diet and training?",
            "How do I avoid quitting during fat loss?",
        ]
    return [
        "How can I build mental toughness?",
        "How do I stop quitting when training gets hard?",
        "How should I recover after a bad week?",
    ]


def _related_queries(raw_query: str, metadata_lookup: dict[str, dict[str, Any]]) -> list[str]:
    raw_normalized = raw_query.strip().lower()
    query_tokens = set(_tokenize(raw_query))
    suggestions: list[str] = []

    for metadata in metadata_lookup.values():
        for query in metadata.get("queries") or []:
            query_text = str(query or "").strip()
            if not query_text or query_text.lower() == raw_normalized or query_text in suggestions:
                continue
            suggestion_tokens = set(_tokenize(query_text))
            if not query_tokens or query_tokens.intersection(suggestion_tokens):
                suggestions.append(query_text)
            if len(suggestions) >= 6:
                return suggestions

    for query in _fallback_related_queries(raw_query):
        if query.lower() != raw_normalized and query not in suggestions:
            suggestions.append(query)
        if len(suggestions) >= 6:
            break
    return suggestions


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    if event.get("httpMethod") == "OPTIONS":
        return options_response()

    try:
        query = _query_param(event, "q") or _query_param(event, "query")
        if not query:
            return error_response("Missing required query parameter: q", 400)

        limit = min(max(int(_query_param(event, "limit", "10")), 1), 50)
        qdrant_url = os.environ["QDRANT_URL"]
        qdrant_api_key = os.environ.get("QDRANT_API_KEY")
        collection_name = os.environ.get("COLLECTION_NAME", "codex_project-videos")

        client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key, timeout=20)
        sparse_vector = None if _should_skip_sparse(query) else _build_sparse_query(query)
        dense_vector: list[float] | None = None
        dense_error: str | None = None

        try:
            dense_vector = _dense_embedding(query)
        except Exception as exc:
            dense_error = str(exc)
            logger.warning("Dense embedding failed; sparse fallback available=%s", bool(sparse_vector), exc_info=True)

        if dense_vector is None and sparse_vector is None:
            return error_response(
                "Search embedding failed and no sparse fallback was available. "
                "Try a shorter keyword-style query or check HF_API_KEY/Hugging Face availability.",
                503,
            )

        if dense_vector and sparse_vector:
            threshold = 0.01
            result = client.query_points(
                collection_name=collection_name,
                prefetch=[
                    models.Prefetch(query=dense_vector, using="dense", limit=limit * 3),
                    models.Prefetch(query=sparse_vector, using="sparse", limit=limit * 3),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=limit,
                score_threshold=threshold,
            )
            mode = "hybrid_rrf"
        elif sparse_vector:
            threshold = 0.01
            result = client.query_points(
                collection_name=collection_name,
                query=sparse_vector,
                using="sparse",
                limit=limit,
                score_threshold=threshold,
            )
            mode = "sparse"
        else:
            threshold = 0.46
            result = client.query_points(
                collection_name=collection_name,
                query=dense_vector,
                using="dense",
                limit=limit,
                score_threshold=threshold,
            )
            mode = "dense"

        hits = [_point_to_hit(point) for point in result.points]
        hits = [hit for hit in hits if hit["score"] >= threshold]
        metadata_lookup = _load_video_metadata(_video_ids_from_hits(hits))
        hits = _enrich_hits(hits, metadata_lookup)
        return response(
            200,
            {
                "query": query,
                "mode": mode,
                "threshold": threshold,
                "count": len(hits),
                "results": hits,
                "related_queries": _related_queries(query, metadata_lookup),
                "warning": f"Dense embedding failed; used sparse search. {dense_error}" if mode == "sparse" and dense_error else None,
            },
        )
    except Exception as exc:
        logger.exception("Search failed")
        return error_response(str(exc))
