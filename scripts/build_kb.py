"""Build data/kb: terms, reference graph and section outline from the corpus."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

WS_RE = re.compile(r"\s+")
REF_RE = re.compile(
    r"(ГОСТ\s*Р(?:\s+ИСО/МЭК)?|ПНСТ)\s*(\d+(?:\.\d+)?)\s*[—–-]\s*(\d{4})",
    re.IGNORECASE,
)
PAREN_RE = re.compile(r"\(([^()]{2,60})\)")
TERM_STRIP_RE = re.compile(r"[^а-яёa-z0-9 ]+")
EXTRA_ALIASES = {
    "искусственный интеллект": ["ИИ", "AI", "artificial intelligence"],
    "машинное обучение": ["ML", "machine learning"],
    "граф знаний": ["knowledge graph"],
    "большая языковая модель": ["LLM", "large language model"],
    "генерация дополненная поиском": ["RAG"],
    "качество данных": ["data quality"],
}


def clean(text: str, limit: int = 1200) -> str:
    return WS_RE.sub(" ", text).strip()[:limit]


def norm_term(text: str) -> str:
    return WS_RE.sub(" ", TERM_STRIP_RE.sub(" ", text.lower())).strip()


def load_chunks(path: Path) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            cid = row["chunk_id"]
            if cid in merged:
                merged[cid]["text"] += "\n" + row["text"]
            else:
                merged[cid] = row
    return merged


def normalize_ref(match: re.Match) -> str:
    kind = WS_RE.sub(" ", match.group(1).upper())
    return f"{kind} {match.group(2)}—{match.group(3)}"


def build_graph(rows: list[dict], standards: dict[str, dict]) -> dict:
    edges: dict[tuple[str, str], dict] = {}
    for row in rows:
        source = row["gost_number"]
        for match in REF_RE.finditer(row["text"]):
            target = normalize_ref(match)
            if target == source:
                continue
            key = (source, target)
            if key in edges:
                edges[key]["count"] += 1
                continue
            edges[key] = {
                "source": source,
                "target": target,
                "internal": target in standards,
                "clause": row["clause"],
                "page": int(row.get("page", 0) or 0),
                "quote": clean(row["text"])[:240],
                "count": 1,
            }
    targets = {edge["target"] for edge in edges.values()}
    nodes = []
    for gost, meta in sorted(standards.items()):
        nodes.append(
            {
                "id": gost,
                "gost": gost,
                "title": meta["title"],
                "doc_type": meta["doc_type"],
                "internal": True,
            }
        )
    for target in sorted(targets - set(standards)):
        nodes.append(
            {
                "id": target,
                "gost": target,
                "title": target,
                "doc_type": "external",
                "internal": False,
            }
        )
    return {"nodes": nodes, "edges": list(edges.values())}


def build_terms(rows: list[dict]) -> list[dict]:
    terms: dict[tuple[str, str], dict] = {}
    for row in rows:
        if not re.match(r"^3\.\d+$", row["clause"]) or not row.get("clause_title"):
            continue
        term = clean(row["clause_title"], 120)
        term = re.split(r"[:—–]", term, maxsplit=1)[0].strip() or term
        term_base = re.sub(r"\s*\([^)]*\)", "", term).strip() or term
        if len(term) < 2 or len(term) > 100:
            continue
        if term.lower() in ("общие положения", "термины и определения"):
            continue
        key = (norm_term(term_base), row["gost_number"])
        definition = clean(row["text"], 1200)
        aliases = [clean(match.group(1), 80) for match in PAREN_RE.finditer(term)]
        for needle, extra in EXTRA_ALIASES.items():
            if key[0] == needle or key[0].startswith(needle):
                aliases.extend(extra)
        aliases = sorted(
            {
                alias
                for alias in aliases
                if len(alias) >= 2 and not re.fullmatch(r"[a-z]{4,}", alias)
            }
        )
        candidate = {
            "term": term,
            "term_norm": key[0],
            "gost": row["gost_number"],
            "clause": row["clause"],
            "page": int(row.get("page", 0) or 0),
            "definition": definition,
            "aliases": aliases,
            "source_file": str(row.get("provenance", {}).get("file", "")),
        }
        current = terms.get(key)
        if current is None or len(candidate["definition"]) > len(current["definition"]):
            terms[key] = candidate
    return sorted(terms.values(), key=lambda item: (item["gost"], item["clause"]))

def clause_key(clause: str) -> tuple:
    parts = []
    for part in clause.replace("#", ".").split("."):
        parts.append((0, int(part), "") if part.isdigit() else (1, 0, part))
    return tuple(parts)


def build_outline(rows: list[dict]) -> dict[str, dict]:
    outline: dict[str, dict] = {}
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if row.get("chunk_type", "clause") != "clause":
            continue
        gost = row["gost_number"]
        doc = outline.setdefault(
            gost,
            {"gost": gost, "doc_id": row["doc_id"], "sections": {}},
        )
        clause = row.get("clause", "")
        dedupe_key = (gost, clause)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        section_raw = row.get("section", "") or "0"
        if section_raw.lower().startswith("приложение"):
            section = section_raw
        elif re.match(r"^\d+(?:\.\d+)+$", clause):
            section = clause.split(".")[0]
        else:
            section = section_raw
        section_title = row.get("section_title", "").strip()
        if not section_title:
            section_title = (
                f"Приложение {section.removeprefix('Приложение ').strip()}"
                if section.lower().startswith("приложение")
                else f"Раздел {section}"
            )
        bucket = doc["sections"].setdefault(
            section, {"section": section, "title": section_title, "clauses": []}
        )
        if clause == section and row.get("clause_title"):
            bucket["title"] = row["clause_title"]
        elif not bucket["title"]:
            bucket["title"] = section_title
        bucket["clauses"].append(
            {
                "clause": row["clause"],
                "title": row.get("clause_title", ""),
                "page": int(row.get("page", 0) or 0),
                "chunk_id": row["chunk_id"],
            }
        )
    for doc in outline.values():
        sections = []
        for section in sorted(
            doc["sections"].values(), key=lambda item: clause_key(item["section"])
        ):
            section["clauses"].sort(key=lambda item: clause_key(item["clause"]))
            sections.append(section)
        doc["sections"] = sections
    return outline


def main() -> None:
    corpus = Path("data/corpus/chunks.jsonl")
    out_dir = Path("data/kb")
    out_dir.mkdir(parents=True, exist_ok=True)
    chunks = load_chunks(corpus)
    rows = list(chunks.values())

    standards: dict[str, dict] = {}
    for row in rows:
        gost = row["gost_number"]
        if not gost:
            continue
        if row.get("chunk_type") == "meta" or gost not in standards:
            title = row.get("clause_title") or ""
            if not title:
                title = clean(row["text"], 120)
            standards[gost] = {
                "title": title,
                "doc_type": row.get("doc_type", "ГОСТ Р"),
            }

    graph = build_graph(rows, standards)
    terms = build_terms(rows)
    outline = build_outline(rows)
    meta = {
        "version": "1.0",
        "corpus_version": rows[0].get("corpus_version", ""),
        "generated_at": datetime.now(UTC).isoformat(),
        "terms": len(terms),
        "nodes": len(graph["nodes"]),
        "edges": len(graph["edges"]),
        "internal_nodes": sum(1 for node in graph["nodes"] if node["internal"]),
        "external_nodes": sum(1 for node in graph["nodes"] if not node["internal"]),
        "internal_edges": sum(1 for edge in graph["edges"] if edge["internal"]),
        "standards": len(outline),
    }
    graph["meta"] = meta
    (out_dir / "graph.json").write_text(
        json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (out_dir / "terms.jsonl").open("w", encoding="utf-8") as fh:
        for term in terms:
            fh.write(json.dumps(term, ensure_ascii=False) + "\n")
    (out_dir / "outline.json").write_text(
        json.dumps(outline, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print("terms by gost:", dict(Counter(term["gost"] for term in terms).most_common(5)))


if __name__ == "__main__":
    main()

