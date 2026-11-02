from datetime import timedelta
from typing import Any

from app.agent.context import ToolContext, ToolResult
from app.agent.handlers._common import describe
from app.agent.spoken import clinic_iso
from app.agent.tools import HoldSlotArgs
from app.core.clinic import VisitType
from app.scheduling.availability import visit_minutes
from app.scheduling.booking import Rejection


async def handle(ctx: ToolContext, args: HoldSlotArgs) -> ToolResult:
    start = args.slot_start if args.slot_start.tzinfo else args.slot_start.replace(tzinfo=ctx.tz)
    visit_type = VisitType(args.visit_type)
    result = await ctx.repo.hold(
        ctx.session_id,
        doctor_id=args.doctor_id,
        start=start,
        end=start + timedelta(minutes=visit_minutes(visit_type)),
        visit_type=visit_type,
        now=ctx.now(),
    )
    if isinstance(result, Rejection):
        return ToolResult.rejected(result)
    hold, released = result
    ctx.state.presented[hold.id] = ctx.turn_id
    doctors = await ctx.repo.doctors()
    expires = hold.hold_expires_at or ctx.now()
    events: list[tuple[str, dict[str, Any]]] = [
        ("calendar.slot_released", {"id": hold_id}) for hold_id in released
    ]
    events.append(
        (
            "calendar.slot_holding",
            {
                "hold_id": hold.id,
                "start": clinic_iso(hold.start, ctx.tz),
                "end": clinic_iso(hold.end, ctx.tz),
                "doctor_id": hold.doctor_id,
                "expires_at": clinic_iso(expires, ctx.tz),
            },
        )
    )
    data = {
        "hold_id": hold.id,
        **describe(hold, doctors, ctx.tz),
        "message": "Read these details back and ask the caller to confirm.",
    }
    if ctx.state.found_appointments:
        data["if_rescheduling"] = (
            "To move their existing appointment here, after their yes call reschedule_appointment "
            "with its appointment_id and this hold_id (not confirm_booking)."
        )
    return ToolResult(data, events)
