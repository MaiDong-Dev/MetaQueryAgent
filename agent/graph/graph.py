"""M6 LangGraph 编排：collect → process_db(循环) → finalize

graph.py 只负责「组装」，节点逻辑在 nodes/ 目录，依赖在 context.py：
- State：业务数据（conn/databases/raw_schemas/index/totals/report）
- Context：基础设施（session_factory/repo/differ/llm/enricher），
          通过 graph.ainvoke(context=...) 注入，节点用 runtime.context 访问

断点续跑说明：
  当前用 InMemorySaver（进程内）。生产要跨进程/跨重启续跑时，换
  langgraph.checkpoint.sqlite.SqliteSaver + 固定 thread_id 即可。
"""

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver

from agent.graph.state import MetaAgentState
from agent.graph.context import MetaAgentContext
from agent.graph.nodes import collect, process_db, finalize


def _should_continue(state: MetaAgentState) -> str:
    """还有未处理的库则继续循环，否则进入 finalize"""
    return "process_db" if state["index"] < len(state["raw_schemas"]) else "finalize"


_graph = None


def get_graph():
    """获取模块级单例图（编译一次，多次运行复用）"""
    global _graph
    if _graph is None:
        builder = StateGraph(
            state_schema=MetaAgentState,
            context_schema=MetaAgentContext,
        )
        builder.add_node("collect", collect)
        builder.add_node("process_db", process_db)
        builder.add_node("finalize", finalize)

        builder.add_edge(START, "collect")
        builder.add_edge("collect", "process_db")
        builder.add_conditional_edges(
            "process_db",
            _should_continue,
            {"process_db": "process_db", "finalize": "finalize"},
        )
        builder.add_edge("finalize", END)

        _graph = builder.compile(checkpointer=InMemorySaver())
    return _graph
