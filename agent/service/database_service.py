from typing import Optional

from sqlalchemy import text

# MySQL 自带的系统库，业务展示时排除
SYSTEM_DATABASES = {"information_schema", "mysql", "performance_schema", "sys"}


class DatabaseService:
    """业务数据库清单服务（多实例：每次调用需显式传入 session_factory）"""

    def __init__(self):
        self._databases: Optional[list[str]] = None

    async def refresh(self, session_factory) -> list[str]:
        """查询 MySQL 并刷新缓存，返回最新业务数据库列表"""
        async with session_factory() as session:
            result = await session.execute(text("show databases"))
            databases = [row[0] for row in result.all()]
        business_databases = [db for db in databases if db not in SYSTEM_DATABASES]
        self._databases = business_databases
        return business_databases

    def get_databases(self) -> list[str]:
        """同步获取已缓存的数据库列表

        未 refresh 过则抛错，避免调用方在不知情时拿到不完整状态
        """
        if self._databases is None:
            raise RuntimeError("数据库清单尚未刷新，请先 await database_service.refresh(session_factory)")
        return self._databases

    async def get_tables(self, session_factory, database: str) -> list[str]:
        """获取指定数据库的表列表

        :param session_factory: 目标实例的 session_factory
        :param database: 单个数据库名字符串(如 "supply_chain")，不要传入列表

        库名属于 SQL 标识符，无法走参数绑定，这里用反引号包裹并做基础校验防注入
        """
        if not database or any(ch in database for ch in ("`", ";", "\0")):
            raise ValueError(f"非法的数据库名: {database!r}")
        async with session_factory() as session:
            result = await session.execute(text(f"show tables in `{database}`"))
            tables = [row[0] for row in result.all()]
        return tables


# 全局单例，供各模块直接复用
database_service = DatabaseService()
