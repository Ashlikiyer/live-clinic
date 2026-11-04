from datetime import date

from app.agent.confirmation import require_confirmation
from app.agent.context import ToolContext, ToolResult
from app.agent.handlers._common import describe
from app.agent.spoken import clinic_iso
from app.agent.tools import HoldIdArgs
from app.core.clinic import CallOutcome
from app.repositories.booking import patient_ref
from app.scheduling.booking import Rejection, check_form_complete


async def handle(ctx: ToolContext, args: HoldIdArgs) -> ToolResult:
    if rejection := await require_confirmation(ctx, args.hold_id):
        return ToolResult.rejected(rejection)
    form = await ctx.repo.form(ctx.call_id)
    if rejection := check_form_complete(form):
        if ctx.state.found_appointments:
            rejection = Rejection(
                rejection.code,
                rejection.message + " If the caller is moving an existing appointment, use "
                "reschedule_appointment with its appointment_id and this hold_id instead.",
            )
        return ToolResult.rejected(rejection)

    name = str(form["full_name"]["value"])
    try:
        birthday = date.fromisoformat(str(form["date_of_birth"]["value"]))
    except ValueError:
        return ToolResult.rejected(
            Rejection("FORM_INCOMPLETE", "Save the date of birth as YYYY-MM-DD first.")
        )
    result = await ctx.repo.confirm(
        ctx.session_id,
        args.hold_id,
        patient_name=name,
        patient_ref=patient_ref(name, birthday),
        now=ctx.now(),
    )
    if isinstance(result, Rejection):
        return ToolResult.rejected(result)
    ctx.state.outcome = CallOutcome.BOOKED
    ctx.state.completed.add(CallOutcome.BOOKED)
    doctors = await ctx.repo.doctors()
    return ToolResult(
        {
            "booked": True,
            **describe(result, doctors, ctx.tz),
            "message": "Booked. Tell the caller to arrive 10 minutes early.",
        },
        [
            (
                "calendar.slot_confirmed",
                {
                    "appointment_id": result.id,
                    "start": clinic_iso(result.start, ctx.tz),
                    "end": clinic_iso(result.end, ctx.tz),
                    "doctor_id": result.doctor_id,
                    "patient_name": name,
                },
            )
        ],
    )
