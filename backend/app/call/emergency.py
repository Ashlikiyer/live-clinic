"""Emergency keyword check. Runs on every caller transcript before the LLM. Pure, no I/O.

It is deliberately broad: a false alarm costs one polite redirect, a miss could cost far more.
"""

import re

EMERGENCY_REPLY = (
    "That sounds like it could be an emergency. "
    "Please call 911 or go to the nearest emergency room right now. "
    "I'm going to end this call so you can get help. Please take care."
)

_PATTERNS: dict[str, list[str]] = {
    "chest_pain": [
        r"chest (pain|pains|tightness|pressure)",
        r"(pain|tightness|pressure) in (my|the|his|her) chest",
        r"heart attack",
    ],
    "breathing": [
        r"(can'?t|cannot|can not|unable to|hard to|trouble|difficulty|struggling to) breath",
        r"short(ness)? of breath",
        r"not breathing",
        r"choking",
        r"(throat|tongue) (is )?(closing|swelling)",
        r"anaphyla",
    ],
    "bleeding": [
        r"(severe|heavy|heavily|a lot of|lots of) bleed",
        r"bleeding (heavily|a lot|badly)",
        r"(won'?t|will not|doesn'?t|does not|can'?t) stop bleeding",
    ],
    "stroke": [
        r"\bstroke\b",
        r"face (is )?(drooping|droopy)",
        r"slurred speech|slurring",
        r"numb(ness)? on one side|one side .{0,20}(numb|weak)",
    ],
    "unresponsive": [
        r"unconscious|unresponsive|passed out|fainted|collapsed",
        r"seizure|convulsing",
        r"overdose|overdosed",
    ],
    "self_harm": [
        r"suicid",
        r"kill(ing)? my ?self|\bkill me\b",
        r"end (my life|it all)",
        r"(hurt|harm)(ing)? my ?self",
        r"self[- ]harm",
        r"want to die|don'?t want to (live|be alive)",
    ],
}

_COMPILED = {
    category: [re.compile(p, re.IGNORECASE) for p in patterns]
    for category, patterns in _PATTERNS.items()
}


def detect_emergency(text: str) -> str | None:
    """Return the emergency category the caller's words match, or None."""
    # STT sometimes returns a curly apostrophe (U+2019) in "can't" and "don't".
    normalized = " ".join(text.replace("\u2019", "'").split())
    for category, patterns in _COMPILED.items():
        if any(p.search(normalized) for p in patterns):
            return category
    return None
