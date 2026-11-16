from app.rag.gost_refs import build_gost_alias_map, resolve_gost_references
from app.rag.query_classifier import extract_gosts

ALIASES = build_gost_alias_map(
    [
        "ГОСТ Р 71476—2024",
        "ГОСТ Р 71484.4—2024",
        "ПНСТ 963—2024",
    ]
)


def test_short_gost_is_expanded():
    resolved = resolve_gost_references("Что такое качество данных по ГОСТ Р 71476?", ALIASES)
    assert resolved == "Что такое качество данных по ГОСТ Р 71476—2024?"
    assert extract_gosts(resolved) == ["ГОСТ Р 71476—2024"]


def test_short_gost_without_r_is_expanded():
    resolved = resolve_gost_references("Что такое качество данных по ГОСТ 71476?", ALIASES)
    assert "ГОСТ Р 71476—2024" in resolved


def test_case_and_dash_variants():
    assert "ГОСТ Р 71476—2024" in resolve_gost_references("по гост р 71476", ALIASES)
    assert "ГОСТ Р 71476—2024" in resolve_gost_references("ГОСТ Р 71476-2024", ALIASES)
    assert "ГОСТ Р 71476—2024" in resolve_gost_references("ГОСТ Р 71476 2024", ALIASES)


def test_part_and_pnst_are_expanded():
    assert "ГОСТ Р 71484.4—2024" in resolve_gost_references("ГОСТ Р 71484.4", ALIASES)
    assert "ПНСТ 963—2024" in resolve_gost_references("ПНСТ 963", ALIASES)


def test_full_and_unknown_are_preserved():
    full = "Что такое граф знаний по ГОСТ Р 71540—2026?"
    assert resolve_gost_references(full, ALIASES) == full
    assert resolve_gost_references("ГОСТ Р 99999", ALIASES) == "ГОСТ Р 99999"


def test_ambiguous_base_is_preserved():
    aliases = build_gost_alias_map(["ГОСТ Р 1—2023", "ГОСТ Р 1—2024"])
    assert resolve_gost_references("по ГОСТ Р 1", aliases) == "по ГОСТ Р 1"


def test_resolution_is_idempotent():
    once = resolve_gost_references("по ГОСТ Р 71476", ALIASES)
    assert resolve_gost_references(once, ALIASES) == once
