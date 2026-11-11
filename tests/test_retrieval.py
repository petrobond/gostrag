from app.llm.chain import classify
from app.retrieval.fusion import rrf


def test_rrf_prefers_items_present_in_both_lists():
    fused = rrf([["a", "b", "c"], ["b", "d"]], top_n=3)
    assert fused[0][0] == "b"


def test_rrf_returns_top_n():
    fused = rrf([["a", "b", "c"]], top_n=2)
    assert len(fused) == 2


def test_classify_simple():
    assert classify("Что такое граф знаний?") == "simple"


def test_classify_complex():
    assert classify("Сравни требования к качеству данных в 71484.2 и 72663 и объясни различия") == "complex"


def test_classify_medium():
    question = (
        "Опишите, какие этапы включает процесс управления качеством данных "
        "по ГОСТ Р 71484.4—2024 и как они соотносятся между собой"
    )
    assert classify(question) == "medium"
