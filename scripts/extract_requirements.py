"""Extract applicable requirements from the corpus for the GOST audit."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MODAL_RE = re.compile(r"\b(должен|должна|должно|должны|следует|рекомендуется)\b", re.IGNORECASE)

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

SEVERITY = {
    "данные": "high",
    "качество": "high",
    "тестирование": "high",
    "безопасность": "high",
    "знания": "medium",
    "архитектура": "medium",
    "документация": "medium",
    "жизненный цикл": "medium",
    "управление": "medium",
    "терминология": "low",
}


def category_of(text: str) -> str:
    lowered = text.lower()
    for category, markers in CATEGORIES.items():
        if any(marker in lowered for marker in markers):
            return category
    return "прочее"


def main(out_path: str = "eval/requirements.yaml", limit: int = 80) -> None:
    rows = [json.loads(line) for line in Path("data/corpus/chunks.jsonl").open(encoding="utf-8")]
    seen: set[str] = set()
    requirements: list[dict] = []
    for row in rows:
        text = row["text"]
        match = MODAL_RE.search(text)
        if not match:
            continue
        category = category_of(text)
        if category == "прочее":
            continue
        key = f"{row['gost_number']}#{row['clause']}"
        if key in seen:
            continue
        seen.add(key)
        requirements.append(
            {
                "id": f"REQ-{len(requirements) + 1:03d}",
                "gost": row["gost_number"],
                "clause": row["clause"],
                "requirement": text.strip()[:600],
                "modality": match.group(1).lower(),
                "category": category,
                "severity": SEVERITY.get(category, "low"),
                "chunk_id": row["chunk_id"],
            }
        )
        if len(requirements) >= limit:
            break

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(
        yaml.safe_dump(requirements, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"requirements: {len(requirements)} -> {out_path}")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "eval/requirements.yaml"
    lim = int(sys.argv[2]) if len(sys.argv) > 2 else 80
    main(out, lim)
