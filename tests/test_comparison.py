from app.rag.generator import Answer
from app.rag.retriever import RetrievedChunk
from app.rag.service import AskService


def make_chunk(gost: str, clause: str, title: str, text: str, page: int) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"doc#{clause}",
        text=text,
        gost_number=gost,
        clause=clause,
        section="",
        section_title=title,
        page=page,
        score=1.0,
        doc_id="doc",
        clause_title=title,
    )


def test_comparison_fact_card_is_deterministic_and_attributed():
    quant = make_chunk(
        "ГОСТ Р 71484.2—2024",
        "5.2",
        "Модель качества данных",
        "Стандарт [2] предоставляет пятнадцать характеристик качества данных: "
        "аккуратность, наполненность, согласованность.",
        10,
    )
    extra = make_chunk(
        "ГОСТ Р 71484.2—2024",
        "8.1",
        "Структура отчетности",
        "Отчеты содержат модели качества данных, показатели качества данных "
        "и результаты их измерений.",
        30,
    )
    indicator = make_chunk(
        "ГОСТ Р 72663—2026",
        "8.1",
        "Общие положения",
        "Стандарт предоставляет базовый набор показателей качества (ПК) данных, "
        "генерируемых функцией измерения, применяемой к элементам измерения качества.",
        16,
    )
    answer = Answer(answer="Ответ LLM")
    AskService._append_comparison_facts(
        answer,
        [quant, extra, indicator],
        ["ГОСТ Р 71484.2—2024", "ГОСТ Р 72663—2026"],
    )
    assert answer.model == "deterministic:comparison"
    assert "ГОСТ Р 71484.2—2024 — модель качества данных и 15 характеристик" in answer.answer
    assert "ГОСТ Р 72663—2026 — измеримые показатели (ПК)" in answer.answer
    assert "ГОСТ Р 72663—2026 — модель качества данных" not in answer.answer
    assert len(answer.citations) == 2
