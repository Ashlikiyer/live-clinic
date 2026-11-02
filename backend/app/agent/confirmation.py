"""The code-level gate for booking changes (not just a prompt rule).

A change is allowed only if (1) what is being changed was presented to the caller in an earlier
turn, so the read-back happened, and (2) the caller's latest turn is a clear yes: the rule list
in call/confirm.py first, then a one-word LLM check when the rules can't tell.
"""

from app.agent.context import ToolContext
from app.call.confirm import CONFIRM_CHECK_PROMPT, classify_confirmation
from app.providers.base import ChatMessage, ProviderError, complete_text
from app.scheduling.booking import Rejection

NEEDS_READBACK = Rejection(
    "NEEDS_READBACK",
    "Not done yet. Read back the doctor, day, date and time, ask the caller to confirm, then "
    "stop and wait for their answer.",
)
NEEDS_CONFIRMATION = Rejection(
    "NEEDS_CONFIRMATION",
    "Not done: the caller hasn't clearly said yes. Ask the caller to confirm first, then wait.",
)


async def _llm_says_yes(ctx: ToolContext) -> bool:
    if ctx.turn_id in ctx.state.confirm_checks:
        return ctx.state.confirm_checks[ctx.turn_id]
    try:
        answer = await complete_text(
            ctx.llm,
            [
                ChatMessage("system", CONFIRM_CHECK_PROMPT),
                ChatMessage("user", f"Caller's reply: {ctx.last_user_text!r}"),
            ],
        )
    except ProviderError:
        answer = ""
    verdict = answer.strip().upper().startswith("YES")
    ctx.state.confirm_checks[ctx.turn_id] = verdict
    return verdict


async def require_confirmation(ctx: ToolContext, *item_ids: str) -> Rejection | None:
    for item_id in item_ids:
        presented = ctx.state.presented.get(item_id)
        if presented is None or presented >= ctx.turn_id:
            return NEEDS_READBACK
    verdict = classify_confirmation(ctx.last_user_text)
    if verdict == "yes":
        return None
    if verdict == "unclear" and await _llm_says_yes(ctx):
        return None
    return NEEDS_CONFIRMATION
