from app.ingest.clean import (
    is_background,
    is_noise_text,
    is_red_stamp,
    is_service_text,
    normalize_text,
)
from app.ingest.extract import Span


def _span(text: str, *, size: float = 9.0, y: float = 124.0) -> Span:
    return Span(
        page=1,
        text=text,
        bbox=(100.0, y, 200.0, y + 13.0),
        color=0x231F20,
        size=size,
        font="Times",
        flags=0,
        block=0,
        line=0,
    )


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


def test_structural_digits_and_appendix_letters_are_kept():
    assert not is_noise_text("4", _span("4", size=12, y=278))
    assert not is_noise_text("5", _span("5", size=12, y=738))
    assert not is_noise_text("B", _span("B", size=9, y=124))
    assert not is_noise_text("C", _span("C", size=9, y=124))


def test_single_body_letter_is_still_noise():
    assert is_noise_text("я", _span("я", size=10, y=500))
    assert is_noise_text("B", _span("B", size=9, y=500))
