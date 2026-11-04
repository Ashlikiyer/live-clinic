from app.agent.confirmation import require_confirmation
from app.agent.context import ToolContext, ToolResult
from app.agent.tools import CancelAppointmentArgs
from app.core.clinic import CallOutcome
from app.scheduling.booking import Rejection


async def handle(ctx: ToolContext, args: CancelAppointmentArgs) -> ToolResult:
    if rejection := await require_confirmation(ctx, args.appointment_id):
        return ToolResult.rejected(rejection)
    result = await ctx.repo.cancel(ctx.session_id, args.appointment_id, ctx.now())
    if isinstance(result, Rejection):
        return ToolResult.rejected(result)
    ctx.state.outcome = CallOutcome.CANCELLED
    ctx.state.completed.add(CallOutcome.CANCELLED)
    return ToolResult(
        {"cancelled": True, "message": "Cancelled. Offer to book a new time."},
        [("calendar.slot_cancelled", {"id": result.id})],
    )
