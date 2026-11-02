from app.agent.context import ToolContext, ToolResult
from app.agent.handlers._common import describe
from app.agent.tools import FindPatientArgs


async def handle(ctx: ToolContext, args: FindPatientArgs) -> ToolResult:
    match = await ctx.repo.find_patient(
        ctx.session_id, args.full_name, args.date_of_birth, ctx.now()
    )
    if match is None:
        return ToolResult(
            {
                "found": False,
                "message": "No patient with that name and birthday. Check the spelling with the "
                "caller, or treat them as a new patient.",
            }
        )
    doctors = await ctx.repo.doctors()
    for appointment in match.appointments:
        ctx.state.presented.setdefault(appointment.id, ctx.turn_id)  # first read-back counts
    ctx.state.found_appointments = [a.id for a in match.appointments]
    return ToolResult(
        {
            "found": True,
            "full_name": match.full_name,
            "upcoming_appointments": [
                {"appointment_id": a.id, **describe(a, doctors, ctx.tz)} for a in match.appointments
            ],
        }
    )
