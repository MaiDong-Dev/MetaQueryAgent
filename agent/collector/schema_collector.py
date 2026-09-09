"""M1：information_schema 采集器

只负责执行 SQL 并把结果组装成 pydantic 模型，不定义数据模型。
数据模型见 agent.collector.models。
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from agent.collector.models import (
    ColumnMeta,
    DatabaseMeta,
    IndexMeta,
    TableMeta,
)


class SchemaCollector:
    """从 information_schema 采集 库/表/字段/索引 技术元数据"""

    SYSTEM_DATABASES = ("information_schema", "mysql", "performance_schema", "sys")

    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def collect(self, databases: list[str] | None = None) -> list[DatabaseMeta]:
        """采集业务库结构

        :param databases: 指定库名列表；None 表示采集所有业务库
        """
        async with self.session_factory() as session:
            db_list = await self._fetch_databases(session)
            if databases is not None:
                db_set = set(databases)
                db_list = [(n, c, o) for n, c, o in db_list if n in db_set]
            result: list[DatabaseMeta] = []
            for db_name, charset, collation in db_list:
                tables = await self._fetch_tables(session, db_name)
                for table in tables:
                    table.columns = await self._fetch_columns(
                        session, db_name, table.table_name
                    )
                    table.indexes = await self._fetch_indexes(
                        session, db_name, table.table_name
                    )
                result.append(
                    DatabaseMeta(
                        database_name=db_name,
                        charset=charset,
                        collation=collation,
                        tables=tables,
                    )
                )
            return result

    async def _fetch_databases(
        self, session: AsyncSession
    ) -> list[tuple[str, str | None, str | None]]:
        sql = text(
            """
            SELECT schema_name, default_character_set_name, default_collation_name
            FROM information_schema.schemata
            WHERE schema_name NOT IN ('information_schema','mysql','performance_schema','sys')
            """
        )
        result = await session.execute(sql)
        return [
            (r["schema_name"], r["default_character_set_name"], r["default_collation_name"])
            for r in self._rows(result)
        ]

    async def _fetch_tables(
        self, session: AsyncSession, database: str
    ) -> list[TableMeta]:
        sql = text(
            """
            SELECT table_name, table_type, engine, table_comment, table_collation
            FROM information_schema.tables
            WHERE table_schema = :db
            """
        )
        result = await session.execute(sql, {"db": database})
        tables: list[TableMeta] = []
        for r in self._rows(result):
            collation = r["table_collation"]
            tables.append(
                TableMeta(
                    database_name=database,
                    table_name=r["table_name"],
                    table_type=r["table_type"],
                    engine=r["engine"],
                    table_comment=r["table_comment"],
                    charset=self._charset_from_collation(collation),
                    collation=collation,
                )
            )
        return tables

    async def _fetch_columns(
        self, session: AsyncSession, database: str, table: str
    ) -> list[ColumnMeta]:
        sql = text(
            """
            SELECT column_name, ordinal_position, column_default, is_nullable,
                   data_type, column_type, character_maximum_length,
                   numeric_precision, numeric_scale, character_set_name,
                   collation_name, extra, column_comment
            FROM information_schema.columns
            WHERE table_schema = :db AND table_name = :tbl
            ORDER BY ordinal_position
            """
        )
        result = await session.execute(sql, {"db": database, "tbl": table})
        columns: list[ColumnMeta] = []
        for r in self._rows(result):
            columns.append(
                ColumnMeta(
                    column_name=r["column_name"],
                    ordinal_position=r["ordinal_position"],
                    column_default=self._as_str(r["column_default"]),
                    is_nullable=r["is_nullable"],
                    data_type=r["data_type"],
                    column_type=r["column_type"],
                    char_max_length=r["character_maximum_length"],
                    numeric_precision=r["numeric_precision"],
                    numeric_scale=r["numeric_scale"],
                    charset=r["character_set_name"],
                    collation=r["collation_name"],
                    column_extra=r["extra"],
                    column_comment=r["column_comment"],
                )
            )
        return columns

    async def _fetch_indexes(
        self, session: AsyncSession, database: str, table: str
    ) -> list[IndexMeta]:
        sql = text(
            """
            SELECT index_name, non_unique, seq_in_index, column_name, index_type
            FROM information_schema.statistics
            WHERE table_schema = :db AND table_name = :tbl
            ORDER BY index_name, seq_in_index
            """
        )
        result = await session.execute(sql, {"db": database, "tbl": table})
        indexes: list[IndexMeta] = []
        for r in self._rows(result):
            indexes.append(
                IndexMeta(
                    index_name=r["index_name"],
                    non_unique=bool(r["non_unique"]),
                    seq_in_index=r["seq_in_index"],
                    column_name=r["column_name"],
                    index_type=r["index_type"],
                )
            )
        return indexes

    @staticmethod
    def _rows(result):
        """把查询结果转为小写列名的 dict 列表

        information_schema 的列名实际返回为大写（如 SCHEMA_NAME），
        统一转小写以便用 r["schema_name"] 访问。
        """
        return [{k.lower(): v for k, v in row.items()} for row in result.mappings()]

    @staticmethod
    def _charset_from_collation(collation: str | None) -> str | None:
        """从排序规则推导字符集，如 utf8mb4_general_ci -> utf8mb4"""
        return collation.split("_")[0] if collation else None

    @staticmethod
    def _as_str(value) -> str | None:
        """把列默认值统一转为字符串，None 保持 None"""
        return None if value is None else str(value)
