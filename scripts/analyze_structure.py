"""Analyze corpus structure: sections, clause depth, tables, appendices, cross-refs."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    rows = [json.loads(line) for line in Path("data/corpus/chunks.jsonl").open(encoding="utf-8")]
    sections = Counter()
    depths = Counter()
    lengths = []
    tables = 0
    appendices = 0
    notes = 0
    cross_refs = 0
    definitions = 0
    lists = 0

    for row in rows:
        section = row.get("section", "")
        sections[section] += 1
        clause = row["clause"]
        depth = clause.count(".") + 1 if clause else 0
        depths[depth] += 1
        lengths.append(len(row["text"]))
        text = row["text"].lower()
        if "таблица" in text:
            tables += 1
        if section.startswith("Приложение"):
            appendices += 1
        if "примечание" in text:
            notes += 1
        if re.search(r"в соответствии с (гост|пнст)|ссылается на|см\. (гост|пнст)", text):
            cross_refs += 1
        if re.search(r"^\S+\s*\([^)]*\):", row["text"]):
            definitions += 1
        if re.search(r"(^|\s)([а-я]\)|\d\))", row["text"]):
            lists += 1

    print(f"chunks={len(rows)}")
    print(f"length: min={min(lengths)} max={max(lengths)} avg={sum(lengths)/len(lengths):.0f}")
    print("depth distribution:", dict(sorted(depths.items())))
    print("top sections:", sections.most_common(15))
    print(f"tables={tables} appendices={appendices} notes={notes} cross_refs={cross_refs} definitions={definitions} lists={lists}")


if __name__ == "__main__":
    main()
