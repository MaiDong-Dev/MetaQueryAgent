"""汇总报告节点：生成最终 SyncReport 字段"""

from langgraph.runtime import Runtime

from agent.graph.context import MetaAgentContext
from agent.graph.state import MetaAgentState


async def finalize(state: MetaAgentState, runtime: Runtime[MetaAgentContext]) -> dict:
    """把累计统计打包为最终报告字段"""
    return {"report": {"instance_name": state["conn"].instance_name, **state["totals"]}}
