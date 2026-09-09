"""FastAPI 入口：连接管理、库列表、元数据构建、查询展示"""

from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from config.client_conf import schema_conf
from agent.schemas import CollectRequest, DbConnection
from agent.orchestrator import build_metadata
from agent.service.database_service import database_service
from agent.service import metadata_query
from agent.sql.schema_initializer import init_metadata_schema
from client.meta_db_client_manager import meta_db_client_manager
from client.mysql_client_manager import mysql_client_manager

_STATIC_DIR = Path(__file__).parents[1] / "static"


@asynccontextmanager
async def lifespan(app):
    # 启动：建表 + 初始化元数据库连接
    await init_metadata_schema()
    meta_db_client_manager.init()
    yield
    # 关闭：释放连接
    await meta_db_client_manager.close()
    await mysql_client_manager.close_all()


app = FastAPI(title="Meta Builder Agent", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def index():
    """前端页面"""
    return (_STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.post("/databases")
async def list_databases(conn: DbConnection):
    """列出指定连接下的业务库（排除系统库），供用户选择"""
    try:
        session_factory = mysql_client_manager.get_session_factory(
            conn.host, conn.port, conn.user, conn.password
        )
        databases = await database_service.refresh(session_factory)
        return {"databases": databases}
    except Exception as e:
        return {"error": str(e)}


@app.post("/collect")
async def collect(req: CollectRequest):
    """发起元数据构建：连接用户数据库，采集选中的库，写入 SQLite + Milvus"""
    conn = DbConnection(
        host=req.host, port=req.port, user=req.user, password=req.password
    )
    report = await build_metadata(conn, req.databases)
    return asdict(report)


# ---------- 元数据查询（SQLite） ----------

@app.get("/metadata/overview")
async def metadata_overview():
    return await metadata_query.get_overview()


@app.get("/metadata/databases")
async def metadata_databases():
    return {"databases": await metadata_query.list_databases()}


@app.get("/metadata/tables")
async def metadata_tables(database: str):
    return {"tables": await metadata_query.list_tables(database)}


@app.get("/metadata/columns")
async def metadata_columns(database: str, table: str):
    return {"columns": await metadata_query.list_columns(database, table)}


# ---------- 元数据库原始表查询（前端直接看 md_* 表内容） ----------

@app.get("/metadata/md_tables")
async def metadata_md_tables():
    """列出元数据库里所有 md_* 表"""
    return {"tables": await metadata_query.list_md_tables()}


@app.get("/metadata/md_table/{name}")
async def metadata_md_table(name: str, limit: int = 100):
    """查询指定 md_* 表的所有记录"""
    return await metadata_query.query_md_table(name, limit)


# ---------- 向量查询（Milvus） ----------

@app.get("/vectors")
async def vectors(limit: int = 100):
    try:
        from pymilvus import MilvusClient

        conf = schema_conf.milvus
        client = MilvusClient(uri=f"http://{conf.host}:{conf.port}")
        # 关键：MilvusClient 实例必须自己 load_collection 过，否则 get_collection_stats 返回 row_count=0
        client.load_collection(conf.collection)
        # growing segment 未 flush 时 row_count 统计为 0，先 flush 兜底
        client.flush(conf.collection)
        stats = client.get_collection_stats(conf.collection)
        row_count = stats.get("row_count", 0)
        items = []
        if row_count > 0:
            items = client.query(
                collection_name=conf.collection,
                filter="id >= 0",
                output_fields=["column_text", "business_domain"],
                limit=limit,
            )
        return {"count": row_count, "items": items}
    except Exception as e:
        return {"count": 0, "items": [], "error": str(e)}


@app.get("/health")
async def health():
    return {"status": "ok"}
