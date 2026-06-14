# Project Architecture

Maven is organized as a three-phase multimodal data pipeline. The source tree is
split by ownership: shared infrastructure in `data_pipeline/common/`, video
processing in `data_pipeline/videos/`, book processing in `data_pipeline/books/`,
and Colab orchestration in `data_pipeline/colab/`.

## Source Layout

```text
data_pipeline/
  common/
    artifacts.py        # local artifact paths, idempotency checks, safe stems
    json_utils.py       # atomic JSON writes and noisy LLM JSON extraction
    logging_config.py   # process-wide logging configuration
    retry.py            # explicit retry/backoff behavior
    llm_client.py       # OpenAI JSON-mode adapter
    text_mapping.py     # character-to-time and character-to-page resolution
    text_splitter.py    # LangChain splitter wrapper with start indices
    dynamo.py           # DynamoDB Decimal serialization helpers
  videos/
    main.py             # phase 1 CLI: transcript ingestion
    transcript_manager.py
    video_enricher.py   # phase 2 CLI: LLM metadata and timestamp resolution
    transcript_processor.py
    dynamo_uploader.py
    sync_from_dynamo.py
    output/
    enriched_metadata/
    processed_chunks/
  books/
    books_main.py       # full book pipeline runner
    book_processor.py   # phase 1 CLI: PDF page extraction
    book_enricher.py    # phase 2 CLI: smart-sampled LLM metadata
    book_chunk_processor.py
    dynamo_uploader.py
    extract_thumbnails.py
    input_books/
    books_output/
    books_enriched_metadata/
    processed_books_chunks/
```

The legacy root modules `data_pipeline/llm_client.py`, `splitters.py`,
`text_mapping.py`, and `dynamo.py` are compatibility shims. New code should use
`data_pipeline.common.*` directly.

## Pipeline Flow

Video flow:

```text
YouTube URL
  -> videos/main.py
  -> videos/output/<video_id>.json
  -> videos/video_enricher.py
  -> videos/enriched_metadata/<video_id>_meta.json
  -> videos/transcript_processor.py
  -> videos/processed_chunks/<video_id>_chunks.json
```

Book flow:

```text
books/input_books/<book>.pdf
  -> books/book_processor.py
  -> books/books_output/<book_name>.json
  -> books/book_enricher.py
  -> books/books_enriched_metadata/<book_name>_meta.json
  -> books/book_chunk_processor.py
  -> books/processed_books_chunks/<book_name>_chunks.json
```

Downstream uploaders consume stable local JSON artifacts. DynamoDB metadata
upload is separated from extraction/enrichment/chunking. Qdrant embedding and
upload are orchestrated from the Colab notebook after local artifact validation.

## Shared Contracts

Every file-producing phase is idempotent: if the expected output exists, the
phase logs a skip and leaves the file untouched.

Video timestamps are resolved only through `common.text_mapping`. LLM output
provides exact transcript anchor text; code maps those anchors to character
offsets and interpolates timestamps from transcript fragments.

Book chunks are page-mapped through the same character-offset approach. Page
starts are recorded while concatenating extracted page text, then binary search
maps chunk offsets back to source pages.

LLM responses are parsed with `common.json_utils.extract_json_object`, which
extracts the first complete JSON object from clean JSON, fenced JSON, or noisy
responses before calling `json.loads`.

## Runtime Boundaries

Local CPU phases generate JSON artifacts and do not require Qdrant or DynamoDB.
LLM enrichment requires `OPENAI_API_KEY`. GPU-heavy embedding work is isolated in
`data_pipeline/colab/codex_project.ipynb`.

Generated artifacts, uploaded PDFs, thumbnails, and environment files are kept
out of git. Empty artifact directories are retained with `.gitkeep` files so the
expected project structure is visible after checkout.
