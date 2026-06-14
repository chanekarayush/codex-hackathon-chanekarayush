# PulseCue

![PulseCue Banner](docs/BANNER.png)

**Find the right moment. Save hours. AI-powered semantic search across YouTube videos and PDF books.**

Multimodal motivation and fitness search data pipeline for YouTube videos and PDF books.

The pipeline extracts raw source text, enriches it with an LLM, creates anchored semantic chunks, generates BGE-M3 embeddings on GPU, and can upload metadata/vectors to DynamoDB and Qdrant.

---

## Table of Contents

- [Technology Stack](#technology-stack)
- [Project Overview & Architecture](#project-overview--architecture)
- [What This Builds](#what-this-builds)
- [Quick Start](#quick-start)
- [Setup Instructions](#setup-instructions)
  - [Google Colab Setup](#google-colab-setup)
  - [Local Machine Setup](#local-machine-setup)
  - [Cloud Backend Deployment](#cloud-backend-deployment)
- [Configuration & Secrets Management](#configuration--secrets-management)
- [Idempotency](#idempotency)
- [Notes](#notes)

---

## Technology Stack

![Python](https://img.shields.io/badge/Python-3.8+-3776ab?style=plastic&logo=python&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-Whisper%20%26%20GPT-412991?style=plastic&logo=openai&logoColor=white)
![Hugging Face](https://img.shields.io/badge/Hugging%20Face-BGE--M3-FFD21E?style=plastic&logo=huggingface&logoColor=white)
![Qdrant](https://img.shields.io/badge/Qdrant-Vector%20DB-4000FF?style=plastic&logo=data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgdmlld0JveD0iMCAwIDIwMCAyMDAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHBhdGggZD0iTTEwMCAxOEM1NS42IDExOSAxOCA5NSAxOCAxNDZDMTggMTY5LjkgMzYuMSAxODkgNTkgMTg5Qzg0LjkgMTg5IDEwNiAxNzAuMSAxMDYgMTQ2VjE4WiIgZmlsbD0id2hpdGUiIGZpbGwtb3BhY2l0eT0iMC44Ii8+PC9zdmc+&logoColor=white)
![AWS](https://img.shields.io/badge/AWS-Lambda%20%26%20DynamoDB-FF9900?style=plastic&logo=amazon-aws&logoColor=white)
![React](https://img.shields.io/badge/React-Vite-61dafb?style=plastic&logo=react&logoColor=white)
![LangChain](https://img.shields.io/badge/LangChain-Data%20Processing-121212?style=plastic&logo=data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgdmlld0JveD0iMCAwIDIwMCAyMDAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHBhdGggZD0iTTEwMCAxMEMxMjA3IDEwIDE0MCAxMzAgMTQwIDEwMENMNjAgMTAwQzYwIDEzMCA0MCAxNDAgMjAgMTQwQzAgMTQwIDAgMTIwIDAgMTAwQzAgMzAgNDAgMTAgMTAwIDEwWiIgZmlsbD0id2hpdGUiIGZpbGwtb3BhY2l0eT0iMC44Ii8+PC9zdmc+&logoColor=white)
![PyMuPDF](https://img.shields.io/badge/PyMuPDF-PDF%20Processing-red?style=plastic&logoColor=white)
![Tesseract](https://img.shields.io/badge/Tesseract-OCR-00838f?style=plastic&logoColor=white)
![Google Colab](https://img.shields.io/badge/Google%20Colab-T4%20GPU-F9AB00?style=plastic&logo=google-colab&logoColor=white)

> **Important:** Google Colab is used **solely for fast T4 GPU compute availability**. The pipeline itself has **NO Colab-specific dependencies** and can run on any system with GPU support (local GPU, cloud GPU instances, AWS SageMaker, etc.).

---

## Project Overview & Architecture

### Data Processing Pipeline

The PulseCue pipeline transforms raw video transcripts and PDF books into enriched, searchable data:

1. **Extract** - YouTube transcripts (via Whisper) and PDF text (via PyMuPDF + pytesseract)
2. **Enrich** - LLM processing to extract Topics, Queries, Moral Stories, Spiritual Songs (videos) and Chapters, Summaries, Audience (books)
3. **Chunk** - Semantic chunking with character-offset mapping for zero-drift timestamps
4. **Embed** - BGE-M3 embeddings via Hugging Face sentence-transformers
5. **Store** - Upload to Qdrant for hybrid search (semantic + keyword) and optional DynamoDB archival

### LLM Enrichment Pipeline

![LLM Enrichment Pipeline](docs/arch/photo_2026-06-14_22-59-33.jpg)

*YouTube videos and PDF books are processed through OpenAI API to extract structured metadata (Topics, Queries, Stories for videos; Chapters, Summaries, Audience for books).*

### Complete Data Processing Pipeline

![Data Processing Pipeline](docs/arch/photo_2026-06-14_22-59-35.jpg)

*End-to-end flow: Sources (YouTube, PDF, Audio) → Transcript/OCR extraction → LLM enrichment → Semantic chunking → BGE-M3 embeddings → Qdrant vector database.*

---

## What This Builds

- YouTube transcripts in `data_pipeline/videos/output/`
- Video LLM metadata in `data_pipeline/videos/enriched_metadata/`
- Zero-drift timestamped video chunks in `data_pipeline/videos/processed_chunks/`
- PDF page text in `data_pipeline/books/books_output/`
- Book LLM metadata in `data_pipeline/books/books_enriched_metadata/`
- Page-mapped book chunks in `data_pipeline/books/processed_books_chunks/`
- Optional BGE-M3 embedded chunks and Qdrant hybrid-search upload from GPU

---

## Quick Start

**Fastest way to run the pipeline on Google Colab with default settings:**

1. Open the notebook in Colab:
   ```
   https://colab.research.google.com/github/[your-github-path]/blob/main/data_pipeline/colab/codex_project.ipynb
   ```

2. Set runtime to **T4 GPU**: `Runtime → Change runtime type → GPU (T4)`

3. Add secrets in Colab sidebar:
   - `OPENAI_API_KEY` (required)

4. Run cells sequentially:
   - **Cell 1:** Mount Google Drive and set up directories
   - **Cell 2:** Clone repo, install dependencies, set up symlinks
   - **Cell 3:** Configure options (keep defaults for quick start)
   - **CPU cells:** Extraction, enrichment, chunking
   - **GPU cells:** BGE-M3 embeddings

5. Check results in `/content/drive/MyDrive/codex_project/output/`

---

## Setup Instructions

### Google Colab Setup

#### Prerequisites

1. A Google account with Google Drive access
2. Google Colab with GPU runtime available
3. Runtime set to **T4 GPU**:
   - Open the notebook in Colab
   - Go to `Runtime → Change runtime type`
   - Select `T4 GPU`
   - Click `Save`
4. API keys added in Colab's Secrets panel
5. For private GitHub repos, add a `GITHUB_TOKEN` secret with read access
6. For book processing, upload PDFs after Cell 1 to:
   - `/content/drive/MyDrive/codex_project/input_books`

#### Notebook Location

```
data_pipeline/colab/codex_project.ipynb
```

#### Colab Run Steps

1. Open `data_pipeline/colab/codex_project.ipynb` in Google Colab
2. Set runtime to **T4 GPU**
3. Add required and optional secrets (see [Configuration & Secrets Management](#configuration--secrets-management))
4. Run Cell 1 to mount Google Drive and create:
   - `/content/drive/MyDrive/codex_project`
5. Run Cell 2 to clone the `feat/data-processing` branch, install dependencies, and symlink Drive folders
6. Run Cell 3 and configure:
   - `VIDEO_URLS` - List of YouTube URLs to process
   - `RUN_VIDEOS` - Whether to process videos
   - `RUN_BOOKS` - Whether to process books
   - `RUN_LLM_ENRICHMENT` - Whether to run LLM enrichment (default: True)
   - `RUN_DYNAMO_UPLOAD` - Whether to upload to DynamoDB (default: False)
   - `RUN_EMBEDDINGS` - Whether to generate embeddings
   - `RUN_QDRANT_UPLOAD` - Whether to upload to Qdrant (default: False)
7. Run the CPU cells for extraction, enrichment, and chunking
8. Run the GPU cells for BGE-M3 embeddings
9. Turn `RUN_QDRANT_UPLOAD = True` **only** when you are ready to upload vectors
10. Run the verification cell to check output counts

> **Note:** By default, the notebook does not upload to Qdrant or DynamoDB until you enable those flags.

### Local Machine Setup

#### Prerequisites

1. Python 3.8 or higher
2. pip package manager
3. (For embeddings) NVIDIA GPU with CUDA support
4. (For PDFs with images) Tesseract OCR installed

#### Installation

Install Python dependencies:

```bash
pip install -r requirements.txt
```

#### Video Pipeline

Download and process YouTube videos:

```bash
python -m data_pipeline.videos.main "https://www.youtube.com/watch?v=VIDEO_ID"
python -m data_pipeline.videos.video_enricher
python -m data_pipeline.videos.transcript_processor
```

#### Book Pipeline

Process PDF books:

```bash
python -m data_pipeline.books.books_main
```

Place PDF files in:

```
data_pipeline/books/input_books/
```

#### Environment Variables

Create a `.env` file in the project root with:

```bash
OPENAI_API_KEY=your-key-here
QDRANT_URL=your-url-here  # optional
QDRANT_API_KEY=your-key-here  # optional
AWS_ACCESS_KEY_ID=your-key-here  # optional
AWS_SECRET_ACCESS_KEY=your-key-here  # optional
AWS_DEFAULT_REGION=us-east-1  # optional
```

### Cloud Backend Deployment

#### Backend Deployment

The AWS SAM backend lives in `cloud-backend/`.

For deployment instructions, see:

```
cloud-backend/PUBLISH.md
```

#### Frontend Setup

The React motivation search UI lives in `frontend/`.

For local development:

```bash
cd frontend
npm install
VITE_API_URL="https://your-api-id.execute-api.us-east-1.amazonaws.com/prod" npm run dev
```

#### Production Release

After the backend stack is deployed, publish both backend and UI:

```bash
cd cloud-backend
make release
```

This command:
- Builds the SAM backend
- Builds the `frontend/` React app
- Uploads the generated UI to the stack S3 bucket
- Writes `config.json` with the deployed API URL
- Invalidates CloudFront cache

---

## Configuration & Secrets Management

### Colab Secrets

Add secrets in Google Colab's Secrets panel (🔑 icon).

#### Required Secrets

Minimum required for the default pipeline configuration:

```text
OPENAI_API_KEY
```

#### Optional: GitHub Access

Only needed if using private GitHub repositories:

```text
GITHUB_TOKEN
```

#### Optional: Qdrant Integration

Only needed if `RUN_QDRANT_UPLOAD=True`:

```text
QDRANT_URL
QDRANT_API_KEY
```

#### Optional: AWS DynamoDB Integration

Only needed if `RUN_DYNAMO_UPLOAD=True`:

```text
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
AWS_DEFAULT_REGION
DITTO_VIDEOS_TABLE
DITTO_BOOKS_TABLE
```

#### Optional: Configuration Overrides

Customize defaults without modifying code:

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

#### Default Values

Used when optional overrides are not provided:

```text
GITHUB_BRANCH=feat/data-processing
DITTO_LLM_MODEL=gpt-4o-mini
DITTO_LLM_TEMPERATURE=0
DITTO_LLM_MAX_ATTEMPTS=6
VIDEO_QDRANT_COLLECTION=codex_project-videos
BOOK_QDRANT_COLLECTION=codex_project-books
```

---

## Idempotency

Every file-producing phase checks whether its output already exists and skips it.
This prevents duplicate LLM calls and makes reruns safe.

## Notes

- Video timestamp mapping is character-offset based and uses interpolation inside
  transcript fragments for zero-drift chunks, experiences, and fitness-advice timestamps.
- Book chunking maps character offsets back to source page numbers.
