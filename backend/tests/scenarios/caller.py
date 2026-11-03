"""The simulated caller: an LLM with a persona and a goal, talking to Mia in text."""

import re
from dataclasses import dataclass

from app.providers.base import ChatMessage, LLMProvider, complete_text
from app.schemas.events import MAX_TYPED_CHARS

from .model import Facts, Line, Scenario

HANGUP = "[HANGUP]"

_PROMPT = """You are role-playing a person phoning Bayview Family Clinic, a demo clinic. You
are talking to Mia, the clinic's receptionist. Her lines are the user messages; you write only
your own next line as the caller.

Who you are: {persona}
Your goal: {goal}

How to talk:
- Sound like a real person on the phone: one or two short sentences, plain spoken words.
- Answer what Mia asks. Give details only when she asks for them, one or two at a time.
- Write only your one next line, then stop. Never continue the call past it, never write
  Mia's lines, and no stage directions, labels like "Caller:", quotes or lists.
- If Mia says something wrong or unclear, say so naturally, as a real caller would.
- When your goal is done, or clearly can't be done, say a short goodbye ("That's all,
  thanks. Bye!").
- If Mia has already said goodbye and there's nothing left to say, reply with exactly
  {hangup}"""


def caller_system_prompt(scenario: Scenario, facts: Facts) -> str:
    return _PROMPT.format(
        persona=scenario.persona.format(**facts),
        goal=scenario.goal.format(**facts),
        hangup=HANGUP,
    )


def caller_messages(system: str, transcript: list[Line]) -> list[ChatMessage]:
    """Mia's lines are the "user" side of the caller's conversation, its own the "assistant"."""
    messages = [ChatMessage("system", system)]
    messages += [
        ChatMessage("user" if line.speaker == "mia" else "assistant", line.text)
        for line in transcript
    ]
    return messages


@dataclass(frozen=True)
class CallerLine:
    text: str
    hangup: bool
    note: str = ""


# A model sometimes writes several future turns back to back with no space between them
# ("Yes, that's right.The next slot is 3 PM."). Only the first one is the caller's line.
_GLUED_TURN = re.compile(r"(?<=[.!?])(?=[A-Z0-9\u2018\u201c\"'])")
_LABEL = re.compile(r"^\s*(caller|me|you|patient)\s*:\s*", re.IGNORECASE)
_DIRECTION = re.compile(r"\*[^*]*\*|\([^)]*\)")


def clean_caller_line(raw: str) -> CallerLine:
    """Strip what a model adds around a spoken line; spot the hang-up marker."""
    text = _GLUED_TURN.split(raw.strip(), maxsplit=1)[0]
    hangup = HANGUP in text
    text = text.replace(HANGUP, "")
    text = _DIRECTION.sub("", _LABEL.sub("", text))
    text = " ".join(text.split()).strip().strip('"').strip()
    if len(text) > MAX_TYPED_CHARS:
        text = text[:MAX_TYPED_CHARS].rsplit(" ", 1)[0]
    return CallerLine(text, hangup)


# The caller model sometimes returns nothing (its reasoning used the whole reply); ask again.
EMPTY_RETRIES = 3


async def caller_reply(llm: LLMProvider, system: str, transcript: list[Line]) -> CallerLine:
    line = CallerLine("", False)
    for _ in range(EMPTY_RETRIES):
        line = clean_caller_line(await complete_text(llm, caller_messages(system, transcript)))
        if line.text or line.hangup:
            return line
    # Nothing usable after several tries: hang up, and say why in the transcript log.
    return CallerLine("", True, note=f"empty caller reply x{EMPTY_RETRIES}")
