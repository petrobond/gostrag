"""Diagnose PDF text spans: colors, sizes, repeated strings (watermarks)."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingest.extract import extract_pdf, is_grayish, rgb_of  # noqa: E402


def main(pdf_path: str) -> None:
    pages = extract_pdf(Path(pdf_path))
    colors: Counter[int] = Counter()
    sizes: Counter[float] = Counter()
    texts: Counter[str] = Counter()
    gray = 0
    total = 0

    for page in pages:
        for span in page.spans:
            total += 1
            colors[span.color] += 1
            sizes[round(span.size, 1)] += 1
            texts[span.text.strip()] += 1
            if is_grayish(span.color):
                gray += 1

    print(f"pages={len(pages)} spans={total} grayish={gray} ({gray / max(total, 1):.1%})")
    print("top colors:")
    for color, count in colors.most_common(10):
        print(f"  rgb={rgb_of(color)} count={count}")
    print("top sizes:")
    for size, count in sizes.most_common(10):
        print(f"  size={size} count={count}")
    print("repeated texts (possible watermarks):")
    for text, count in texts.most_common(40):
        if count >= 3 and len(text) <= 40:
            print(f"  {count}x {text!r}")


if __name__ == "__main__":
    main(sys.argv[1])
