"""Emergency keyword check. Runs on every caller transcript before the LLM. Pure, no I/O.

It is deliberately broad: a false alarm costs one polite redirect, a miss could cost far more.
"""

import re

EMERGENCY_REPLY = (
    "That sounds like it could be an emergency. "
    "Please call 911 or go to the nearest emergency room right now. "
    "I'm going to end this call so you can get help. Please take care."
)
# The same, for a caller speaking Tagalog or Taglish.
EMERGENCY_REPLY_TL = (
    "Mukhang emergency po ito. "
    "Tumawag po kayo sa 911 o pumunta agad sa pinakamalapit na emergency room. "
    "Tatapusin ko na po ang tawag para makahingi kayo ng tulong. Mag-ingat po kayo."
)

# Everyday Tagalog words that rarely appear in English sentences.
_TAGALOG_WORDS = frozenset(
    "ang ng mga ko po opo ako siya kami tayo kayo sila yung iyong ito ay sa si ni hindi "
    "wala may meron na pa ba lang naman kasi pero para gusto ngayon kanina yata".split()
)


def looks_tagalog(text: str) -> bool:
    """Is the caller speaking Tagalog or Taglish? Two everyday Tagalog words are enough."""
    words = re.findall(r"[a-z']+", text.lower())
    return sum(1 for word in words if word in _TAGALOG_WORDS) >= 2


def emergency_reply(text: str) -> str:
    """The emergency advice in the caller's language."""
    return EMERGENCY_REPLY_TL if looks_tagalog(text) else EMERGENCY_REPLY


_PATTERNS: dict[str, list[str]] = {
    "chest_pain": [
        r"chest (pain|pains|tightness|pressure)",
        r"(pain|tightness|pressure) in (my|the|his|her) chest",
        r"heart attack",
        # Tagalog / Taglish: "masakit ang dibdib ko", "naninikip ang dibdib", "inaatake sa puso"
        r"(masakit|sumasakit|kumikirot|naninikip|paninikip|sakit)\b.{0,20}\bdibdib",
        r"\bdibdib\b.{0,20}(masakit|sumasakit|kumikirot|naninikip|sakit)",
        r"(atake|inaatake|inatake) sa puso",
    ],
    "breathing": [
        r"(can'?t|cannot|can not|unable to|hard to|trouble|difficulty|struggling to) breath",
        r"short(ness)? of breath",
        r"not breathing",
        r"choking",
        r"(throat|tongue) (is )?(closing|swelling)",
        r"anaphyla",
        # "hindi ako makahinga", "hirap huminga", "kinakapos ng hininga"
        r"\b(hindi|di|hirap|nahihirapan\w*|kinakapos)\s+(\w+\s+){0,2}(makahinga|huminga|hininga)",
        r"nabubulunan|nabulunan",
        r"namamaga (ang |yung )?(lalamunan|dila)",
    ],
    "bleeding": [
        r"(severe|heavy|heavily|a lot of|lots of) bleed",
        r"bleeding (heavily|a lot|badly)",
        r"(won'?t|will not|doesn'?t|does not|can'?t) stop bleeding",
        # "dumudugo nang malakas", "hindi tumitigil ang pagdurugo", "malakas na pagdurugo"
        r"dumudugo\s+(nang|ng)\s+(malakas|husto|sobra)",
        r"(hindi|ayaw|di)\s+(\w+\s+){0,2}(tumitigil|tumigil|huminto)\b.{0,20}\b(dugo|pagdurugo|pagdugo)",
        r"(malakas|matinding|sobrang)\s+(na\s+)?(pagdurugo|pagdugo)",
    ],
    "stroke": [
        r"\bstroke\b",
        r"face (is )?(drooping|droopy)",
        r"slurred speech|slurring",
        r"numb(ness)? on one side|one side .{0,20}(numb|weak)",
        # "na-stroke", "tabingi ang mukha", "bulol magsalita", "manhid ang kalahati ng katawan"
        r"na-?stroke|istrok",
        r"(tabingi|lumalaylay|nakalaylay|bumagsak) (ang |yung )?(mukha|bibig)",
        r"bulol (na )?(magsalita|siya|ako)|biglang (hindi|di) (makapagsalita|makapag-salita)",
        r"manhid (ang |yung )?(kalahati|isang (bahagi|side|gilid))",
    ],
    "unresponsive": [
        r"unconscious|unresponsive|passed out|fainted|collapsed",
        r"seizure|convulsing",
        r"overdose|overdosed",
        # "nahimatay", "nawalan ng malay", "hindi magising", "nangingisay", "kinukumbulsyon"
        r"nahimatay|hinimatay|nawalan (siya |ako )?ng malay|walang malay",
        r"(hindi|ayaw|di) (siya )?magising",
        r"nangingisay|nangisay|kinukumbulsyon|kumbulsyon",
        r"na-?overdose",
    ],
    "self_harm": [
        r"suicid",
        r"kill(ing)? my ?self|\bkill me\b",
        r"end (my life|it all)",
        r"(hurt|harm)(ing)? my ?self",
        r"self[- ]harm",
        r"want to die|don'?t want to (live|be alive)",
        # "magpakamatay", "patayin ang sarili ko", "ayoko nang mabuhay", "gusto ko nang mamatay"
        r"magpakamatay|nagpakamatay|pagpapakamatay",
        r"(patayin|papatayin|saktan|sasaktan) (ko )?(ang |yung )?sarili",
        r"ayoko? (na|nang) mabuhay|gusto ko (na|nang) mamatay",
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
