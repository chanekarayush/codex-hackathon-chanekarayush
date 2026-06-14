# Maven Multimodal Spiritual Search Pipeline

## Summary

Maven is a multimodal search data pipeline for processing YouTube videos and PDF books into semantically searchable records. The pipeline extracts raw content, enriches it with structured LLM metadata, and chunks it for indexing into a vector database such as Qdrant and a NoSQL store such as DynamoDB.

The implementation must preserve exact source anchors. For videos, the critical requirement is zero-drift timestamp mapping: every LLM-extracted story, musical segment, and semantic chunk must resolve back to the correct source timestamp using transcript character offsets and interpolation.

## Target Architecture

```text
data_pipeline/
  common/
    json_utils.py
    retry.py
    llm_client.py
    text_splitter.py
    logging_config.py
  videos/
    main.py
    transcript_manager.py
    video_enricher.py
    transcript_processor.py
    output/
    enriched_metadata/
    processed_chunks/
  books/
    books_main.py
    book_processor.py
    book_enricher.py
    book_chunk_processor.py
    input_books/
    books_output/
    books_enriched_metadata/
    books_processed_chunks/
```

Each domain has three phases:

1. Raw extraction.
2. LLM enrichment.
3. Semantic chunking.

Every phase must be idempotent. Before doing network calls, LLM calls, PDF extraction, or chunk processing, the script checks whether its expected output file already exists. If it exists, the script logs a skip message and returns without modifying it.

## Shared Implementation Requirements

### Configuration

Use environment variables for runtime configuration:

```text
LLM_PROVIDER=openai
OPENAI_API_KEY=...
QDRANT_URL=...
QDRANT_API_KEY=...
DYNAMODB_TABLE_METADATA=...
DYNAMODB_TABLE_CHUNKS=...
```

The initial code should generate JSON artifacts locally. Qdrant and DynamoDB indexing can be implemented as a downstream step after extraction, enrichment, and chunk validation are stable.

### Robust JSON Parsing

LLM output must not be parsed with a direct `json.loads(raw_response)`.

Implement a brace-counting parser:

1. Find the first `{`.
2. Scan forward character by character.
3. Track nested `{` and `}` depth.
4. Respect quoted strings and escaped characters so braces inside strings do not affect depth.
5. When depth returns to zero, slice that exact substring.
6. Call `json.loads()` on the extracted JSON object.

This parser should handle clean JSON, Markdown-fenced JSON, and LLM responses with extra leading or trailing prose.

### Retry And Rate Limit Handling

Wrap transcript fetching and LLM calls with retry logic:

1. Catch HTTP 429, quota exceeded errors, transient connection failures, and timeout errors.
2. Retry with exponential backoff, for example `2s`, `4s`, `8s`, `16s`, capped at a reasonable maximum.
3. Add jitter to avoid synchronized retries.
4. Log each retry attempt.
5. After max retries, log the failure and skip the item without crashing the full batch.

### Empty Input Handling

If a transcript, PDF, page, or concatenated text is empty:

1. Log a warning with the source identifier.
2. Do not call the LLM.
3. Do not create misleading enriched metadata or chunk files.
4. Continue processing the rest of the batch.

## Video Pipeline

### Phase 1: Transcript Ingestion

Files:

```text
data_pipeline/videos/main.py
data_pipeline/videos/transcript_manager.py
```

Input:

```text
List of standard YouTube URLs
```

Processing:

1. Parse the YouTube video ID from each URL.
2. Check for `data_pipeline/videos/output/<video_id>.json`.
3. If the file exists, skip the video.
4. Fetch transcript fragments through the YouTube transcript API.
5. Normalize each fragment into a stable schema.
6. Skip gracefully if no transcript is available.

Output:

```json
[
  {
    "text": "fragment text",
    "start_time": 12.5,
    "duration": 3.0
  }
]
```

Write to:

```text
data_pipeline/videos/output/<video_id>.json
```

### Phase 2: LLM Metadata Enrichment

File:

```text
data_pipeline/videos/video_enricher.py
```

Processing:

1. Load `output/<video_id>.json`.
2. Check for `enriched_metadata/<video_id>_meta.json`.
3. Concatenate all transcript fragments into one full transcript string.
4. Build a `char_to_time_map` during concatenation.
5. Send the full transcript to the LLM with a strict zero-shot system prompt in Marathi or the target language.
6. Request a JSON-only response using the OpenAI API response format.
7. Parse the response with the shared brace-counting JSON parser.
8. Resolve timestamps for stories and musical segments from exact transcript text.

