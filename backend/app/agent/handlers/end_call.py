from typing import Any

from app.agent.context import EndRequest, ToolContext, ToolResult
from app.agent.tools import EndCallArgs
from app.call.confirm import sounds_like_goodbye
from app.scheduling.booking import Rejection

NOT_DONE = Rejection(
    "CALLER_NOT_DONE",
    "Don't end the call yet. Ask if there's anything else, then wait for the caller.",
)


async def handle(ctx: ToolContext, args: EndCallArgs) -> ToolResult:
    # Transfers and emergencies end the call on the agent's call; a normal goodbye needs the
    # caller to have said they're done, so the agent can't hang up on them mid-conversation.
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
