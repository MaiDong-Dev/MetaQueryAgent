"""单库处理节点（M2~M5）：diff 同步 + LLM 补全 + 写 SQLite + 写向量"""

from langgraph.runtime import Runtime

from agent.schemas import DbConnection
from agent.graph.context import MetaAgentContext
from agent.graph.state import MetaAgentState


def _is_empty_enrich(enrich) -> bool:
    """LLM 兜底返回的空结构视为失败"""
    return not enrich.table_biz_desc and not enrich.business_domain and not enrich.column_enrich


def _write_vectors(enriched) -> tuple[int, str | None]:
    """把补全后的字段语义向量写入 Milvus，返回 (写入条数, 错误信息)"""
    try:
        from agent.vector import milvus_store

        texts, domains = [], []
        for table, enrich in enriched:
            domain = enrich.business_domain
            for col in table.columns:
                texts.append(f"{table.database_name} {table.table_name} {col.column_name}")
                domains.append(domain or "")
        if not texts:
            return 0, None
        milvus_store.init_collection()
        milvus_store.upsert(texts, domains)
        return len(texts), None
    except Exception as e:
        # 向量库/embedding 不可用时不影响元数据落库，但记录错误
        return 0, str(e)


async def process_db(state: MetaAgentState, runtime: Runtime[MetaAgentContext]) -> dict:
    """处理当前下标指向的库：diff + 补全 + 落库 + 向量"""
    conn = state["conn"]
    ctx = runtime.context
    db_meta = state["raw_schemas"][state["index"]]
    totals = dict(state["totals"])

    # 每个库一个独立 instance（带 database），互不干扰
    db_conn = DbConnection(
        host=conn.host, port=conn.port,
        user=conn.user, password=conn.password,
        database=db_meta.database_name,
    )
    diff = await ctx.differ.sync(db_conn, [db_meta])
    summary = diff.summary()
    for key in ("added_tables", "modified_tables", "deleted_tables",
                "added_columns", "modified_columns", "deleted_columns"):
        totals[key] += summary[key]

    # 条件分支：仅对新增/修改的表做 LLM 补全与向量写入
    changed_tables = diff.added_tables + [new for _, new in diff.modified_tables]
    if changed_tables:
        enriched = await ctx.enricher.enrich_all(changed_tables)
        await ctx.repo.save_enrichments(ctx.differ.instance_id, enriched)
        totals["enriched_tables"] += len(enriched)
        totals["enriched_columns"] += sum(len(e.column_enrich) for _, e in enriched)
        totals["llm_failed"] += sum(1 for _, e in enriched if _is_empty_enrich(e))
        vectors_written, vectors_error = _write_vectors(enriched)
        totals["vectors_written"] += vectors_written
        if vectors_error:
            totals["vectors_error"] = vectors_error

    return {"index": state["index"] + 1, "totals": totals}