Target metadata:

```json
{
  "video_id": "youtube_id",
  "topics": [],
  "questions": [],
  "actionable_practices": [],
  "quoted_verses": [],
  "stories": [
    {
      "title": "Story title",
      "summary": "Story summary",
      "exact_start_text": "first 7-10 transcript words",
      "exact_end_text": "last 7-10 transcript words",
      "start_time": 0.0,
      "end_time": 0.0
    }
  ],
  "musical_segments": [
    {
      "title": "Segment title",
      "description": "Segment description",
      "exact_start_text": "first 7-10 transcript words",
      "exact_end_text": "last 7-10 transcript words",
      "start_time": 0.0,
      "end_time": 0.0
    }
  ]
}
```

Write to:

```text
data_pipeline/videos/enriched_metadata/<video_id>_meta.json
```

### Zero-Drift Timestamp Resolution

When concatenating transcript fragments, build a character map:

```python
char_to_time_map = [
    {
        "char_start": current_char_length,
        "start_time": fragment["start_time"],
        "duration": fragment["duration"],
        "text_len": len(fragment["text"])
    }
]
```

Resolution algorithm:

1. Search for `exact_start_text` or `exact_end_text` in the full transcript using `str.find()`.
2. If direct search fails, use a regex fallback that tolerates punctuation and whitespace differences.
3. Once the absolute character index is found, use `bisect` against `char_start` values to find the owning fragment.
4. Compute `chars_into_fragment = absolute_index - fragment.char_start`.
5. Interpolate timestamp:

```python
resolved_time = fragment.start_time + (
    fragment.duration * (chars_into_fragment / fragment.text_len)
)
```

The same resolver must be used for LLM-extracted stories, musical segments, and semantic chunks.

### Phase 3: Transcript Semantic Chunking

File:

```text
data_pipeline/videos/transcript_processor.py
```

Processing:

1. Load `output/<video_id>.json`.
2. Check for `processed_chunks/<video_id>_chunks.json`.
3. Rebuild the exact same full transcript string and `char_to_time_map`.
4. Use LangChain `RecursiveCharacterTextSplitter` with:

```python
chunk_size = 700
chunk_overlap = 150
add_start_index = True
```

5. For each chunk, read the LangChain-provided absolute `start_index`.
6. Resolve `start_index` to `start_time` with the shared interpolation algorithm.
7. Include enough metadata for vector indexing and source playback.

Output:

```json
[
  {
    "video_id": "youtube_id",
    "chunk_index": 0,
    "text": "chunk text",
    "start_index": 0,
    "start_time": 0.0,
    "source_type": "video"
  }
]
```

Write to:

```text
data_pipeline/videos/processed_chunks/<video_id>_chunks.json
```

## Books Pipeline

### Phase 1: PDF Extraction

Files:

```text
data_pipeline/books/books_main.py
data_pipeline/books/book_processor.py
```

Input:

```text
data_pipeline/books/input_books/*.pdf
```

Processing:

1. Iterate over PDFs in `input_books/`.
2. Derive a stable `book_name` from the PDF filename.
3. Check for `books_output/<book_name>.json`.
4. If it exists, skip extraction.
5. Extract text page by page.
6. Skip gracefully if the PDF has no extractable text.

Output:

```json
[
  {
    "page": 1,
    "text": "page text"
  }
]
```

Write to:

```text
data_pipeline/books/books_output/<book_name>.json
```

### Phase 2: Book LLM Enrichment

File:

```text
data_pipeline/books/book_enricher.py
```

Processing:

1. Load `books_output/<book_name>.json`.
2. Check for `books_enriched_metadata/<book_name>_meta.json`.
3. Concatenate page text into a full book string.
4. Build a smart sample because books may exceed the LLM context window.

Smart sample algorithm:

```text
first 40,000 characters

[...]

middle 8,000 characters

[...]

final 8,000 characters
```

Target metadata:

```json
{
  "book_name": "book_name",
  "author": "",
  "date_written": "",
  "summary": "",
  "questions": [],
  "key_learnings": [],
  "for_whom": [],
  "mood": "",
  "topics": [],
  "structure_type": "",
  "table_of_contents": []
}
```

Write to:

