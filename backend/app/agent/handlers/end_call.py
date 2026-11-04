from typing import Any

from app.agent.context import EndRequest, ToolContext, ToolResult
from app.agent.tools import EndCallArgs
from app.call.confirm import sounds_like_goodbye, transfer_allowed
from app.core.clinic import CallOutcome
from app.scheduling.booking import Rejection

NOT_DONE = Rejection(
    "CALLER_NOT_DONE",
    "Don't end the call yet. Ask if there's anything else, then wait for the caller.",
)


NO_TRANSFER_REQUEST = Rejection(
    "TRANSFER_NOT_REQUESTED",
    "Don't transfer unless the caller asks for a person or says yes to your offer. "
    "Keep helping them, or offer a transfer and wait for their answer.",
)


# Outcomes that claim a booking change: only allowed once that change has succeeded.
CHANGE_OUTCOMES = {CallOutcome.BOOKED, CallOutcome.RESCHEDULED, CallOutcome.CANCELLED}


def outcome_not_done(outcome: str) -> Rejection:
    return Rejection(
        "OUTCOME_NOT_DONE",
        f"Nothing was {outcome} in this call. Finish it with the booking tools first "
        "(hold_slot, then confirm_booking after the caller's yes), or tell the caller it "
        "isn't done.",
    )


async def handle(ctx: ToolContext, args: EndCallArgs) -> ToolResult:
    # A transfer needs the caller's say-so; an emergency ends on the agent's call; a normal
    # goodbye needs the caller to have said they're done. The agent can't hang up on a caller
    # mid-conversation.
    if args.transfer and not transfer_allowed(ctx.last_user_text):
        return ToolResult.rejected(NO_TRANSFER_REQUEST)
    if args.outcome in CHANGE_OUTCOMES and args.outcome not in ctx.state.completed:
        return ToolResult.rejected(outcome_not_done(args.outcome))
    closing = args.transfer or args.outcome == "emergency_advised"
    if not closing and not sounds_like_goodbye(ctx.last_user_text):
        return ToolResult.rejected(NOT_DONE)
    outcome = "transferred" if args.transfer else args.outcome
    ctx.state.end_request = EndRequest(outcome, args.summary, args.transfer)
    events: list[tuple[str, dict[str, Any]]] = []
    if args.transfer:
        events.append(("call.transferring", {"reason": args.summary}))
    return ToolResult(
        {"ending": True, "message": "Say a brief goodbye now; the call ends after it."}, events
    )
