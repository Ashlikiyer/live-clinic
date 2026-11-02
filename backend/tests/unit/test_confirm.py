import pytest

from app.call.confirm import classify_confirmation, sounds_like_goodbye


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
