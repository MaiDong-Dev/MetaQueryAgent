"""自动建表初始化：幂等创建 SQLite 元数据库的 md_* 表

读取同目录下的 001_create_metadata_tables.sql，拆分出建表语句执行。
SQLite 无需建库，只需确保文件目录存在后直接建表。
"""

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from config.client_conf import schema_conf

_SQL_FILE = Path(__file__).parent / "001_create_metadata_tables.sql"


async def init_metadata_schema() -> None:
    """创建 SQLite 元数据库文件并执行建表语句（幂等）"""
    db_path = Path(schema_conf.meta_db.path)
    db_path.parent.mkdir(parents=True, exist_ok=True)   # 确保 data/ 目录存在

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        for ddl in _load_create_table_ddl():
            await conn.execute(text(ddl))
    await engine.dispose()


def _load_create_table_ddl() -> list[str]:
    """从 SQL 文件解析出建表语句（过滤注释行）"""
    raw = _SQL_FILE.read_text(encoding="utf-8")
    statements: list[str] = []
    for stmt in raw.split(";"):
        lines = [ln for ln in stmt.splitlines() if not ln.strip().startswith("--")]
        s = "\n".join(lines).strip()
        if s:
            statements.append(s)
    return statements
