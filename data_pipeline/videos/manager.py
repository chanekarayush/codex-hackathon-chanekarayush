"""Phase 1: fetch and persist YouTube transcripts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse

from data_pipeline.common import (
    call_with_backoff,
    get_logger,
    normalize_whitespace,
    save_json_atomic,
    skip_if_exists,
)


LOGGER = get_logger(__name__)


class TranscriptIngestionBlocked(RuntimeError):
    """Raised when YouTube blocks transcript requests for the current IP/session."""


def is_youtube_block_error(error: BaseException) -> bool:
    """Best-effort detection for youtube-transcript-api request/IP blocks."""

    error_type = type(error).__name__.lower()
    message = str(error).lower()
    needles = (
        "requestblocked",
        "ipblocked",
        "request blocked",
        "ip blocked",
        "ip has been blocked",
        "blocking requests from your ip",
        "cloud provider",
        "too many requests",
        "working around ip bans",
    )
    return any(needle in error_type or needle in message for needle in needles)


class TranscriptManager:
    """Fetch transcripts from YouTube and normalize them for downstream stages."""

    DEFAULT_LANGUAGES = ("en", "en-US", "en-GB")

    @staticmethod
    def parse_video_id(url_or_id: str) -> str:
        value = url_or_id.strip()
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
            return value

        parsed = urlparse(value)
        host = parsed.netloc.lower()

        if host.endswith("youtu.be"):
            candidate = parsed.path.strip("/").split("/")[0]
            if re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
                return candidate

        query_video_id = parse_qs(parsed.query).get("v", [None])[0]
        if query_video_id and re.fullmatch(r"[A-Za-z0-9_-]{11}", query_video_id):
            return query_video_id

        path_parts = [part for part in parsed.path.split("/") if part]
        for marker in ("embed", "shorts", "live", "v"):
            if marker in path_parts:
                marker_index = path_parts.index(marker)
                if marker_index + 1 < len(path_parts):
                    candidate = path_parts[marker_index + 1]
                    if re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
                        return candidate

        raise ValueError(f"Could not parse a YouTube video id from: {url_or_id}")

    def fetch_transcript(
        self,
        video_id: str,
        *,
        languages: Iterable[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch transcript snippets and normalize to text/start_time/duration."""

        from youtube_transcript_api import YouTubeTranscriptApi

        preferred_languages = list(languages or self.DEFAULT_LANGUAGES)

        def _fetch() -> Any:
            try:
                api = YouTubeTranscriptApi()
                return api.fetch(video_id, languages=preferred_languages)
            except AttributeError:
                try:
                    return YouTubeTranscriptApi.get_transcript(video_id, languages=preferred_languages)
                except Exception as exc:
                    if is_youtube_block_error(exc):
                        raise TranscriptIngestionBlocked(
                            f"YouTube blocked transcript requests while fetching {video_id}."
                        ) from exc
                    raise
            except Exception as exc:
                if is_youtube_block_error(exc):
                    raise TranscriptIngestionBlocked(
                        f"YouTube blocked transcript requests while fetching {video_id}."
                    ) from exc
                raise

        fetched = call_with_backoff(_fetch, logger=LOGGER)
        return self._normalize_transcript(fetched)

    def save_transcript(
        self,
        url_or_id: str,
        *,
        output_dir: str | Path,
        languages: Iterable[str] | None = None,
    ) -> Path | None:
        """Fetch one transcript unless the idempotent output already exists."""

        video_id = self.parse_video_id(url_or_id)
        output_path = Path(output_dir) / f"{video_id}.json"
        if skip_if_exists(output_path, LOGGER):
            return output_path

        fragments = self.fetch_transcript(video_id, languages=languages)
        if not fragments:
            LOGGER.warning("Transcript is empty for video %s; skipping.", video_id)
            return None

        save_json_atomic(output_path, fragments)
        LOGGER.info("Saved %s transcript fragments to %s", len(fragments), output_path)
        return output_path

    @staticmethod
    def _normalize_transcript(fetched: Any) -> list[dict[str, Any]]:
        if hasattr(fetched, "to_raw_data"):
            raw_items = fetched.to_raw_data()
        else:
            raw_items = list(fetched)

        fragments: list[dict[str, Any]] = []
        for item in raw_items:
            if isinstance(item, dict):
                text = item.get("text")
                start = item.get("start_time", item.get("start", 0.0))
                duration = item.get("duration", 0.0)
            else:
                text = getattr(item, "text", "")
                start = getattr(item, "start", getattr(item, "start_time", 0.0))
                duration = getattr(item, "duration", 0.0)

            cleaned_text = normalize_whitespace(str(text or ""))
            if not cleaned_text:
                continue

            fragments.append(
                {
                    "text": cleaned_text,
                    "start_time": float(start or 0.0),
                    "duration": float(duration or 0.0),
                }
            )

        return fragments
