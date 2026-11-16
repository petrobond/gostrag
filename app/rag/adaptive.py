"""Small adaptive planner for structured term questions.

The planner deliberately does not enumerate every possible user intent. It only
routes questions that need a corpus tool; everything else stays on the existing
RAG fast path.
"""

from __future__ import annotations

from dataclasses import dataclass

TERM_MARKERS = ("термин", "поняти", "определени")
SUBSET_MARKERS = (
    "характериз",
    "относя",
    "описыва",
    "связан",
    "каса",
    "входит",
    "использу",
    "как цело",
    "относят",
    "определяют",
)
INVENTORY_MARKERS = ("какие", "перечисли", "список", "перечень", "назови", "основн")


@dataclass(frozen=True, slots=True)
class AdaptivePlan:
    kind: str
    gost_number: str
    question: str


def _has_term_marker(question: str) -> bool:
    return any(marker in question.lower() for marker in TERM_MARKERS)


def is_term_subset_question(question: str) -> bool:
    q = question.lower()
    return _has_term_marker(q) and any(marker in q for marker in SUBSET_MARKERS)


def is_term_inventory_question(question: str) -> bool:
    q = question.lower()
    if not _has_term_marker(q) or is_term_subset_question(q):
        return False
    return any(marker in q for marker in INVENTORY_MARKERS)


def plan_question(question: str, gost_numbers: list[str]) -> AdaptivePlan | None:
    if len(gost_numbers) != 1:
        return None
    gost = gost_numbers[0]
    if is_term_subset_question(question):
        return AdaptivePlan("term_subset", gost, question)
    if is_term_inventory_question(question):
        return AdaptivePlan("term_inventory", gost, question)
    return None
