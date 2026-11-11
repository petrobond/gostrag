from app.rag.generator import _parse_json


def test_parse_plain_json():
    assert _parse_json('{"answer": "ok"}')["answer"] == "ok"


def test_parse_markdown_json():
    assert _parse_json('```json\n{"refused": true}\n```')["refused"] is True


def test_parse_json_with_prefix():
    assert _parse_json('Ответ: {"confidence": 0.5} конец')["confidence"] == 0.5


def test_parse_invalid_returns_empty():
    assert _parse_json("не json") == {}
