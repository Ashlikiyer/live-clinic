import pytest

from app.call.emergency import detect_emergency


@pytest.mark.parametrize(
    ("text", "category"),
    [
        ("I have really bad chest pain right now", "chest_pain"),
        ("there's pressure in my chest", "chest_pain"),
        ("I can't breathe properly", "breathing"),
        ("my son is having trouble breathing", "breathing"),
        ("Her throat is swelling after eating peanuts", "breathing"),
        ("the cut won't stop bleeding", "bleeding"),
        ("my dad's face is drooping and his speech is slurred", "stroke"),
        ("my mom just collapsed", "unresponsive"),
        ("I've been thinking about killing myself", "self_harm"),
        ("I want to end my life", "self_harm"),
        ("I don\u2019t want to live anymore", "self_harm"),
    ],
)
def test_detects_emergencies(text: str, category: str) -> None:
    assert detect_emergency(text) == category


@pytest.mark.parametrize(
    "text",
    [
        "I'd like to book a check-up for my cough",
        "Can I end my appointment early?",
        "I cut myself shaving, it's fine now, can I get a tetanus shot?",
        "What time do you close?",
        "This cough is killing me, honestly",
    ],
)
def test_ignores_ordinary_requests(text: str) -> None:
    assert detect_emergency(text) is None
