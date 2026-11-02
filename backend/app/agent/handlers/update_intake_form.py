from app.agent.context import ToolContext, ToolResult
from app.agent.tools import UpdateIntakeFormArgs
from app.scheduling.booking import missing_form_fields


async def handle(ctx: ToolContext, args: UpdateIntakeFormArgs) -> ToolResult:
    values = {k: str(v) for k, v in args.model_dump(exclude_none=True, mode="json").items()}
    changed = await ctx.repo.update_form(ctx.call_id, values)
    form = await ctx.repo.form(ctx.call_id)
    return ToolResult(
        {
            "saved": list(values),
            "still_needed_for_booking": missing_form_fields(form),
        },
        [
            ("form.field_updated", {"field": field, "value": value, "corrected": corrected})
            for field, value, corrected in changed
        ],
    )
