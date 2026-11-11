from app.ingest.chunk import MAX_CHARS, _split_long


def test_short_text_is_not_split():
    assert _split_long("короткий текст") == ["короткий текст"]


def test_long_text_is_split_under_limit():
    text = "Это предложение. " * 500
    parts = _split_long(text)
    assert len(parts) > 1
    assert all(len(part) <= MAX_CHARS for part in parts)


def test_semicolon_list_is_split():
    text = "; ".join([f"аббревиатура номер {i}" for i in range(200)])
    parts = _split_long(text)
    assert all(len(part) <= MAX_CHARS for part in parts)