```text
data_pipeline/books/books_enriched_metadata/<book_name>_meta.json
```

### Phase 3: Book Semantic Chunking

File:

```text
data_pipeline/books/book_chunk_processor.py
```

Processing:

1. Load `books_output/<book_name>.json`.
2. Check for `books_processed_chunks/<book_name>_chunks.json`.
3. Concatenate pages into one full text string.
4. Build a `char_to_page_map` while concatenating.
5. Use LangChain `RecursiveCharacterTextSplitter` with:

```python
chunk_size = 700
chunk_overlap = 150
add_start_index = True
```

6. Map each chunk `start_index` to the source page using binary search over page character starts.
7. Optionally resolve an end page from the chunk end offset.

Output:

```json
[
  {
    "book_name": "book_name",
    "chunk_index": 0,
    "text": "chunk text",
    "start_index": 0,
    "start_page": 1,
    "end_page": 1,
    "source_type": "book"
  }
]
```

Write to:

```text
data_pipeline/books/books_processed_chunks/<book_name>_chunks.json
```

## Indexing Plan

After local JSON artifact generation is verified, add indexers that consume processed chunks and enriched metadata.

Qdrant records should include:

```json
{
  "id": "stable_chunk_id",
  "vector": [],
  "payload": {
    "source_type": "video_or_book",
    "source_id": "video_id_or_book_name",
    "chunk_index": 0,
    "text": "chunk text",
    "start_time": 0.0,
    "start_page": 1,
    "topics": []
  }
}
```

DynamoDB records should store source-level metadata and optionally chunk lookup metadata for fast retrieval.

Stable IDs should be deterministic:

```text
video::<video_id>::chunk::<chunk_index>
book::<book_name>::chunk::<chunk_index>
```

## Dependencies

Expected Python dependencies:

```text
youtube-transcript-api
langchain-text-splitters
openai
pypdf
qdrant-client
boto3
python-dotenv
tenacity
```

Use a small internal retry helper even if `tenacity` is installed, so retry behavior is explicit and testable.

## Test Plan

Unit tests:

1. JSON brace extraction handles clean JSON, fenced JSON, prefixed text, suffixed text, braces inside strings, and malformed responses.
2. Retry helper retries 429/quota-like errors and stops after the configured max attempts.
3. Video ID parsing handles common YouTube URL formats.
4. `char_to_time_map` generation preserves absolute character offsets.
5. Timestamp interpolation returns expected values for synthetic fragments.
6. Exact text lookup resolves direct matches and punctuation-normalized fallback matches.
7. Idempotency checks skip existing output files.
8. Empty transcript and empty PDF inputs are skipped without LLM calls.
9. Smart sampling returns first, middle, and final text sections with separators.
10. Book chunk page mapping resolves correct start and end pages.

Integration tests:

1. Mock transcript ingestion produces `output/<video_id>.json`.
2. Mock video LLM response produces enriched metadata with resolved story and music timestamps.
3. Mock video chunking produces chunks with stable `start_time`.
4. Sample PDF or mocked page JSON produces page-based book chunks.
5. Full local dry run processes multiple videos and books while skipping already-generated artifacts.

## Acceptance Criteria

The implementation is complete when:

1. Running the video pipeline creates raw transcript, enriched metadata, and processed chunk JSON files.
2. Running the book pipeline creates page extraction, enriched metadata, and processed chunk JSON files.
3. Re-running either pipeline skips existing outputs without repeating expensive work.
4. Video chunks and LLM-extracted story/music segments resolve to source timestamps through character-offset interpolation.
5. Book chunks resolve to page numbers through character-offset mapping.
6. Invalid or noisy LLM JSON is handled by the brace-counting parser.
7. Empty inputs, rate limits, quota errors, and missing transcripts are logged and handled gracefully.
8. Generated JSON artifacts are stable enough to feed downstream Qdrant and DynamoDB indexers.

## Implementation Order

1. Create shared utilities for logging, retries, JSON parsing, LLM access, and text splitting.
2. Build video transcript ingestion and validate raw transcript output.
3. Implement video character-to-time mapping and timestamp resolver with tests.
4. Implement video LLM enrichment and story/music timestamp resolution.
5. Implement video semantic chunking using LangChain start indexes.
6. Build book PDF extraction and validate page-level output.
7. Implement book smart sampling and LLM enrichment.
8. Implement book semantic chunking and page mapping.
9. Add integration tests with mocked network and LLM calls.
10. Add optional Qdrant and DynamoDB indexers after artifact generation is stable.
# codex_project

