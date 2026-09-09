from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)


class MysqlClientManager:
    """业务库动态连接管理器

    业务库由用户按需提供连接信息，不再固定配置。
    按连接信息（host:port:user）缓存 engine 与 session_factory。
    """

    def __init__(self):
        self._engines: dict[str, AsyncEngine] = {}
        self._sessions: dict[str, async_sessionmaker] = {}

    def get_session_factory(self, host: str, port: int, user: str, password: str):
        """根据连接信息获取 session_factory（懒创建并缓存）"""
        key = f"{host}:{port}:{user}"
        if key not in self._sessions:
            engine = create_async_engine(
                f"mysql+aiomysql://{user}:{password}@{host}:{port}",
                pool_size=10,
                pool_pre_ping=True,
            )
            self._engines[key] = engine
            self._sessions[key] = async_sessionmaker(
                engine,
                autoflush=True,
                autobegin=True,
                expire_on_commit=False,
            )
        return self._sessions[key]

    async def close_all(self):
        """关闭所有业务库连接"""
        for engine in self._engines.values():
            await engine.dispose()
        self._engines.clear()
        self._sessions.clear()


mysql_client_manager = MysqlClientManager()
