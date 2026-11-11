"""Preview cleaned lines for a PDF."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingest.clean import clean_pages, pages_to_lines  # noqa: E402
from app.ingest.extract import extract_pdf  # noqa: E402


def main(pdf_path: str, limit: int = 60) -> None:
    pages = extract_pdf(Path(pdf_path))
    lines = pages_to_lines(clean_pages(pages))
    print(f"pdf={pdf_path} lines={len(lines)}")
    for line in lines[:limit]:
        print(f"p{line.page:03d} [{line.size:.1f}] {line.text}")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 60)
