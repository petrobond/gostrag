"""Build eval/gold_kb.yaml from the generated knowledge base."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.kb.kb import KnowledgeBase, norm_text  # noqa: E402


def main() -> None:
    kb = KnowledgeBase(Path("data/kb"))
    questions = []
    term_specs = [
        ("KB01", "Что такое граф знаний по ГОСТ Р 71540—2024?", "граф знаний", "ГОСТ Р 71540—2024"),
        ("KB02", "Что такое машинное обучение по ПНСТ 965—2024?", "машинное обучение", "ПНСТ 965—2024"),
        (
            "KB03",
            "Что такое искусственный интеллект по ГОСТ Р 59277—2020?",
            "искусственный интеллект",
            "ГОСТ Р 59277—2020",
        ),
        (
            "KB04",
            "Что такое качество данных по ПНСТ 1046—2026?",
            "качество данных",
            "ПНСТ 1046—2026",
        ),
    ]
    for qid, question, term, gost in term_specs:
        found = kb.find_term(term, gost)
        if not found:
            print("missing term", qid, term, gost)
            continue
        exact = [
            item for item in found if norm_text(item["term"]) == norm_text(term)
        ] or [item for item in found if norm_text(term) in item["term_norm"]]
        exact = [item for item in exact if len(item["definition"]) >= 80]
        item = max(exact or found, key=lambda row: len(row["definition"]))
        questions.append(
            {
                "id": qid,
                "category": "definition",
                "question": question,
                "expected_answer": item["definition"][:500],
                "expected_sources": [f"{item['gost']}, п. {item['clause']}"],
                "expect_refusal": False,
            }
        )

    outline_71484 = kb.outline("ГОСТ Р 71484.4—2024")
    questions.append(
        {
            "id": "KB05",
            "category": "kb_outline",
            "question": "Какие разделы включает ГОСТ Р 71484.4—2024?",
            "expected_answer": "; ".join(
                f"{section['section']} — {section['title']}"
                for section in outline_71484["sections"][:14]
            ),
            "expected_sources": ["ГОСТ Р 71484.4—2024, п. 1"],
            "expect_refusal": False,
        }
    )
    outline_72663 = kb.outline("ГОСТ Р 72663—2026")
    section8 = next(item for item in outline_72663["sections"] if item["section"] == "8")
    unique_clauses = []
    seen_clauses: set[str] = set()
    for clause in section8["clauses"]:
        if clause["clause"] in seen_clauses:
            continue
        seen_clauses.add(clause["clause"])
        unique_clauses.append(clause)
    questions.append(
        {
            "id": "KB06",
            "category": "kb_outline",
            "question": "Какие пункты входят в раздел 8 ГОСТ Р 72663—2026?",
            "expected_answer": "; ".join(
                f"{clause['clause']} — {clause['title']}"
                for clause in unique_clauses[:20]
            ),
            "expected_sources": ["ГОСТ Р 72663—2026, раздел 8"],
            "expect_refusal": False,
        }
    )
    links_71540 = kb.neighbors("ГОСТ Р 71540—2024")["outgoing"]
    internal = [edge["target"] for edge in links_71540 if edge["internal"]]
    questions.append(
        {
            "id": "KB07",
            "category": "kb_links",
            "question": "На какие стандарты корпуса ссылается ГОСТ Р 71540—2024?",
            "expected_answer": "; ".join(internal) or "ссылок на стандарты корпуса нет",
            "expected_sources": ["ГОСТ Р 71540—2024, п. 2"],
            "expect_refusal": False,
        }
    )
    incoming = [
        edge["source"]
        for edge in kb.neighbors("ГОСТ Р 71476—2024")["incoming"][:8]
    ]
    questions.append(
        {
            "id": "KB08",
            "category": "kb_links",
            "question": "Какие стандарты корпуса ссылаются на ГОСТ Р 71476—2024?",
            "expected_answer": "; ".join(incoming),
            "expected_sources": ["ГОСТ Р 71484.4—2024, п. 2"],
            "expect_refusal": False,
        }
    )
    path = kb.path("ГОСТ Р 71476—2024", "ГОСТ Р 59898—2021")
    questions.append(
        {
            "id": "KB09",
            "category": "kb_path",
            "question": "Как связаны ГОСТ Р 71476—2024 и ГОСТ Р 59898—2021?",
            "expected_answer": " → ".join(path),
            "expected_sources": ["ГОСТ Р 71476—2024, п. 2"],
            "expect_refusal": False,
        }
    )
    external = [
        edge["target"]
        for edge in kb.neighbors("ГОСТ Р 71562—2024")["outgoing"]
        if not edge["internal"]
    ][:8]
    questions.append(
        {
            "id": "KB10",
            "category": "kb_external",
            "question": "Какие внешние стандарты упоминает ГОСТ Р 71562—2024?",
            "expected_answer": "; ".join(external),
            "expected_sources": ["ГОСТ Р 71562—2024, п. 2"],
            "expect_refusal": False,
        }
    )

    out = {
        "version": "1.0",
        "corpus_version": kb.stats().get("corpus_version", ""),
        "notes": "KB gold: terms, outline, internal/external links, path",
        "questions": questions,
    }
    Path("eval/gold_kb.yaml").write_text(
        yaml.safe_dump(out, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    print(f"questions: {len(questions)}")
    for item in questions:
        print(item["id"], "|", item["question"], "|", item["expected_answer"][:100])


if __name__ == "__main__":
    main()
