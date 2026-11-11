from app.rag.generator import _parse_json, _resolve_chunk

CHUNKS = [
    {
        "gost_number": "ГОСТ Р 72663—2026",
        "clause": "8.2",
        "clause_title": "Показатели качества прецизионности",
        "page": 17,
        "text": "Показатели Acc-I-1 и Acc-I-2",
    },
    {
        "gost_number": "ГОСТ Р 59926—2021",
        "clause": "Приложение A",
        "clause_title": "",
        "page": 50,
        "text": "Текст приложения",
    },
]


def test_parse_plain_json():
    assert _parse_json('{"answer": "ok"}')["answer"] == "ok"


def test_parse_markdown_json():
    assert _parse_json('```json\n{"refused": true}\n```')["refused"] is True


def test_parse_json_with_prefix():
    assert _parse_json('Ответ: {"confidence": 0.5} конец')["confidence"] == 0.5


def test_parse_invalid_returns_empty():
    assert _parse_json("не json") == {}


def test_resolve_clause_with_page_suffix():
    chunk = _resolve_chunk(CHUNKS, "ГОСТ Р 59926—2021", "Приложение A, страница 50", "")
    assert chunk is not None
    assert chunk["clause"] == "Приложение A"


def test_resolve_clause_number_with_prefix():
    chunk = _resolve_chunk(CHUNKS, "ГОСТ Р 72663-2026", "пункт 8.2, страница 17", "")
    assert chunk is not None
    assert chunk["clause"] == "8.2"


def test_resolve_by_quote():
    chunk = _resolve_chunk(CHUNKS, "ГОСТ Р 72663—2026", "таблица прецизионности", "Показатели Acc-I-1")
    assert chunk is not None
    assert chunk["clause"] == "8.2"


def test_resolve_unknown_returns_none():
    assert _resolve_chunk(CHUNKS, "ГОСТ Р 1—2000", "1.1", "") is None
