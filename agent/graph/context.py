"""M6 LangGraph 上下文定义（基础设施依赖，单次运行内不变）

与 State 分离：
- State：业务数据，随节点执行而变化
- Context：基础设施依赖，全程不变，通过 graph.invoke(context=...) 注入

节点通过 runtime.context.xxx 访问，无需在节点 __init__ 中注入依赖。
"""

from dataclasses import dataclass
from typing import Any

from agent.repo import MetaRepo
from agent.diff import Differ
from agent.llm import LlmClient, Enricher


@dataclass
class MetaAgentContext:
    """单次元数据构建运行的基础设施依赖"""

    session_factory: Any       # 业务库连接工厂（来自请求连接信息）
    repo: MetaRepo             # SQLite 元数据仓库
    differ: Differ             # diff 比对器
    llm: LlmClient             # LLM 客户端
    enricher: Enricher         # 补全器
