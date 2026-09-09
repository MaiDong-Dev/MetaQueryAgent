import asyncio

from client.mysql_client_manager import mysql_client_manager

from agent.service.database_service import database_service


async def _main():
    session_factory = mysql_client_manager.get_session_factory("wl", 3307, "root", "123456")
    try:
        databases = await database_service.refresh(session_factory)
        print(f"业务数据库列表: {databases}")
        # 演示缓存用法：refresh 后再取，不会再次查库
        print(f"缓存读取: {database_service.get_databases()}")
    finally:
        await mysql_client_manager.close_all()


if __name__ == "__main__":
    asyncio.run(_main())
