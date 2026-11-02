import pytest

from app.call.sentences import MetaTextFilter, SentenceSplitter, is_question, split_sentences


def stream(text: str, chunk: int = 3) -> list[str]:
    """Feed text in small chunks, like an LLM stream, and collect sentences."""
    splitter = SentenceSplitter()
    out: list[str] = []
    for i in range(0, len(text), chunk):
        out.extend(splitter.feed(text[i : i + chunk]))
    last = splitter.flush()
    return [*out, last] if last else out


def test_splits_on_sentence_ends() -> None:
    assert stream("Sure. What day works? Great!") == ["Sure.", "What day works?", "Great!"]


def test_never_splits_doctor_or_pm() -> None:
    text = "Dr. Reyes is free at 2:30 p.m. tomorrow. Shall I hold it?"
    assert stream(text) == ["Dr. Reyes is free at 2:30 p.m. tomorrow.", "Shall I hold it?"]


@pytest.mark.parametrize("text", ["It costs 1.5 thousand pesos.", "Ask for Ana B. Reyes."])
def test_decimals_and_initials_stay_together(text: str) -> None:
    assert stream(text) == [text]


def test_long_clause_splits_at_comma_after_60_chars() -> None:
    text = (
        "I have Tuesday at nine thirty in the morning with Dr. Ana Reyes, "
        "or Wednesday at two in the afternoon."
    )
    first, second = stream(text)
    assert first.endswith("Reyes,") and len(first) >= 60
    assert second == "or Wednesday at two in the afternoon."


def test_short_comma_does_not_split() -> None:
    assert stream("Okay, one moment.") == ["Okay, one moment."]


def test_short_answer_no_is_a_sentence() -> None:
    assert stream("No. That's fine.") == ["No.", "That's fine."]


def test_sentence_is_emitted_as_soon_as_whitespace_follows() -> None:
    splitter = SentenceSplitter()
    assert splitter.feed("Hello there.") == []
    assert splitter.feed(" How") == ["Hello there."]
    assert splitter.flush() == "How"


def test_flush_on_empty_stream() -> None:
    assert SentenceSplitter().flush() is None
    assert split_sentences("") == []


def test_splits_when_a_model_forgets_the_space() -> None:
    assert stream("Does that work for you?Sure. Booked.") == [
        "Does that work for you?",
        "Sure.",
        "Booked.",
    ]
    assert stream("Any allergies?... I see.") == ["Any allergies?...", "I see."]
    # ...but not inside abbreviations.
    assert stream("See Dr.Reyes at 9 a.m.Thanks!") == ["See Dr.Reyes at 9 a.m.Thanks!"]


def test_meta_text_filter_drops_bracketed_text_across_chunks() -> None:
    f = MetaTextFilter()
    parts = [f.feed(p) for p in ["Goodbye! [Call", "ing end_", "call] Take care."]]
    assert "".join(parts) == "Goodbye!  Take care."


def test_is_question() -> None:
    assert is_question("Shall I book it?")
    assert is_question("Any allergies?...")
    assert is_question('Did you say "Tuesday?"')
    assert not is_question("Booked.")
