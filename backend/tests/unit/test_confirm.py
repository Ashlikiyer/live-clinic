import pytest

from app.call.confirm import (
    asks_for_a_person,
    classify_confirmation,
    sounds_like_goodbye,
    transfer_allowed,
)


@pytest.mark.parametrize(
    "text",
    [
        "yes",
        "Yes.",
        "yeah sure",
        "that works",
        "Oo",
        "Yes please, go ahead.",
        "Sounds good!",
        "That's correct",
        "Sige",
        "Yes, cancel it",
        "Please move it",
    ],
)
def test_clear_yes(text: str) -> None:
    assert classify_confirmation(text) == "yes"


@pytest.mark.parametrize(
    "text",
    [
        "wait",
        "what time?",
        "no",
        "Nope.",
        "Actually, can we do the afternoon?",
        "Yes, but make it 3 PM instead",
        "I don't think so",
        "Hold on, let me check",
        "Is that with Dr. Reyes?",
        "No, cancel it",
    ],
)
def test_not_a_yes(text: str) -> None:
    assert classify_confirmation(text) == "no"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "hmm",
        "my birthday is March 3",
        "I guess I would like that appointment slot then maybe yes",
    ],
)
def test_unclear_goes_to_the_llm_check(text: str) -> None:
    assert classify_confirmation(text) == "unclear"


@pytest.mark.parametrize(
    ("text", "done"),
    [
        ("Thanks, that's all.", True),
        ("No, I'm good. Bye!", True),
        ("Nothing else, salamat", True),
        ("Yes, please.", False),
        ("Maybe Thursday instead?", False),
        ("Okay, thank you", False),
    ],
)
def test_goodbye_detection(text: str, done: bool) -> None:
    assert sounds_like_goodbye(text) is done


@pytest.mark.parametrize(
    ("text", "asks"),
    [
        ("Can I speak to someone in billing?", True),
        ("I want to talk to a real person", True),
        ("Please transfer me.", True),
        ("Is there a human I can talk to?", True),
        ("Can you connect me to the front desk?", True),
        ("March 3, 1990.", False),
        ("I'd like to book a consult for a cough.", False),
        ("Can I speak Tagalog?", False),
    ],
)
def test_asks_for_a_person(text: str, asks: bool) -> None:
    assert asks_for_a_person(text) is asks


def test_transfer_needs_a_request_or_a_clear_yes() -> None:
    assert transfer_allowed("Yes, please transfer me.")
    assert transfer_allowed("Yes please")  # answering Mia's transfer offer
    assert not transfer_allowed("March 3, 1990.")
    assert not transfer_allowed("No, I'll call back later.")
