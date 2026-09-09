"""元数据查询服务：供前端展示 SQLite 里的元数据"""

import re

from sqlalchemy import text

from client.meta_db_client_manager import meta_db_client_manager

# md_* 表名白名单
MD_TABLE_NAMES = [
    "md_instance", "md_database", "md_table", "md_column", "md_index",
    "md_change_log", "md_table_biz", "md_column_biz", "md_code_dict",
]


async def get_overview() -> dict:
    """总览：库/表/字段数量"""
    async with meta_db_client_manager.session_factory() as session:
        databases = (await session.execute(
            text("SELECT COUNT(*) FROM md_database WHERE is_deleted = 0")
        )).scalar()
        tables = (await session.execute(
            text("SELECT COUNT(*) FROM md_table WHERE is_deleted = 0")
        )).scalar()
        columns = (await session.execute(
            text("SELECT COUNT(*) FROM md_column WHERE is_deleted = 0")
        )).scalar()
    return {"databases": databases, "tables": tables, "columns": columns}


async def list_databases() -> list[str]:
    """元数据库里的库名列表"""
    async with meta_db_client_manager.session_factory() as session:
        result = await session.execute(
            text("SELECT database_name FROM md_database WHERE is_deleted = 0")
        )
        return [r[0] for r in result.all()]


async def list_tables(database: str) -> list[dict]:
    """某库的表列表（含业务域/描述）"""
    async with meta_db_client_manager.session_factory() as session:
        result = await session.execute(
            text(
                """
                SELECT t.table_name, t.table_type, t.engine, t.table_comment,
                       b.table_biz_desc, b.business_domain
                FROM md_table t
                LEFT JOIN md_table_biz b
                  ON b.instance_id = t.instance_id
                 AND b.database_name = t.database_name
                 AND b.table_name = t.table_name
                WHERE t.database_name = :db AND t.is_deleted = 0
                """
            ),
            {"db": database},
        )
        return [dict(r) for r in result.mappings()]


async def list_columns(database: str, table: str) -> list[dict]:
    """某表的字段列表（含业务描述/敏感标记）"""
    async with meta_db_client_manager.session_factory() as session:
        result = await session.execute(
            text(
                """
                SELECT c.column_name, c.column_type, c.is_nullable,
                       c.column_default, c.column_comment,
                       b.biz_desc, b.sensitivity, b.business_domain
                FROM md_column c
                LEFT JOIN md_column_biz b
                  ON b.instance_id = c.instance_id
                 AND b.database_name = c.database_name
                 AND b.table_name = c.table_name
                 AND b.column_name = c.column_name
                WHERE c.database_name = :db AND c.table_name = :tbl AND c.is_deleted = 0
                ORDER BY c.ordinal_position
                """
            ),
            {"db": database, "tbl": table},
        )
        return [dict(r) for r in result.mappings()]


# ---------- 元数据库原始表查询（前端直接看 md_* 表内容） ----------

async def list_md_tables() -> list[str]:
    """列出元数据库里所有 md_* 表"""
    return MD_TABLE_NAMES


async def query_md_table(table: str, limit: int = 100) -> dict:
    """查询指定 md_* 表的所有记录"""
    # 严格白名单 + 标识符格式校验（防 SQL 注入）
    if table not in MD_TABLE_NAMES or not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", table):
        return {"table": table, "columns": [], "rows": [], "count": 0, "error": "Invalid table name"}
    async with meta_db_client_manager.session_factory() as session:
        result = await session.execute(
            text(f'SELECT * FROM "{table}" LIMIT :limit'),
            {"limit": limit},
        )
        rows = [dict(r) for r in result.mappings()]
        columns = list(result.keys()) if rows else []
    return {"table": table, "columns": columns, "rows": rows, "count": len(rows)}
