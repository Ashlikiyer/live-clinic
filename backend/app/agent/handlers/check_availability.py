from app.agent.context import ToolContext, ToolResult
from app.agent.handlers._common import doctor_name
from app.agent.spoken import clinic_iso, spoken_time
from app.agent.tools import CheckAvailabilityArgs
from app.core.clinic import VisitType
from app.scheduling.availability import free_slots


async def handle(ctx: ToolContext, args: CheckAvailabilityArgs) -> ToolResult:
    doctors = await ctx.repo.doctors()
    doctor_ids = [d.id for d in doctors]
    if args.doctor_id and args.doctor_id not in doctor_ids:
        return ToolResult(
            {"error": "UNKNOWN_DOCTOR", "message": f"Known doctor ids: {', '.join(doctor_ids)}."},
            ok=False,
        )
    now = ctx.now()
    last = args.date_to or args.date_from
    busy = await ctx.repo.busy(ctx.session_id, args.date_from, last, now)
    slots = free_slots(
        date_from=args.date_from,
        date_to=last,
        now=now,
        tz=ctx.tz,
        doctor_ids=[args.doctor_id] if args.doctor_id else doctor_ids,
        visit_type=VisitType(args.visit_type),
        part_of_day=args.part_of_day,
        busy=busy,
    )
    if not slots:
        return ToolResult(
            {
                "slots": [],
                "message": "Nothing free then. Check the next days or another part of the day.",
            }
        )
    first_day = slots[0].start.astimezone(ctx.tz).date()
    offered_today = [
        {"start": clinic_iso(s.start, ctx.tz), "doctor_id": s.doctor_id}
        for s in slots
        if s.start.astimezone(ctx.tz).date() == first_day
    ]
    return ToolResult(
        {
            "slots": [
                {
                    "slot_start": clinic_iso(s.start, ctx.tz),
                    "doctor_id": s.doctor_id,
                    "doctor": doctor_name(doctors, s.doctor_id),
                    "when": spoken_time(s.start, ctx.tz),
                }
                for s in slots
            ],
            "message": "Offer at most two of these.",
        },
        [("calendar.slots_offered", {"date": first_day.isoformat(), "slots": offered_today})],
    )
