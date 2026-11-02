from app.agent.context import ToolContext, ToolResult
from app.agent.tools import HoldIdArgs
from app.scheduling.booking import Rejection


async def handle(ctx: ToolContext, args: HoldIdArgs) -> ToolResult:
    result = await ctx.repo.release(ctx.session_id, args.hold_id)
    if isinstance(result, Rejection):
        return ToolResult.rejected(result)
    return ToolResult({"released": True}, [("calendar.slot_released", {"id": result.id})])
