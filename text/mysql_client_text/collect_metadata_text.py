"""测试脚本：本地触发一次元数据构建（采集 → SQLite + Milvus）"""

import asyncio

from agent.schemas import DbConnection
from agent.orchestrator import build_metadata
from agent.sql.schema_initializer import init_metadata_schema
from client.meta_db_client_manager import meta_db_client_manager
from client.mysql_client_manager import mysql_client_manager


async def main():
    await init_metadata_schema()     # 建 SQLite 表
    meta_db_client_manager.init()
    try:
        conn = DbConnection(
            host="wl",
            port=3307,
            user="root",
            password="123456",
        )
        report = await build_metadata(conn, ["supply_chain"])   # 选中的业务库
        print(report.format())
    finally:
        await meta_db_client_manager.close()
        await mysql_client_manager.close_all()


if __name__ == "__main__":
    asyncio.run(main())
