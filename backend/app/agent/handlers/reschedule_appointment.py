from app.agent.confirmation import require_confirmation
from app.agent.context import ToolContext, ToolResult
from app.agent.handlers._common import describe
from app.agent.spoken import clinic_iso
from app.agent.tools import RescheduleAppointmentArgs
from app.core.clinic import CallOutcome
from app.scheduling.booking import Rejection


async def handle(ctx: ToolContext, args: RescheduleAppointmentArgs) -> ToolResult:
    if rejection := await require_confirmation(ctx, args.appointment_id, args.new_hold_id):
        return ToolResult.rejected(rejection)
    result = await ctx.repo.reschedule(
        ctx.session_id, args.appointment_id, args.new_hold_id, ctx.now()
    )
    if isinstance(result, Rejection):
        return ToolResult.rejected(result)
    ctx.state.outcome = CallOutcome.RESCHEDULED
    ctx.state.completed.add(CallOutcome.RESCHEDULED)
    moved = result.appointment
    doctors = await ctx.repo.doctors()
    return ToolResult(
        {"rescheduled": True, **describe(moved, doctors, ctx.tz)},
        [
            ("calendar.slot_released", {"id": result.released_hold_id}),
            (
                "calendar.slot_moved",
                {
                    "appointment_id": moved.id,
                    "from_start": clinic_iso(result.from_start, ctx.tz),
                    "to_start": clinic_iso(moved.start, ctx.tz),
                    "doctor_id": moved.doctor_id,
                },
            ),
        ],
    )
