"""Split streaming LLM text into speakable sentences. Pure, no I/O.

A sentence ends at ".", "?" or "!" followed by whitespace, except after abbreviations such as
"Dr." or "p.m.". A long clause (60+ characters) may also end at a comma, so the first audio
starts sooner. Whatever remains when the stream ends is flushed as the last sentence.
"""

import re

LONG_CLAUSE_CHARS = 60

# Words that end in "." but don't end a sentence (compared lowercase, without the final dot).
ABBREVIATIONS = frozenset(
    {"dr", "mr", "mrs", "ms", "st", "jr", "sr", "vs", "etc", "e.g", "i.e", "a.m", "p.m"}
)

# A sentence end is followed by whitespace, or directly by a capital letter: some models stream
# "Does that work?Great." with no space in between.
_END = re.compile(r"[.?!][.?!]*[\"')\]]*(?=\s|[A-Z])")
_COMMA = re.compile(r",(?=\s)")


def _is_abbreviation(text: str, dot_index: int) -> bool:
    if text[dot_index] != ".":
        return False
    start = dot_index
    while start > 0 and not text[start - 1].isspace():
        start -= 1
    word = text[start:dot_index].lower().lstrip("(\"'")
    if word in ABBREVIATIONS:
        return True
    # Single letters ("J. Cruz") and decimals ("2.5") are not sentence ends.
    return len(word) == 1 and word.isalpha()


def _next_boundary(text: str) -> int | None:
    """Index just past the first sentence boundary in `text`, if one is complete."""
    for match in _END.finditer(text):
        if not _is_abbreviation(text, match.start()):
            return match.end()
    if len(text) >= LONG_CLAUSE_CHARS:
        for match in _COMMA.finditer(text):
            if match.end() >= LONG_CLAUSE_CHARS:
                return match.end()
    return None


class SentenceSplitter:
    def __init__(self) -> None:
        self._buffer = ""

    def feed(self, delta: str) -> list[str]:
        """Add streamed text; return any sentences it completed."""
        self._buffer += delta
        sentences: list[str] = []
        while (end := _next_boundary(self._buffer)) is not None:
            sentence = self._buffer[:end].strip()
            self._buffer = self._buffer[end:]
            if sentence:
                sentences.append(sentence)
        return sentences

    def flush(self) -> str | None:
        """End of stream: return the remaining text as a final sentence."""
        rest = self._buffer.strip()
        self._buffer = ""
        return rest or None


def split_sentences(text: str) -> list[str]:
    """Split complete text in one go (used for fixed lines like the greeting)."""
    splitter = SentenceSplitter()
    sentences = splitter.feed(text)
    last = splitter.flush()
    return [*sentences, last] if last else sentences


def is_question(sentence: str) -> bool:
    # "Any allergies?..." is still a question.
    return sentence.rstrip("\"')] .").endswith("?")


class MetaTextFilter:
    """Drops [bracketed] text from a stream. Some models write "[Calling end_call]" as speech
    instead of calling the tool; it must never be spoken."""

    def __init__(self) -> None:
        self._depth = 0

    def feed(self, text: str) -> str:
        kept: list[str] = []
        for ch in text:
            if ch == "[":
                self._depth += 1
            elif ch == "]" and self._depth:
                self._depth -= 1
            elif not self._depth:
                kept.append(ch)
        return "".join(kept)
