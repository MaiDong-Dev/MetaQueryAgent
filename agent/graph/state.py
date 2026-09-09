"""M6 LangGraph 状态定义（业务数据，随工作流流转变化）

与 Context 分离：
- State：存储业务数据，随节点执行而变化
- Context：存储基础设施依赖，单次运行内不变（见 context.py）
"""

from typing import Any, TypedDict

from agent.schemas import DbConnection


def empty_totals() -> dict[str, Any]:
    """初始汇总统计"""
    return {
        "added_tables": 0, "modified_tables": 0, "deleted_tables": 0,
        "added_columns": 0, "modified_columns": 0, "deleted_columns": 0,
        "enriched_tables": 0, "enriched_columns": 0,
        "llm_failed": 0, "vectors_written": 0, "vectors_error": None,
    }


class MetaAgentState(TypedDict, total=False):
    conn: DbConnection                # 连接信息
    databases: list[str] | None       # 选中的业务库；None 表示全部
    raw_schemas: list[Any]            # M1 采集结果（所有选中库的 metas）
    index: int                        # 当前处理的库下标（循环用）
    totals: dict[str, Any]            # 汇总统计（累积）
    report: dict[str, Any]            # 最终报告（SyncReport 字段）
    error: str | None
