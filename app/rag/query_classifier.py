from __future__ import annotations

import re

from app.rag.gost_refs import GOST_FULL_RE, canonical_prefix

GOST_RE = GOST_FULL_RE
CLAUSE_RE = re.compile(r"(?:п\.?|пункт)\s*(\d+(?:\.\d+)+)", re.IGNORECASE)
TABLE_REF_RE = re.compile(
    r"таблиц[аыуе]\s+([А-ЯA-Z]?\.?\s?\d+(?:\.\d+)?)", re.IGNORECASE
)

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

CORPUS_LIST_RE = re.compile(
    r"(?:какие|какой|перечисли(?:те)?|список|перечень|назови(?:те)?)\s+"
    r"(?:все\s+)?(?:есть\s+)?"
    r"(?:гост(?:ы|ов)?|стандарт(?:ы|ов)?|пнст|нормативн\w*\s+документ\w*)",
    re.IGNORECASE,
)
CORPUS_LIST_NEGATIVE = (
    "характеристик",
    "этап",
    "слой",
    "требован",
    "показател",
    "вид",
    "состав",
    "пункт",
    "раздел",
    "таблиц",
    "определен",
    "термин",
    "качеств",
    "метод",
)
CORPUS_LIST_CONTEXT = (
    "ты знаешь",
    "вы знаете",
    "в корпусе",
    "в базе",
    "корпус",
    "доступн",
    "есть",
)
CORPUS_LIST_VERBS = ("перечисли", "список", "перечень", "назови")


def is_corpus_list_question(question: str) -> bool:
    """Strict detector for "which standards are in the corpus" inventory questions."""
    q = question.lower().strip()
    if re.search(r"(?:ссыл|ссыла|связан)", q):
        return False
    if GOST_RE.search(q):
        return False
    if not re.search(r"(?:гост|стандарт|пнст|нормативн)", q):
        return False
    if any(marker in q for marker in CORPUS_LIST_NEGATIVE):
        return False
    if any(verb in q for verb in CORPUS_LIST_VERBS):
        return True
    if CORPUS_LIST_RE.search(q):
        return any(marker in q for marker in CORPUS_LIST_CONTEXT)
    return False


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
    if is_corpus_list_question(q):
        return "corpus_list"
    if any(marker in q for marker in ("какие", "перечисли", "этапы", "слои", "характеристики", "виды", "состав")):
        return "enumeration"
    if any(marker in q for marker in ("что такое", "дай определение", "определение", "что понимается")):
        return "definition"
    return "general"


def extract_gosts(question: str) -> list[str]:
    result: list[str] = []
    for match in GOST_RE.finditer(question):
        prefix = canonical_prefix(match.group("prefix"))
        value = f"{prefix} {match.group('number')}—{match.group('year')}"
        if value not in result:
            result.append(value)
    return result


def extract_clause(question: str) -> str | None:
    match = CLAUSE_RE.search(question)
    return match.group(1) if match else None


def extract_table_ref(question: str) -> str | None:
    match = TABLE_REF_RE.search(question)
    return match.group(1).replace(" ", "") if match else None


def is_injection(question: str) -> bool:
    return classify_question(question) == "injection"


TERM_RE = re.compile(
    r"(?:что такое|дай определение|определение|что понимается под)\s+(.+?)(?:\s+(?:по|в)\s+ГОСТ|\s*$)",
    re.IGNORECASE,
)
APPENDIX_RE = re.compile(r"приложени[еи]\s+([А-ЯA-Z]+)", re.IGNORECASE)
COMPARISON_RE = re.compile(
    r"чем\s+отлича(?:ются|ется|ет)\s+(.+?)\s+и\s+(.+?)"
    r"(?:\s+(?:в|по)\s+ГОСТ|\s*\?|$)",
    re.IGNORECASE,
)


def extract_comparison_entities(question: str) -> list[str]:
    """Split "чем отличаются A и B" into A and B for per-entity lookup."""
    match = COMPARISON_RE.search(question)
    if not match:
        return []
    left = match.group(1).strip(" .,?»«")
    right = match.group(2).strip(" .,?»«")
    return [entity for entity in (left, right) if entity]



def extract_term(question: str) -> str:
    match = TERM_RE.search(question)
    if match:
        return match.group(1).strip(" .?»«")
    return question.strip(" .?")


def extract_appendix(question: str) -> str:
    match = APPENDIX_RE.search(question)
    return match.group(1) if match else ""

