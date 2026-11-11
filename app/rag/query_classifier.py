from __future__ import annotations

import re

GOST_RE = re.compile(r"(ГОСТ\s*Р|ПНСТ)\s*(\d+(?:\.\d+)?)\s*[—–-]\s*(\d{4})", re.IGNORECASE)
CLAUSE_RE = re.compile(r"(?:п\.?|пункт)\s*(\d+(?:\.\d+)+)", re.IGNORECASE)

INJECTION_MARKERS = (
    "игнорируй",
    "проигнорируй",
    "забудь",
    "ты больше не",
    "системный промпт",
    "system prompt",
    "секретн",
    "ключи",
    "удали все",
    "выполни",
    "ignore previous",
)


def classify_question(question: str) -> str:
    q = question.lower().strip()
    if any(marker in q for marker in INJECTION_MARKERS):
        return "injection"
    if CLAUSE_RE.search(q):
        return "clause_lookup"
    if "чем отлича" in q or q.startswith("сравни") or "в чём разница" in q:
        return "comparison"
    if "приложени" in q:
        return "appendix"
    if "таблиц" in q:
        return "table"
    if "ссыл" in q and ("гост" in q or "стандарт" in q):
        return "cross_reference"
    if q.startswith(("является ли", "обязател", "можно ли", "должен ли")):
        return "binary"
    if "когда" in q and ("введ" in q or "действ" in q or "опубликов" in q):
        return "temporal"
    if any(marker in q for marker in ("какие", "перечисли", "этапы", "слои", "характеристики", "виды", "состав")):
        return "enumeration"
    if any(marker in q for marker in ("что такое", "дай определение", "определение", "что понимается")):
        return "definition"
    return "general"


def extract_gosts(question: str) -> list[str]:
    result: list[str] = []
    for match in GOST_RE.finditer(question):
        value = f"{match.group(1).upper()} {match.group(2)}—{match.group(3)}"
        if value not in result:
            result.append(value)
    return result


def is_injection(question: str) -> bool:
    return classify_question(question) == "injection"


TERM_RE = re.compile(
    r"(?:что такое|дай определение|определение|что понимается под)\s+(.+?)(?:\s+(?:по|в)\s+ГОСТ|\s*$)",
    re.IGNORECASE,
)
APPENDIX_RE = re.compile(r"приложени[еи]\s+([А-ЯA-Z]+)", re.IGNORECASE)


def extract_term(question: str) -> str:
    match = TERM_RE.search(question)
    if match:
        return match.group(1).strip(" .?»«")
    return question.strip(" .?")


def extract_appendix(question: str) -> str:
    match = APPENDIX_RE.search(question)
    return match.group(1) if match else ""

