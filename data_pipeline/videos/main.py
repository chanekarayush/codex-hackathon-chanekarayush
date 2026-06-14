"""CLI entrypoint for video Phase 1 transcript ingestion."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from data_pipeline.common import ensure_dir, get_logger
from data_pipeline.videos.manager import TranscriptIngestionBlocked, TranscriptManager


LOGGER = get_logger(__name__)
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def _read_urls_file(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def ingest_urls(
    urls: list[str],
    *,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    languages: list[str] | None = None,
) -> list[Path]:
    ensure_dir(output_dir)
    manager = TranscriptManager()
    saved_paths: list[Path] = []

    for url in urls:
        try:
            saved_path = manager.save_transcript(
                url,
                output_dir=output_dir,
                languages=languages,
            )
            if saved_path:
                saved_paths.append(saved_path)
        except TranscriptIngestionBlocked as exc:
            LOGGER.warning(
                "Stopping remaining transcript extraction after YouTube block for %s: %s. "
                "Continuing with already extracted transcripts.",
                url,
                exc,
            )
            break
        except Exception as exc:
            LOGGER.exception("Failed to ingest %s: %s", url, exc)

    return saved_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch YouTube transcripts for Ditto.")
    parser.add_argument("urls", nargs="*", help="YouTube URLs or raw 11-character video ids.")
    parser.add_argument("--urls-file", type=Path, help="Text file with one YouTube URL per line.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--languages",
        nargs="+",
        default=list(TranscriptManager.DEFAULT_LANGUAGES),
        help="Preferred transcript language codes in order.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    urls = list(args.urls)
    if args.urls_file:
        urls.extend(_read_urls_file(args.urls_file))

    if not urls:
        raise SystemExit("Provide at least one YouTube URL/id or --urls-file.")

    ingest_urls(urls, output_dir=args.output_dir, languages=args.languages)


if __name__ == "__main__":
    main()
