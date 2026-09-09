"""采集节点（M1）：连接业务库，采集所有选中库的 schema"""

from langgraph.runtime import Runtime

from agent.collector import SchemaCollector
from agent.graph.context import MetaAgentContext
from agent.graph.state import MetaAgentState, empty_totals


async def collect(state: MetaAgentState, runtime: Runtime[MetaAgentContext]) -> dict:
    """采集用户数据库的库/表/列结构，作为后续节点的输入"""
    session_factory = runtime.context.session_factory
    collector = SchemaCollector(session_factory)
    metas = await collector.collect(state.get("databases"))
    return {"raw_schemas": metas, "index": 0, "totals": empty_totals()}
