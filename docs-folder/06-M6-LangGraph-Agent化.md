# 06 · M6 LangGraph Agent 化

## 一、实现目标

当采集/比对/补全等流程变复杂（多分支、工具调用、断点续跑、人工介入）后，把现有 async 流程函数重构为 **LangGraph** 状态机，获得：

1. 状态持久化（checkpoint），支持断点续跑与回溯；
2. 图结构清晰表达多步骤、条件分支；
3. 工具调用能力（查询元数据库、触发采集、调用 LLM）；
4. 支持人工审批节点（human-in-the-loop）。

### 验收标准
- 原有 M1~M5 能力在 LangGraph 编排下功能等价；
- 中途失败可从 checkpoint 恢复，不重复执行已完成步骤；
- 新增工具节点（如"查询某库表结构"）可被 Agent 决策调用。

## 二、详细开发过程

### 步骤 1：定义状态（`agent/state.py`）

LangGraph 的 `State` 基于 `TypedDict`，与方案中的 `MetaAgentState` 对应：

```python
from typing import TypedDict
from datetime import datetime

class MetaAgentState(TypedDict, total=False):
    instance_id: str
    connection_conf: dict
    raw_schemas: list[dict]
    diff_result: dict
    enrich_schemas: list[dict]
    crawl_time: datetime
    pending_human_approval: bool
```

### 步骤 2：把现有步骤拆成节点

```python
from langgraph.graph import StateGraph, START, END

async def node_collect(state):        # M1 采集
    state["raw_schemas"] = await collector.collect()
    return state

async def node_diff(state):           # M2 比对
    state["diff_result"] = await differ.diff(state["instance_id"], state["raw_schemas"])
    return state

async def node_enrich(state):         # M3 LLM 补全
    state["enrich_schemas"] = await enricher.enrich_all(state["diff_result"]["changed"])
    return state

async def node_persist(state):        # 写元数据库
    await repo.save(state["enrich_schemas"], state["diff_result"])
    return state
```

### 步骤 3：构建图

```python
builder = StateGraph(MetaAgentState)
builder.add_node("collect", node_collect)
builder.add_node("diff", node_diff)
builder.add_node("enrich", node_enrich)
builder.add_node("persist", node_persist)

builder.add_edge(START, "collect")
builder.add_edge("collect", "diff")
builder.add_edge("diff", "enrich")
builder.add_edge("enrich", "persist")
builder.add_edge("persist", END)

graph = builder.compile(checkpointer=MemorySaver())   # 先内存 checkpoint，生产换持久化
```

### 步骤 4：条件分支（示例：无变更跳过 LLM）

```python
def should_enrich(state):
    return "enrich" if state["diff_result"]["has_changes"] else END

builder.add_conditional_edges("diff", should_enrich, {"enrich": "enrich", END: END})
```

### 步骤 5：工具调用（Agent 化核心）

把"查询元数据库""触发采集"等能力注册为 LangChain Tool，让 LLM 决策调用：

```python
@tool
async def query_tables(instance: str, database: str):
    """查询指定实例指定库的表清单"""
    return await database_service.get_tables(database)
```

### 步骤 6：运行与断点恢复

```python
config = {"configurable": {"thread_id": "run-20260908"}}
result = await graph.ainvoke(initial_state, config)
```

通过固定的 `thread_id` + 持久化 checkpointer，失败后重新 invoke 会从断点续跑。

## 三、关键注意点

- **先保证 M1~M5 稳定**，再迁移到 LangGraph，否则状态机掩盖业务 bug；
- LangGraph 的异步节点用 `ainvoke`/`astream`，与现有 async 栈一致；
- checkpoint 生产环境要换成持久化（如 SQLite/Postgres saver），不能只用 `MemorySaver`；
- 工具描述要清晰，便于 LLM 正确路由；敏感操作（如删除、批量写）建议加人工审批节点。

## 四、依赖变更

`pyproject.toml` 新增：`langgraph`、`langchain-core`（如需 tool 装饰器）。执行 `uv add langgraph langchain-core`。