Multimodal spiritual search data pipeline for YouTube videos and PDF books.

The pipeline extracts raw source text, enriches it with an LLM, creates anchored
semantic chunks, generates BGE-M3 embeddings on Colab T4 GPU, and can upload
metadata/vectors to DynamoDB and Qdrant.

## What This Builds

- YouTube transcripts in `data_pipeline/videos/output/`
- Video LLM metadata in `data_pipeline/videos/enriched_metadata/`
- Zero-drift timestamped video chunks in `data_pipeline/videos/processed_chunks/`
- PDF page text in `data_pipeline/books/books_output/`
- Book LLM metadata in `data_pipeline/books/books_enriched_metadata/`
- Page-mapped book chunks in `data_pipeline/books/processed_books_chunks/`
- Optional BGE-M3 embedded chunks and Qdrant hybrid-search upload from Colab

## Recommended: Run In Google Colab

Use this notebook:

`data_pipeline/colab/codex_project.ipynb`

### Prerequisites

1. A Google account with Google Drive.
2. Google Colab with GPU runtime available.
3. Runtime set to **T4 GPU**:
   - Open the notebook in Colab.
   - Go to `Runtime -> Change runtime type`.
   - Select `T4 GPU`.
   - Save.
4. API keys added in Colab's Secrets panel.
5. For private GitHub repos, add a `GITHUB_TOKEN` secret with read access.
6. For book processing, upload PDFs to this Google Drive folder after Cell 1:
   - `/content/drive/MyDrive/codex_project/input_books`

### Required Colab Secrets

For OpenAI enrichment:

```text
OPENAI_API_KEY
```

For cloning a private repo:

```text
GITHUB_TOKEN
```

For Qdrant upload:

```text
QDRANT_URL
QDRANT_API_KEY
```

For DynamoDB upload:

```text
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
AWS_DEFAULT_REGION
DITTO_VIDEOS_TABLE
DITTO_BOOKS_TABLE
```

Optional overrides:

```text
GITHUB_REPO_URL
GITHUB_BRANCH
DITTO_LLM_MODEL
DITTO_LLM_TEMPERATURE
DITTO_LLM_MAX_ATTEMPTS
DITTO_VIDEO_SEGMENTS_TABLE
VIDEO_QDRANT_COLLECTION
BOOK_QDRANT_COLLECTION
```

## Colab Run Steps

1. Open `data_pipeline/colab/codex_project.ipynb` in Google Colab.
2. Set runtime to **T4 GPU**.
3. Add the secrets listed above in Colab's Secrets sidebar.
4. Run Cell 1 to mount Google Drive and create:
   - `/content/drive/MyDrive/codex_project`
5. Run Cell 2 to clone only the `feat/data-processing` branch, install dependencies, and symlink Drive folders.
6. Run Cell 3 and configure:
   - `VIDEO_URLS`
   - `RUN_VIDEOS`
   - `RUN_BOOKS`
   - `RUN_LLM_ENRICHMENT`
   - `RUN_DYNAMO_UPLOAD`
   - `RUN_EMBEDDINGS`
   - `RUN_QDRANT_UPLOAD`
7. Run the CPU cells for extraction, enrichment, and chunking.
8. Run the GPU cells for BGE-M3 embeddings.
9. Turn `RUN_QDRANT_UPLOAD = True` only when you are ready to upload vectors.
10. Run the verification cell to check output counts.

By default, the notebook does not upload to Qdrant or DynamoDB until you enable
those flags.

## Local Run Commands

Install dependencies:

```bash
pip install -r requirements.txt
```

Video pipeline:

```bash
python -m data_pipeline.videos.main "https://www.youtube.com/watch?v=VIDEO_ID"
python -m data_pipeline.videos.video_enricher
python -m data_pipeline.videos.transcript_processor
```

Book pipeline:

```bash
python -m data_pipeline.books.books_main
```

Put PDFs in:

```text
data_pipeline/books/input_books/
```

## Idempotency

Every file-producing phase checks whether its output already exists and skips it.
This prevents duplicate LLM calls and makes reruns safe.

## Notes

- Video timestamp mapping is character-offset based and uses interpolation inside
  transcript fragments for zero-drift chunk/story timestamps.
- Book chunking maps character offsets back to source page numbers.
