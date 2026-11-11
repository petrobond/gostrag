from app.ingest.clean import is_background, is_red_stamp, is_service_text, normalize_text


def test_normalize_collapses_spaced_letters():
    assert normalize_text("П р и м е ч а н и е — текст") == "Примечание — текст"


def test_normalize_keeps_soft_hyphen_for_join():
    assert "\u00ad" in normalize_text("ру\u00ad ководящие")


def test_background_detection():
    assert is_background(0xBFBFBF)
    assert is_background(0xCCCCC9)
    assert not is_background(0x231F20)


def test_red_stamp_detection():
    assert is_red_stamp(0xFF0000)
    assert not is_red_stamp(0x231F20)


def test_service_text_detection():
    assert is_service_text("ФГБУ «Институт стандартизации» – Федеральный информационный фонд")
    assert is_service_text("Федеральное агентство по техническому регулированию и метрологии")
    assert not is_service_text("Настоящий стандарт устанавливает требования")
