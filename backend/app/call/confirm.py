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
    # More Tagalog: "tama" (right), "ayos" (fine), "pwede" (that works), "tuloy" (go ahead).
    "tama",
    "tama po",
    "ayos",
    "ayos lang",
    "pwede",
    "pwede po",
    "tuloy",
    "ituloy",
    "ituloy mo",
    "i-book mo na",
    "book mo na",
    "kumpirmado",
)

# Anything that signals doubt, refusal or a change of plan.
_NO_WORDS = re.compile(
    # Not "cancel": confirming a cancellation ("yes, cancel it") is a yes.
    r"\b(no|nope|nah|not|don'?t|wait|hold on|actually|instead|change|different|"
    r"other|another|but|hindi|wag|huwag|"
    # Tagalog doubt: ayoko/ayaw (don't want), teka/sandali (wait), pero (but), iba (another),
    # palitan (change), mamaya (later).
    r"ayoko|ayaw|teka|sandali|pero|iba|palitan|mamaya)\b"
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
    r"i'?m good|i'?m done|all set|have a (good|nice) (day|one)|salamat|"
    # Tagalog: paalam (goodbye), "yun lang" / "wala na" (that's all), "ok na ako" (I'm good).
    r"paalam|yun lang|iyon lang|wala na|ok na ako|okay na ako|ayos na)\b"
)


def sounds_like_goodbye(text: str) -> bool:
    """Did the caller signal they're finished? Guards end_call against hanging up early."""
    return bool(_CLOSING.search(_normalize(text)))


_PERSON = (
    r"(a |an |the |some |)(real |live |actual |)"
    r"(person|human|someone|somebody|staff|agent|representative|receptionist|manager|"
    r"operator|doctor|nurse|billing|front desk)"
)
# Tagalog: "kausapin ang tao/staff", "may totoong tao ba", "ipasa mo ako", "ikonek mo ako".
_TAO = r"(tao|staff|doktor|doctor|nurse|receptionist|billing|manager)"
_WANTS_PERSON = re.compile(
    rf"\b((speak|talk|chat) (to|with) {_PERSON}|transfer|connect me|put me through|"
    rf"real person|human|operator|"
    rf"(kausapin|makausap|kakausapin) (ang |si |yung |ng |isang |)(totoong |)?{_TAO}|"
    rf"totoong tao|may tao ba|ipasa mo|ikonek mo|i-connect mo|ilipat mo)"
)


def asks_for_a_person(text: str) -> bool:
    """Did the caller ask for a person (or to be transferred)? Pure."""
    return bool(_WANTS_PERSON.search(_normalize(text)))


def transfer_allowed(text: str) -> bool:
    """A transfer ends the call, so it needs the caller's say-so: they asked for a person, or
    they clearly said yes (to a transfer Mia offered). Guards against a model hanging up on a
    caller mid-booking with a made-up transfer."""
    return asks_for_a_person(text) or classify_confirmation(text) == "yes"
