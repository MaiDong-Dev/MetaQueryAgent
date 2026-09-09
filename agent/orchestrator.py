"""核心编排：按请求驱动，采集用户数据库 → 写入 SQLite + Milvus

M6 起内部改用 LangGraph 状态图编排，详见 agent/graph/。
对外接口 build_metadata(conn, databases) 保持不变，/collect 与前端零改动。
"""

from uuid import uuid4

from config.client_conf import schema_conf
from agent.schemas import DbConnection
from agent.report import SyncReport
from agent.repo import MetaRepo
from agent.diff import Differ
from agent.llm import LlmClient, Enricher
from agent.graph.context import MetaAgentContext
from agent.graph.graph import get_graph
from client.mysql_client_manager import mysql_client_manager
from client.meta_db_client_manager import meta_db_client_manager


def _build_context(conn: DbConnection) -> MetaAgentContext:
    """按请求构建基础设施依赖（业务库连接是请求级的，故每次构建）"""
    session_factory = mysql_client_manager.get_session_factory(
        conn.host, conn.port, conn.user, conn.password
    )
    repo = MetaRepo(meta_db_client_manager.session_factory)
    differ = Differ(repo)
    llm = LlmClient(
        schema_conf.llm.base_url,
        schema_conf.llm.api_key,
        schema_conf.llm.model,
    )
    enricher = Enricher(llm)
    return MetaAgentContext(
        session_factory=session_factory,
        repo=repo,
        differ=differ,
        llm=llm,
        enricher=enricher,
    )


async def build_metadata(conn: DbConnection, databases: list[str] | None = None) -> SyncReport:
    """核心流程（LangGraph 状态图编排）：连接 → 采集 → 每个库独立增量同步 + LLM 补全 → 写入 SQLite + Milvus"""
    graph = get_graph()
    context = _build_context(conn)
    try:
        # 每次运行唯一 thread_id，避免 InMemorySaver checkpoint 状态跨请求串扰；
        # 生产要断点续跑时：换 SqliteSaver + 固定 thread_id
        config = {"configurable": {"thread_id": f"meta-{conn.instance_name}-{uuid4().hex}"}}
        state = await graph.ainvoke(
            {"conn": conn, "databases": databases},
            context=context,
            config=config,
        )
        return SyncReport(**state["report"])
    except Exception as e:
        return SyncReport(instance_name=conn.instance_name, error=str(e))
    finally:
        await context.llm.aclose()
