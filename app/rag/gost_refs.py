"""Resolve short GOST references (without year) to canonical corpus numbers."""

from __future__ import annotations

import re
from collections.abc import Iterable

# Russian text often inflects the designation: «в ГОСТе Р 71476», «по ГОСТу Р …».
GOST_PREFIX = r"(?:ГОСТ(?:а|у|е|ом|ами|ах)?(?:\s*Р)?|ПНСТ(?:а|у|е|ом|ами|ах)?)"

GOST_FULL_RE = re.compile(
    rf"(?P<prefix>{GOST_PREFIX})\s*(?P<number>\d+(?:\.\d+){{0,3}})"
    r"\s*[—–-]\s*(?P<year>\d{4})",
    re.IGNORECASE,
)

# Year is optional: users often write "ГОСТ Р 71476" instead of "ГОСТ Р 71476—2024".
GOST_REF_RE = re.compile(
    rf"(?P<prefix>{GOST_PREFIX})\s*(?P<number>\d+(?:\.\d+){{0,3}})"
    r"(?:\s*[—–-]?\s*(?P<year>\d{4}))?",
    re.IGNORECASE,
)


def canonical_prefix(prefix: str) -> str:
    return "ПНСТ" if prefix.upper().startswith("ПНСТ") else "ГОСТ Р"


def _key(value: str) -> str:
    """Normalize a GOST designation for lookups (case/spaces/dashes-insensitive)."""
    return re.sub(r"[\s—–-]+", "", value or "").lower()


def _base(value: str) -> str:
    return re.sub(r"\s*[—–-]\s*\d{4}\s*$", "", value or "").strip()


def build_gost_alias_map(known: Iterable[str]) -> dict[str, str]:
    """Map full and year-less GOST designations to the canonical corpus value.

    A year-less base is mapped only when it is unambiguous: if the corpus has
    two editions of the same base, the short form is left untouched.
    """
    aliases: dict[str, str] = {}
    bases: dict[str, str] = {}
    ambiguous: set[str] = set()

    for raw in known:
        value = (raw or "").strip()
        if not value:
            continue
        aliases[_key(value)] = value
        base_key = _key(_base(value))
        if base_key in bases and bases[base_key] != value:
            ambiguous.add(base_key)
        else:
            bases[base_key] = value

    for key in ambiguous:
        bases.pop(key, None)
    aliases.update(bases)
    return aliases


def resolve_gost_references(question: str, aliases: dict[str, str]) -> str:
    """Replace known short GOST references with canonical full designations.

    Unknown numbers, different editions and ambiguous bases are preserved as-is,
    so the normal retrieval/refusal path is not changed for them.
    """
    if not question or not aliases:
        return question

    def replace(match: re.Match[str]) -> str:
        prefix = canonical_prefix(match.group("prefix"))
        number = match.group("number")
        year = match.group("year")
        key = _key(f"{prefix} {number}" + (f"—{year}" if year else ""))
        return aliases.get(key, match.group(0))

    return GOST_REF_RE.sub(replace, question)
