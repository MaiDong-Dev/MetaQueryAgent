from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)

from config.client_conf import schema_conf, MetaDbConf


class MetaDbClientManager:
    """元数据库客户端管理器（SQLite）

    元数据与业务数据分离，存本地 SQLite 文件，不占用业务 MySQL。
    """

    def __init__(self, meta_db_conf: MetaDbConf):
        self.meta_db_conf = meta_db_conf
        self.engine: Optional[AsyncEngine] = None
        self.session_factory = None

    def _get_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.meta_db_conf.path}"

    def init(self, echo: bool = False):
        self.engine = create_async_engine(self._get_url(), echo=echo)
        self.session_factory = async_sessionmaker(
            self.engine,
            autoflush=True,
            autobegin=True,
            expire_on_commit=False,
        )

    async def close(self):
        await self.engine.dispose()

    async def __aenter__(self):
        self.init()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()


meta_db_client_manager = MetaDbClientManager(schema_conf.meta_db)
