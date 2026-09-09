import asyncio

from client.mysql_client_manager import mysql_client_manager

from agent.service.database_service import database_service


async def _main():
    session_factory = mysql_client_manager.get_session_factory("wl", 3307, "root", "123456")
    try:
        databases = await database_service.refresh(session_factory)
        for database in databases:
            tables = await database_service.get_tables(session_factory, database)
            print(f"数据库 {database}: {tables}")
    finally:
        await mysql_client_manager.close_all()


if __name__ == "__main__":
    asyncio.run(_main())
