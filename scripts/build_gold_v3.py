"""Build eval/gold_set_v3.yaml: keep gold v2 and add corpus-grounded questions."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import yaml

CLAUSE_RE = re.compile(r"^\d+(?:\.\d+)+$")
TABLE_RE = re.compile(r"Таблица\s+([\wА-Яа-яЁё.-]+)")
WS_RE = re.compile(r"\s+")


def clean(text: str, limit: int = 500) -> str:
    return WS_RE.sub(" ", text).strip()[:limit]


def is_noisy_table(text: str, threshold: int = 8) -> bool:
    """Skip OCR-garbled tables: many isolated one-letter tokens in headers."""
    single = re.findall(r"(?:^|\s)[А-ЯЁA-Zа-яёa-z](?=\s|$)", text)
    return len(single) >= threshold


def load_chunks(path: Path) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            chunk_id = row["chunk_id"]
            if chunk_id in merged:
                merged[chunk_id]["text"] += "\n" + row["text"]
            else:
                merged[chunk_id] = row
    return merged


def item(question: str, answer: str, sources: list[str], page: int, quote: str) -> dict:
    return {
        "question": question,
        "expected_answer": clean(answer),
        "expected_sources": sources,
        "expected_page": page,
        "expected_quote": clean(quote, 200),
        "expect_refusal": False,
    }


def main() -> None:
    gold_path = Path("eval/gold_set_v2.yaml")
    out_path = Path("eval/gold_set_v3.yaml")
    gold = yaml.safe_load(gold_path.read_text(encoding="utf-8"))
    chunks = load_chunks(Path("data/corpus/chunks.jsonl"))
    rows = list(chunks.values())
    used_sources = {
        (source.split(",")[0].strip(), source.split("п.")[-1].strip())
        for row in gold["questions"]
        for source in row.get("expected_sources", [])
    }
    used_questions = {row["question"].strip().lower() for row in gold["questions"]}
    coverage = Counter(row["gost_number"] for row in rows)
    additions: list[dict] = []

    def add(row: dict) -> None:
        text = row["question"].strip().lower()
        if text in used_questions:
            return
        used_questions.add(text)
        additions.append(row)

    def count(kind: str) -> int:
        return sum(1 for row in additions if row.get("_kind") == kind)

    # 1. Clause lookup: one per standard, least-covered standards first.
    eligible = [
        row
        for row in rows
        if row.get("chunk_type", "clause") == "clause"
        and CLAUSE_RE.match(row["clause"])
        and 250 <= len(row["text"]) <= 1200
        and row.get("page", 0) > 0
        and (row["gost_number"], row["clause"]) not in used_sources
    ]
    by_standard: dict[str, list[dict]] = defaultdict(list)
    for row in eligible:
        by_standard[row["gost_number"]].append(row)
    for gost in sorted(by_standard, key=lambda name: (coverage[name], name)):
        if count("clause") >= 8:
            break
        row = by_standard[gost][0]
        add(
            {
                "_kind": "clause",
                "id": f"CL{count('clause') + 1:02d}",
                "category": "clause_lookup",
                **item(
                    f"Что говорится в п. {row['clause']} {gost}?",
                    row["text"],
                    [f"{gost}, п. {row['clause']}"],
                    int(row.get("page", 0)),
                    row["text"],
                ),
            }
        )

    # 2. Tables: one per standard, real table number only.
    table_rows = [
        row
        for row in rows
        if row.get("chunk_type") == "table"
        and TABLE_RE.search(row["clause"])
        and len(row["text"]) >= 200
        and row.get("page", 0) > 0
        and not is_noisy_table(row["text"])
    ]
    table_by_standard: dict[str, list[dict]] = defaultdict(list)
    for row in table_rows:
        table_by_standard[row["gost_number"]].append(row)
    for gost in sorted(table_by_standard, key=lambda name: (coverage[name], name)):
        if count("table") >= 4:
            break
        row = table_by_standard[gost][0]
        number = TABLE_RE.search(row["clause"]).group(1)
        add(
            {
                "_kind": "table",
                "id": f"TB{count('table') + 1:02d}",
                "category": "table",
                **item(
                    f"Что приведено в таблице {number} {gost}?",
                    row["text"],
                    [f"{gost}, таблица {number}"],
                    int(row.get("page", 0)),
                    row["text"],
                ),
            }
        )

    # 3. Enumeration: sections with >=3 clauses and a meaningful title.
    sections: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        if row.get("chunk_type", "clause") == "clause" and row.get("section"):
            sections[(row["doc_id"], row["section"])].append(row)
    candidates = []
    for (_doc_id, section), items in sections.items():
        if not section.isdigit() or section in ("1", "2", "3", "4"):
            continue
        titled = [row for row in items if row.get("clause_title") and row.get("page", 0) > 0]
        if len(titled) < 3:
            continue
        section_title = titled[0].get("section_title", "")
        if len(section_title) < 8:
            continue
        candidates.append((titled, section, section_title))
    candidates.sort(key=lambda value: (-len(value[0]), value[1]))
    for items, section, section_title in candidates:
        if count("section") >= 4:
            break
        gost = items[0]["gost_number"]
        ordered = sorted(items, key=lambda row: row["clause"])
        answer = "; ".join(
            f"{row['clause']} — {row['clause_title'][:80]}" for row in ordered[:8]
        )
        add(
            {
                "_kind": "section",
                "id": f"EN{count('section') + 1:02d}",
                "category": "enumeration",
                **item(
                    f"Какие пункты включает раздел {section} «{section_title}» {gost}?",
                    answer,
                    [f"{gost}, раздел {section}"],
                    int(ordered[0].get("page", 0)),
                    ordered[0]["text"],
                ),
            }
        )


    # 4. Definitions from clause titles in section 3.
    definitions = [
        row
        for row in rows
        if row.get("chunk_type", "clause") == "clause"
        and row["clause"].startswith("3.")
        and row.get("clause_title")
        and 200 <= len(row["text"]) <= 1000
        and row.get("page", 0) > 0
        and (row["gost_number"], row["clause"]) not in used_sources
    ]
    for row in definitions:
        if count("definition") >= 4:
            break
        add(
            {
                "_kind": "definition",
                "id": f"DF{count('definition') + 1:02d}",
                "category": "definition",
                **item(
                    f"Что такое {row['clause_title'][:80]} по {row['gost_number']}?",
                    row["text"],
                    [f"{row['gost_number']}, п. {row['clause']}"],
                    int(row.get("page", 0)),
                    row["text"],
                ),
            }
        )

    # 5. Cross-references: clause 2 of a standard.
    refs = [
        row
        for row in rows
        if row["clause"] in ("2", "2.1")
        and ("ГОСТ Р" in row["text"] or "ПНСТ" in row["text"])
        and len(row["text"]) >= 200
        and row.get("page", 0) > 0
    ]
    for row in refs:
        if count("ref") >= 2:
            break
        add(
            {
                "_kind": "ref",
                "id": f"XR{count('ref') + 1:02d}",
                "category": "cross_reference",
                **item(
                    f"На какие стандарты ссылается {row['gost_number']}?",
                    row["text"],
                    [f"{row['gost_number']}, раздел 2"],
                    int(row.get("page", 0)),
                    row["text"],
                ),
            }
        )

    clean_additions = []
    for row in additions:
        row = dict(row)
        if row["id"].startswith(("EN", "XR")):
            # Synthetic EN/XR questions are diagnostic only: their expected
            # clause slices do not match the real section composition.
            continue
        if row["id"].startswith("TB") and is_noisy_table(row["expected_answer"], threshold=4):
            # OCR-garbled table excerpts make the reference answer unreadable.
            continue
        row.pop("_kind", None)
        clean_additions.append(row)

    gold["version"] = "3.0.0"
    gold["notes"] = (
        "v3: gold v2 (37) + corpus-grounded additions; expected page/quote added; "
        "generated by scripts/build_gold_v3.py"
    )
    gold["questions"] = gold["questions"] + clean_additions
    out_path.write_text(
        yaml.safe_dump(gold, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    categories = Counter(row["category"] for row in gold["questions"])
    covered = {
        source.split(",")[0].strip()
        for row in gold["questions"]
        for source in row.get("expected_sources", [])
    }
    print(f"questions: {len(gold['questions'])}")
    print(f"categories: {dict(categories)}")
    print(f"standards with sources: {len(covered)}")


if __name__ == "__main__":
    main()

