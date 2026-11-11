"""Parse one PDF and print document meta + clause stats."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingest.parse import parse_document  # noqa: E402


def main(pdf_path: str) -> None:
    doc = parse_document(Path(pdf_path))
    print("META:", doc.meta)
    print("CLAUSES:", len(doc.clauses))
    for clause in doc.clauses[:15]:
        print(f"  {clause.number} (p{clause.page}) [{clause.section}] {clause.text[:120]}")


if __name__ == "__main__":
    main(sys.argv[1])
