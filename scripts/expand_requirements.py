"""Expand the audit requirements from corpus clauses.

Existing requirements get applicability metadata; new requirements are taken
from clauses with modal verbs (should/must) and verified by chunk_id/page.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import yaml

MODAL_RE = re.compile(r"\b(должен|должна|должно|должны|следует|рекомендуется)\b", re.I)
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
BOILERPLATE = (
    "нормативные ссылки",
    "область применения",
    "соглашения по терминологии",
    "при пользовании настоящим стандартом",
    "издание официальное",
    "дата введения",
)
QUOTAS = {
    "ГОСТ Р 59926—2021": 6,
    "ГОСТ Р 59898—2021": 10,
    "ГОСТ Р 72514—2026": 10,
    "ГОСТ Р 71484.2—2024": 10,
    "ГОСТ Р 72663—2026": 8,
    "ГОСТ Р 71540—2024": 8,
    "ГОСТ Р 71752—2024": 6,
    "ПНСТ 965—2024": 6,
    "ГОСТ Р 71866—2024": 6,
    "ГОСТ Р 59925—2021": 6,
    "ПНСТ 943—2024": 4,
    "ПНСТ 963—2024": 4,
    "ГОСТ Р 71562—2024": 6,
    "ГОСТ Р 71484.3—2024": 10,
    "ГОСТ Р 59276—2020": 6,
    "ГОСТ Р 59277—2020": 6,
    "ГОСТ Р 71476—2024": 8,
    "ГОСТ Р 71484.4—2024": 8,
}
MAX_PER_GOST = 12
EXCLUDED_GOSTS = {"ПНСТ 1046—2026", "ПНСТ 836—2023"}
TERMINOLOGY_OK = {
    "ГОСТ Р 72663—2026",
    "ГОСТ Р 59276—2020",
    "ГОСТ Р 59277—2020",
    "ГОСТ Р 71562—2024",
}
SECTION_OK = {
    "ГОСТ Р 59926—2021",
    "ГОСТ Р 72514—2026",
    "ГОСТ Р 71484.2—2024",
}
GOST_CATEGORY = {
    "ГОСТ Р 71562—2024": "тестирование",
    "ГОСТ Р 59276—2020": "управление",
    "ГОСТ Р 59277—2020": "терминология",
    "ГОСТ Р 72663—2026": "качество",
    "ГОСТ Р 59926—2021": "данные",
    "ГОСТ Р 72514—2026": "безопасность",
    "ГОСТ Р 59898—2021": "тестирование",
}
NA_IDS = {
    "REQ-006",
    "REQ-008",
    "REQ-009",
    "REQ-021",
    "REQ-026",
    "REQ-031",
    "REQ-035",
    "REQ-037",
    "REQ-043",
    "REQ-046",
    "REQ-047",
    "REQ-048",
    "REQ-049",
    "REQ-050",
    "REQ-051",
}
APPLICABLE_REASONS = {
    "REQ-013": "Применимо: система эксплуатируется в РФ; юрисдикция и локализация "
    "зафиксированы в docs/scope.md.",
    "REQ-042": "Применимо: gold set и правила разметки ведутся вручную; "
    "docs/test_plan.md, eval/gold_set_v3.yaml.",
}
EVIDENCE = {
    "данные": "docs/data_quality.md; data/corpus/quality_report.json",
    "терминология": "docs/glossary.md; data/kb/terms.jsonl",
    "знания": "docs/kb.md; app/kb/kb.py",
    "архитектура": "docs/architecture.md; app/rag/retriever.py",
    "качество": "docs/eval_results_v3.md; eval/",
    "тестирование": "docs/test_plan.md; tests/",
    "документация": "docs/",
    "безопасность": "docs/trust.md; app/guard/",
    "жизненный цикл": "docs/architecture.md; plans/",
    "управление": "docs/operations.md",
    "прочее": "docs/architecture.md",
}
CATEGORIES = {
    "терминология": ("термин", "определен", "понятие"),
    "данные": ("данн", "качеств", "разметк", "набор"),
    "знания": ("знани", "онтолог", "граф", "база знаний"),
    "архитектура": ("архитектур", "слой", "компонент"),
    "качество": ("качеств", "показател", "метрик", "оценк"),
    "тестирование": ("тест", "испытан", "верификац", "валидац"),
    "документация": ("документ", "описан", "отчет", "запис"),
    "безопасность": ("безопасн", "защит", "риск", "конфиденциальн"),
    "жизненный цикл": ("жизненн", "цикл", "эксплуатац", "сопровожд"),
    "управление": ("управлен", "ответственн", "роль", "процесс"),
}


def category_of(text: str) -> str:
    lowered = text.lower()
    for category, markers in CATEGORIES.items():
        if any(marker in lowered for marker in markers):
            return category
    return "прочее"


def requirement_sentence(text: str) -> tuple[str, str] | None:
    cleaned = " ".join(text.replace("\n", " ").split())
    for sentence in SENTENCE_RE.split(cleaned):
        sentence = " ".join(sentence.split())
        if len(sentence) < 60:
            continue
        if sentence[:1].islower():
            sentence = sentence[0].upper() + sentence[1:]
        if "?" in sentence or "должны были" in sentence.lower():
            continue
        if sentence.lower().startswith(("это ваш", "мы ", "примечание", "например")):
            continue
        modal = MODAL_RE.search(sentence)
        if modal:
            return sentence[:600], modal.group(1).lower()
    if len(cleaned) >= 80 and MODAL_RE.search(cleaned) and "?" not in cleaned:
        modal = MODAL_RE.search(cleaned)
        return cleaned[:600], modal.group(1).lower()
    return None

def main() -> None:
    root = Path("eval/requirements.yaml")
    requirements = yaml.safe_load(root.read_text(encoding="utf-8"))
    findings = {
        item["requirement_id"]: item
        for item in json.loads(
            Path("docs/reports/3.1.0/1/audit.json").read_text(encoding="utf-8")
        )
    }
    chunks = [
        json.loads(line)
        for line in Path("data/corpus_v2/chunks.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    by_chunk = {row["chunk_id"]: row for row in chunks}

    for item in requirements:
        item.setdefault(
            "applicability", "not_applicable" if item["id"] in NA_IDS else "applicable"
        )
        finding = findings.get(item["id"], {})
        if item["applicability"] == "not_applicable":
            item["applicability_reason"] = (
                finding.get("evidence")
                or "Не применимо: требование относится к обучению модели, RL "
                "или иной функции, отсутствующей в RAG-системе."
            )[:240]
        else:
            item["applicability_reason"] = APPLICABLE_REASONS.get(
                item["id"],
                "Применимо: требование относится к данным, качеству, тестированию "
                "или архитектуре RAG-системы.",
            )
        item.setdefault("evidence_hint", EVIDENCE.get(item["category"], EVIDENCE["прочее"]))
        chunk = by_chunk.get(item.get("chunk_id", ""))
        if chunk:
            item.setdefault("page", chunk["page"])

    existing = {(item["gost"], str(item["clause"])) for item in requirements}
    candidates: dict[str, list[dict]] = defaultdict(list)
    for row in chunks:
        if row.get("chunk_type") != "clause":
            continue
        if row.get("gost_number") in EXCLUDED_GOSTS:
            continue
        clause = str(row.get("clause", ""))
        if clause in {"1", "2"}:
            continue
        if clause.startswith("3.") and row["gost_number"] not in TERMINOLOGY_OK:
            continue
        if "." not in clause and row["gost_number"] not in SECTION_OK:
            continue
        if "приложение" in clause.lower():
            continue
        text = " ".join(row.get("text", "").split())
        if len(text) < 80 or len(text) > 1200:
            continue
        if any(marker in text.lower() for marker in BOILERPLATE):
            continue
        if requirement_sentence(text) is None:
            continue
        if (row["gost_number"], clause) in existing:
            continue
        category = category_of(text)
        if category == "прочее":
            category = GOST_CATEGORY.get(row["gost_number"], "прочее")
        if category == "прочее":
            continue
        candidates[row["gost_number"]].append(row)

    selected: list[dict] = []
    for gost, quota in QUOTAS.items():
        if len(requirements) + len(selected) >= 170:
            break
        rows = sorted(
            candidates.get(gost, []), key=lambda item: (item["page"], item["clause"])
        )
        take = min(quota, 170 - len(requirements) - len(selected))
        selected.extend(rows[:take])
    if len(requirements) + len(selected) < 170:
        used = {(row["gost_number"], row["clause"]) for row in selected}
        per_gost: Counter[str] = Counter(row["gost_number"] for row in selected)
        for _gost, rows in candidates.items():
            for row in sorted(rows, key=lambda item: (item["page"], item["clause"])):
                if len(requirements) + len(selected) >= 170:
                    break
                if (row["gost_number"], row["clause"]) in used:
                    continue
                if per_gost[row["gost_number"]] >= MAX_PER_GOST:
                    continue
                selected.append(row)
                used.add((row["gost_number"], row["clause"]))
                per_gost[row["gost_number"]] += 1

    for row in selected:
        parsed = requirement_sentence(" ".join(row["text"].split()))
        if parsed is None:
            continue
        text, modality = parsed
        category = category_of(text)
        if category == "прочее":
            category = GOST_CATEGORY.get(row["gost_number"], "прочее")
        if category == "прочее":
            continue
        requirements.append(
            {
                "id": f"REQ-{len(requirements) + 1:03d}",
                "gost": row["gost_number"],
                "clause": row["clause"],
                "requirement": text,
                "modality": modality,
                "category": category,
                "severity": "high"
                if category in {"данные", "качество", "тестирование", "безопасность"}
                else "medium",
                "chunk_id": row["chunk_id"],
                "page": row["page"],
                "applicability": "applicable",
                "applicability_reason": "Применимо: требование взято из корпуса "
                "и относится к RAG-системе.",
                "evidence_hint": EVIDENCE.get(category, EVIDENCE["прочее"]),
            }
        )

    root.write_text(
        yaml.safe_dump(requirements, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print("requirements:", len(requirements))
    print("by gost:", dict(Counter(item["gost"] for item in requirements)))
    print(
        "applicability:",
        dict(Counter(item["applicability"] for item in requirements)),
    )
    print(
        "na:",
        sorted(
            item["id"]
            for item in requirements
            if item["applicability"] == "not_applicable"
        ),
    )


if __name__ == "__main__":
    main()
