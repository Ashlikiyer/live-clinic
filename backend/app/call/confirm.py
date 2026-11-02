"""Is the caller's latest turn a clear "yes"? Booking changes are refused unless it is.

`classify_confirmation` is the fast rule list (pure). When it can't decide, the tool handler
asks the LLM a one-word yes/no question instead.
"""

import re
from typing import Literal

Confirmation = Literal["yes", "no", "unclear"]

# Short, unambiguous agreement. "oo" is Filipino for yes.
_YES_PHRASES = (
    "yes",
    "yeah",
    "yep",
    "yup",
    "yes please",
    "sure",
    "of course",
    "okay",
    "ok",
    "that works",
    "works for me",
    "correct",
    "that's correct",
    "that's right",
    "right",
    "go ahead",
    "please do",
    "do it",
    "confirm",
    "confirm it",
    "book it",
    "cancel it",
    "move it",
    "sounds good",
    "perfect",
    "great",
    "oo",
    "opo",
    "sige",
)

# Anything that signals doubt, refusal or a change of plan.
_NO_WORDS = re.compile(
    # Not "cancel": confirming a cancellation ("yes, cancel it") is a yes.
    r"\b(no|nope|nah|not|don'?t|wait|hold on|actually|instead|change|different|"
    r"other|another|but|hindi|wag|huwag)\b"
)

_MAX_WORDS = 10


def _normalize(text: str) -> str:
    text = text.lower().replace("\u2019", "'")  # curly apostrophe from STT
    return " ".join(re.sub(r"[^\w\s'?]", " ", text).split())


def classify_confirmation(text: str) -> Confirmation:
    normalized = _normalize(text)
    if not normalized:
        return "unclear"
    if _NO_WORDS.search(normalized):
        return "no"
    if "?" in normalized:
        # A question back ("what time?") is never a confirmation.
        return "no"
    words = normalized.split()
    if len(words) > _MAX_WORDS:
        return "unclear"
    phrase = " ".join(words)
    padded = f" {phrase} "
    if any(f" {yes} " in padded for yes in _YES_PHRASES):
        return "yes"
    return "unclear"


CONFIRM_CHECK_PROMPT = (
    "You check phone call transcripts. The receptionist just read back an appointment change "
    "and asked the caller to confirm. Reply with exactly one word: YES if the caller's reply "
    "clearly agrees to go ahead, otherwise NO."
)


_CLOSING = re.compile(
    r"\b(bye|goodbye|that'?s all|that is all|that'?s it|nothing else|no thanks|no thank you|"
    r"i'?m good|i'?m done|all set|have a (good|nice) (day|one)|salamat)\b"
)


def sounds_like_goodbye(text: str) -> bool:
    """Did the caller signal they're finished? Guards end_call against hanging up early."""
    return bool(_CLOSING.search(_normalize(text)))
