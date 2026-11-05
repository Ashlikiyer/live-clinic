"""Rules for server-side speech (Groq Orpheus). Pure, no I/O.

The browser asks the server to speak a line, so the server must check the line is Mia's own:
otherwise the call socket would be a free text-to-speech service for anyone with a session.
"""

from collections.abc import Iterable

# Speech requests one call may make. A long call is ~20 replies plus a few fixed lines; the
# Groq free tier allows 100 a day, so this mostly stops a runaway client.
MAX_SPEECH_REQUESTS_PER_CALL = 40


def _squash(text: str) -> str:
    return " ".join(text.split())


def speech_allowed(text: str, said: Iterable[str], fixed_lines: Iterable[str]) -> bool:
    """`text` is a fixed line, or part of something Mia already said in this call."""
    wanted = _squash(text)
    if not wanted:
        return False
    if wanted in {_squash(line) for line in fixed_lines}:
        return True
    return any(wanted in _squash(reply) for reply in said)
