import pytest

from app.call.emergency import (
    EMERGENCY_REPLY,
    EMERGENCY_REPLY_TL,
    detect_emergency,
    emergency_reply,
    looks_tagalog,
)


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
def test_detects_emergencies_in_english(text: str, category: str) -> None:
    assert detect_emergency(text) == category


@pytest.mark.parametrize(
    ("text", "category"),
    [
        ("Masakit ang dibdib ko ngayon", "chest_pain"),
        ("Gusto ko sanang mag-book, kasi sumasakit yung dibdib ko kanina pa", "chest_pain"),
        ("Naninikip ang dibdib ng tatay ko", "chest_pain"),
        ("Parang inaatake sa puso si lola", "chest_pain"),
        ("Hindi ako makahinga", "breathing"),
        ("Nahihirapan siyang huminga", "breathing"),
        ("Kinakapos ako ng hininga", "breathing"),
        ("Nabulunan yung anak ko", "breathing"),
        ("Dumudugo nang malakas yung sugat", "bleeding"),
        ("Hindi tumitigil ang pagdurugo", "bleeding"),
        ("Tabingi ang mukha ni mama at bulol magsalita", "stroke"),
        ("Na-stroke yata si lolo", "stroke"),
        ("Nahimatay si papa", "unresponsive"),
        ("Nawalan siya ng malay", "unresponsive"),
        ("Nangingisay yung baby ko", "unresponsive"),
        ("Gusto ko nang magpakamatay", "self_harm"),
        ("Ayoko nang mabuhay", "self_harm"),
    ],
)
def test_detects_emergencies_in_tagalog_and_taglish(text: str, category: str) -> None:
    assert detect_emergency(text) == category


@pytest.mark.parametrize(
    "text",
    [
        "I'd like to book a check-up for my cough",
        "Can I end my appointment early?",
        "I cut myself shaving, it's fine now, can I get a tetanus shot?",
        "What time do you close?",
        "This cough is killing me, honestly",
        "Gusto ko pong mag-book ng check-up para sa ubo ko",
        "Ano po ang oras ninyo sa Sabado?",
        "May lagnat po yung anak ko since kahapon",
        "Sige po, salamat. Bye!",
        "Masakit ang ulo ko, pwede ba akong magpa-consult bukas?",
    ],
)
def test_ignores_ordinary_requests(text: str) -> None:
    assert detect_emergency(text) is None


@pytest.mark.parametrize(
    ("text", "tagalog"),
    [
        ("Masakit ang dibdib ko ngayon", True),
        ("Hindi po ako makahinga", True),
        ("My chest hurts a lot", False),
        ("I have chest pain, can I book a check-up?", False),
        ("Si lola, parang na-stroke", True),
    ],
)
def test_looks_tagalog(text: str, tagalog: bool) -> None:
    assert looks_tagalog(text) is tagalog


def test_the_emergency_advice_is_given_in_the_callers_language() -> None:
    assert emergency_reply("Masakit ang dibdib ko") == EMERGENCY_REPLY_TL
    assert emergency_reply("I have chest pain") == EMERGENCY_REPLY
    assert "911" in EMERGENCY_REPLY_TL
