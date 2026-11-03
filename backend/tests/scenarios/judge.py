"""The LLM judge: scores Mia's side of a scenario call, plus simple counts done in code."""

import json
import re
from dataclasses import dataclass, field

from app.call.sentences import is_question, split_sentences
from app.providers.base import ChatMessage, LLMProvider, complete_text

from .model import Line, Scenario

SCORES = ("politeness", "brevity", "one_question")

_PROMPT = """You review phone calls handled by Mia, an AI receptionist at a demo clinic.
Score only Mia's lines, from 1 (poor) to 5 (excellent):
- politeness: warm, respectful, patient; never curt or robotic.
- brevity: each reply is 1-3 short sentences that suit being spoken aloud.
- one_question: each reply asks at most one question, then waits for the caller.
{checks_intro}
Reply with JSON only, no other text, in this shape:
{{"politeness": 1-5, "brevity": 1-5, "one_question": 1-5,
"checks": [{{"check": "<the check, copied>", "pass": true or false}}],
"notes": "<one short sentence on the biggest problem, or 'none'>"}}"""


@dataclass(frozen=True)
class StyleStats:
    """Counted in code, so the judge's scores can be sanity-checked."""

    replies: int
    max_sentences: int
    long_replies: int  # more than 3 sentences
    multi_question_replies: int


def style_stats(transcript: list[Line]) -> StyleStats:
    """Mia's replies after the greeting (the greeting is a fixed line)."""
    replies = [line.text for line in transcript if line.speaker == "mia"][1:]
    sentences = [split_sentences(text) for text in replies]
    return StyleStats(
        replies=len(replies),
        max_sentences=max((len(s) for s in sentences), default=0),
        long_replies=sum(1 for s in sentences if len(s) > 3),
        multi_question_replies=sum(1 for s in sentences if sum(map(is_question, s)) > 1),
    )


@dataclass
class Judgement:
    scores: dict[str, int]
    checks: list[tuple[str, bool]] = field(default_factory=list)
    notes: str = ""
    # Set when the judge's reply couldn't be read; scores are then empty.
    error: str = ""

    @property
    def checks_passed(self) -> int:
        return sum(1 for _, ok in self.checks if ok)


def judge_messages(scenario: Scenario, transcript: list[Line]) -> list[ChatMessage]:
    checks_intro = ""
    if scenario.judge_checks:
        listed = "\n".join(f"- {c}" for c in scenario.judge_checks)
        checks_intro = f"\nAlso answer each check below with true or false:\n{listed}\n"
    conversation = "\n".join(
        f"{'Mia' if line.speaker == 'mia' else 'Caller'}: {line.text}" for line in transcript
    )
    return [
        ChatMessage("system", _PROMPT.format(checks_intro=checks_intro)),
        ChatMessage("user", f"Scenario: {scenario.title}\n\nCall:\n{conversation}"),
    ]


_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def parse_judgement(raw: str, expected_checks: tuple[str, ...]) -> Judgement:
    """Read the judge's JSON. Scores are clamped to 1-5; checks it skipped count as failed."""
    match = _JSON_OBJECT.search(raw)
    try:
        data = json.loads(match.group(0)) if match else None
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict):
        return Judgement({}, [(c, False) for c in expected_checks], error="unreadable reply")
    scores: dict[str, int] = {}
    for name in SCORES:
        value = data.get(name)
        if isinstance(value, int | float) and not isinstance(value, bool):
            scores[name] = min(5, max(1, round(value)))
    answered = [
        (str(item.get("check", "")).strip().lower(), item["pass"])
        for item in data.get("checks") or []
        if isinstance(item, dict) and isinstance(item.get("pass"), bool)
    ]
    by_text = dict(answered)
    checks = []
    for i, check in enumerate(expected_checks):
        # Matched by text; if the judge reworded it, by position when the counts agree.
        ok = by_text.get(check.strip().lower())
        if ok is None and len(answered) == len(expected_checks):
            ok = answered[i][1]
        checks.append((check, bool(ok)))
    missing = [name for name in SCORES if name not in scores]
    return Judgement(
        scores,
        checks,
        notes=str(data.get("notes") or ""),
        error=f"missing {', '.join(missing)}" if missing else "",
    )


async def judge_call(llm: LLMProvider, scenario: Scenario, transcript: list[Line]) -> Judgement:
    raw = await complete_text(llm, judge_messages(scenario, transcript))
    return parse_judgement(raw, scenario.judge_checks)
