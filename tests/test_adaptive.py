from app.rag.adaptive import (
    is_term_inventory_question,
    is_term_subset_question,
    plan_question,
)


def test_inventory_question_is_detected():
    question = "Какие основные термины определены в ГОСТ Р 71476—2024?"
    assert is_term_inventory_question(question)
    assert not is_term_subset_question(question)
    plan = plan_question(question, ["ГОСТ Р 71476—2024"])
    assert plan is not None
    assert plan.kind == "term_inventory"


def test_subset_question_is_detected():
    question = "Какие термины ГОСТ Р 71476—2024 характеризуют ИИ-систему как целое?"
    assert is_term_subset_question(question)
    assert not is_term_inventory_question(question)
    plan = plan_question(question, ["ГОСТ Р 71476—2024"])
    assert plan is not None
    assert plan.kind == "term_subset"


def test_no_plan_without_gost_or_term_marker():
    assert plan_question("Какие характеристики качества данных?", ["ГОСТ Р 71476—2024"]) is None
    assert plan_question("Что такое агент ИИ?", []) is None
    assert plan_question("Какие термины?", []) is None


def test_plan_does_not_trigger_for_other_questions():
    assert plan_question("Какие характеристики модели качества систем ИИ?", ["ГОСТ Р 71476—2024"]) is None
    assert plan_question("Какие требования определены в ГОСТ Р 71476—2024?", ["ГОСТ Р 71476—2024"]) is None
    assert plan_question("Что такое агент ИИ по ГОСТе Р 71476?", []) is None
