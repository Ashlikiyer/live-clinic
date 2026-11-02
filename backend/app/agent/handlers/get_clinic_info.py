import re

from app.agent.context import ToolContext, ToolResult
from app.agent.tools import GetClinicInfoArgs
from app.repositories.clinic import InfoEntry

_STOPWORDS = frozenset(
    "a an the is are do does you your i my me we to of for in on at and or what how when where "
    "can could will would there it this that".split()
)


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOPWORDS}


def rank_answers(entries: list[InfoEntry], topic: str, question: str) -> list[InfoEntry]:
    """Entries for the topic, best keyword match first; for 'other', only real matches."""
    wanted = _words(question)

    def score(e: InfoEntry) -> int:
        return len(wanted & _words(f"{e.question} {e.answer}"))

    if topic != "other":
        in_topic = [e for e in entries if e.topic == topic]
        if in_topic:
            return sorted(in_topic, key=score, reverse=True)[:2]
    matches = [e for e in entries if score(e) > 0]
    return sorted(matches, key=score, reverse=True)[:2]


async def handle(ctx: ToolContext, args: GetClinicInfoArgs) -> ToolResult:
    answers = rank_answers(await ctx.clinic.entries(), args.topic, args.question)
    if not answers:
        ctx.state.callback_notes.append(args.question)
        return ToolResult(
            {
                "found": False,
                "message": "Not in the clinic's information. Say you're not sure and that the "
                "staff will call them back about it (a callback note was saved).",
            }
        )
    return ToolResult({"found": True, "answers": [e.answer for e in answers]})
