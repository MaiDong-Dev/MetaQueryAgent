"""元数据库(SQLite)读写层

负责 md_* 表的增删改查，数据模型来自 agent.collector.models。
SQL 使用 SQLite 方言（ON CONFLICT ... DO UPDATE 做 upsert）。
"""

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from agent.collector.models import (
    ColumnMeta,
    DatabaseMeta,
    IndexMeta,
    TableMeta,
)


class MetaRepo:
    """元数据库读写层（SQLite）"""

    def __init__(self, session_factory):
        self.session_factory = session_factory

    # ---------- 实例 ----------

    async def get_or_create_instance(self, conn) -> int:
        """upsert 实例并返回 instance_id"""
        async with self.session_factory() as session:
            instance_id = await self._upsert_instance(session, conn)
            await session.commit()
            return instance_id

    # ---------- 读取现有记录 ----------

    async def load_existing(
        self, instance_id: int
    ) -> tuple[dict[tuple[str, str], TableMeta], dict[tuple[str, str, str], ColumnMeta]]:
        """读取该实例现有（未删除）的表和列，返回 (tables, columns)"""
        async with self.session_factory() as session:
            tables = await self._load_tables(session, instance_id)
            columns = await self._load_columns(session, instance_id)
            return tables, columns

    # ---------- 应用增量变更 ----------

    async def apply_diff(self, instance_id: int, metas: list[DatabaseMeta], diff) -> None:
        """在一个事务里完成：库 upsert + 表/字段增删改 + 变更日志"""
        async with self.session_factory() as session:
            for db in metas:
                await self._upsert_database(session, instance_id, db)

            for t in diff.added_tables:
                await self._upsert_table(session, instance_id, t)
                for col in t.columns:
                    await self._upsert_column(session, instance_id, t.database_name, t.table_name, col)
                for idx in t.indexes:
                    await self._upsert_index(session, instance_id, t.database_name, t.table_name, idx)

            for old, new in diff.modified_tables:
                await self._upsert_table(session, instance_id, new)

            for old_t in diff.deleted_tables:
                await self._soft_delete_table(session, instance_id, old_t.database_name, old_t.table_name)

            for db_name, table_name, col in diff.added_columns:
                await self._upsert_column(session, instance_id, db_name, table_name, col)

            for db_name, table_name, old, new in diff.modified_columns:
                await self._upsert_column(session, instance_id, db_name, table_name, new)

            for db_name, table_name, old_col in diff.deleted_columns:
                await self._soft_delete_column(
                    session, instance_id, db_name, table_name, old_col.column_name
                )

            await self._insert_change_logs(session, instance_id, diff)
            await session.commit()

    # ---------- 实例 upsert ----------

    async def _upsert_instance(self, session: AsyncSession, conn) -> int:
        sql = text(
            """
            INSERT INTO md_instance (instance_name, host, port, username, password)
            VALUES (:name, :host, :port, :username, :password)
            ON CONFLICT(instance_name) DO UPDATE SET
                host = excluded.host,
                port = excluded.port,
                username = excluded.username,
                password = excluded.password,
                updated_at = CURRENT_TIMESTAMP
            """
        )
        await session.execute(
            sql,
            {
                "name": conn.instance_name,
                "host": conn.host,
                "port": conn.port,
                "username": conn.user,
                "password": conn.password,
            },
        )
        result = await session.execute(
            text("SELECT id FROM md_instance WHERE instance_name = :name"),
            {"name": conn.instance_name},
        )
        return result.scalar_one()

    # ---------- 读取现有 ----------

    async def _load_tables(self, session: AsyncSession, instance_id: int) -> dict[tuple[str, str], TableMeta]:
        sql = text(
            """
            SELECT database_name, table_name, table_type, engine, table_comment, charset, collation
            FROM md_table
            WHERE instance_id = :instance_id AND is_deleted = 0
            """
        )
        result = await session.execute(sql, {"instance_id": instance_id})
        tables: dict[tuple[str, str], TableMeta] = {}
        for r in result.mappings():
            t = TableMeta(
                database_name=r["database_name"],
                table_name=r["table_name"],
                table_type=r["table_type"],
                engine=r["engine"],
                table_comment=r["table_comment"],
                charset=r["charset"],
                collation=r["collation"],
            )
            tables[(t.database_name, t.table_name)] = t
        return tables

    async def _load_columns(
        self, session: AsyncSession, instance_id: int
    ) -> dict[tuple[str, str, str], ColumnMeta]:
        sql = text(
            """
            SELECT database_name, table_name, column_name, ordinal_position, column_default,
                   is_nullable, data_type, column_type, char_max_length, numeric_precision,
                   numeric_scale, charset, collation, column_extra, column_comment
            FROM md_column
            WHERE instance_id = :instance_id AND is_deleted = 0
            """
        )
        result = await session.execute(sql, {"instance_id": instance_id})
        columns: dict[tuple[str, str, str], ColumnMeta] = {}
        for r in result.mappings():
            c = ColumnMeta(
                column_name=r["column_name"],
                ordinal_position=r["ordinal_position"],
                column_default=r["column_default"],
                is_nullable=r["is_nullable"],
                data_type=r["data_type"],
                column_type=r["column_type"],
                char_max_length=r["char_max_length"],
                numeric_precision=r["numeric_precision"],
                numeric_scale=r["numeric_scale"],
                charset=r["charset"],
                collation=r["collation"],
                column_extra=r["column_extra"],
                column_comment=r["column_comment"],
            )
            columns[(r["database_name"], r["table_name"], r["column_name"])] = c
        return columns

    # ---------- upsert ----------

    async def _upsert_database(self, session: AsyncSession, instance_id: int, db: DatabaseMeta):
        sql = text(
            """
            INSERT INTO md_database (instance_id, database_name, charset, collation, is_deleted)
            VALUES (:instance_id, :database_name, :charset, :collation, 0)
            ON CONFLICT(instance_id, database_name) DO UPDATE SET
                charset = excluded.charset,
                collation = excluded.collation,
                is_deleted = 0,
                updated_at = CURRENT_TIMESTAMP
            """
        )
        await session.execute(
            sql,
            {
                "instance_id": instance_id,
                "database_name": db.database_name,
                "charset": db.charset,
                "collation": db.collation,
            },
        )

    async def _upsert_table(self, session: AsyncSession, instance_id: int, table: TableMeta):
        sql = text(
            """
            INSERT INTO md_table
                (instance_id, database_name, table_name, table_type, engine,
                 table_comment, charset, collation, is_deleted)
            VALUES
                (:instance_id, :database_name, :table_name, :table_type, :engine,
                 :table_comment, :charset, :collation, 0)
            ON CONFLICT(instance_id, database_name, table_name) DO UPDATE SET
                table_type = excluded.table_type,
                engine = excluded.engine,
                table_comment = excluded.table_comment,
                charset = excluded.charset,
                collation = excluded.collation,
                is_deleted = 0,
                updated_at = CURRENT_TIMESTAMP
            """
        )
        await session.execute(
            sql,
            {
                "instance_id": instance_id,
                "database_name": table.database_name,
                "table_name": table.table_name,
                "table_type": table.table_type,
                "engine": table.engine,
                "table_comment": table.table_comment,
                "charset": table.charset,
                "collation": table.collation,
            },
        )

    async def _upsert_column(
        self, session: AsyncSession, instance_id: int, database_name: str, table_name: str, col: ColumnMeta
    ):
        sql = text(
            """
            INSERT INTO md_column
                (instance_id, database_name, table_name, column_name,
                 ordinal_position, column_default, is_nullable, data_type,
                 column_type, char_max_length, numeric_precision, numeric_scale,
                 charset, collation, column_extra, column_comment, is_deleted)
            VALUES
                (:instance_id, :database_name, :table_name, :column_name,
                 :ordinal_position, :column_default, :is_nullable, :data_type,
                 :column_type, :char_max_length, :numeric_precision, :numeric_scale,
                 :charset, :collation, :column_extra, :column_comment, 0)
            ON CONFLICT(instance_id, database_name, table_name, column_name) DO UPDATE SET
                ordinal_position = excluded.ordinal_position,
                column_default = excluded.column_default,
                is_nullable = excluded.is_nullable,
                data_type = excluded.data_type,
                column_type = excluded.column_type,
                char_max_length = excluded.char_max_length,
                numeric_precision = excluded.numeric_precision,
                numeric_scale = excluded.numeric_scale,
                charset = excluded.charset,
                collation = excluded.collation,
                column_extra = excluded.column_extra,
                column_comment = excluded.column_comment,
                is_deleted = 0,
                updated_at = CURRENT_TIMESTAMP
            """
        )
        await session.execute(
            sql,
            {
                "instance_id": instance_id,
                "database_name": database_name,
                "table_name": table_name,
                "column_name": col.column_name,
                "ordinal_position": col.ordinal_position,
                "column_default": col.column_default,
                "is_nullable": col.is_nullable,
                "data_type": col.data_type,
                "column_type": col.column_type,
                "char_max_length": col.char_max_length,
                "numeric_precision": col.numeric_precision,
                "numeric_scale": col.numeric_scale,
                "charset": col.charset,
                "collation": col.collation,
                "column_extra": col.column_extra,
                "column_comment": col.column_comment,
            },
        )

    async def _upsert_index(
        self, session: AsyncSession, instance_id: int, database_name: str, table_name: str, idx: IndexMeta
    ):
        sql = text(
            """
            INSERT INTO md_index
                (instance_id, database_name, table_name, index_name,
                 non_unique, seq_in_index, column_name, index_type)
            VALUES
                (:instance_id, :database_name, :table_name, :index_name,
                 :non_unique, :seq_in_index, :column_name, :index_type)
            ON CONFLICT(instance_id, database_name, table_name, index_name, seq_in_index) DO UPDATE SET
                non_unique = excluded.non_unique,
                column_name = excluded.column_name,
                index_type = excluded.index_type
            """
        )
        await session.execute(
            sql,
            {
                "instance_id": instance_id,
                "database_name": database_name,
                "table_name": table_name,
                "index_name": idx.index_name,
                "non_unique": int(idx.non_unique),
                "seq_in_index": idx.seq_in_index,
                "column_name": idx.column_name,
                "index_type": idx.index_type,
            },
        )

    # ---------- 软删除 ----------

    async def _soft_delete_table(self, session: AsyncSession, instance_id: int, database_name: str, table_name: str):
        await session.execute(
            text(
                "UPDATE md_table SET is_deleted = 1, updated_at = CURRENT_TIMESTAMP "
                "WHERE instance_id = :iid AND database_name = :db AND table_name = :tbl"
            ),
            {"iid": instance_id, "db": database_name, "tbl": table_name},
        )
        await session.execute(
            text(
                "UPDATE md_column SET is_deleted = 1, updated_at = CURRENT_TIMESTAMP "
                "WHERE instance_id = :iid AND database_name = :db AND table_name = :tbl"
            ),
            {"iid": instance_id, "db": database_name, "tbl": table_name},
        )

    async def _soft_delete_column(
        self, session: AsyncSession, instance_id: int, database_name: str, table_name: str, column_name: str
    ):
        await session.execute(
            text(
                "UPDATE md_column SET is_deleted = 1, updated_at = CURRENT_TIMESTAMP "
                "WHERE instance_id = :iid AND database_name = :db AND table_name = :tbl AND column_name = :col"
            ),
            {"iid": instance_id, "db": database_name, "tbl": table_name, "col": column_name},
        )

    # ---------- 变更日志 ----------

    async def _insert_change_logs(self, session: AsyncSession, instance_id: int, diff) -> None:
        logs = []
        for t in diff.added_tables:
            logs.append(self._log(instance_id, t.database_name, t.table_name, None, "TABLE", "ADD", None, t))
        for old, new in diff.modified_tables:
            logs.append(self._log(instance_id, old.database_name, old.table_name, None, "TABLE", "MODIFY", old, new))
        for old_t in diff.deleted_tables:
            logs.append(self._log(instance_id, old_t.database_name, old_t.table_name, None, "TABLE", "DELETE", old_t, None))

        for db_name, table_name, col in diff.added_columns:
            logs.append(self._log(instance_id, db_name, table_name, col.column_name, "COLUMN", "ADD", None, col))
        for db_name, table_name, old, new in diff.modified_columns:
            logs.append(self._log(instance_id, db_name, table_name, old.column_name, "COLUMN", "MODIFY", old, new))
        for db_name, table_name, old_col in diff.deleted_columns:
            logs.append(self._log(instance_id, db_name, table_name, old_col.column_name, "COLUMN", "DELETE", old_col, None))

        if not logs:
            return

        sql = text(
            """
            INSERT INTO md_change_log
                (instance_id, database_name, table_name, column_name,
                 change_type, object_type, old_value, new_value)
            VALUES
                (:instance_id, :database_name, :table_name, :column_name,
                 :change_type, :object_type, :old_value, :new_value)
            """
        )
        for log in logs:
            await session.execute(sql, log)

    @staticmethod
    def _log(instance_id, database_name, table_name, column_name, object_type, change_type, old, new) -> dict:
        return {
            "instance_id": instance_id,
            "database_name": database_name,
            "table_name": table_name,
            "column_name": column_name,
            "object_type": object_type,
            "change_type": change_type,
            "old_value": MetaRepo._dump(old) if old else None,
            "new_value": MetaRepo._dump(new) if new else None,
        }

    @staticmethod
    def _dump(obj) -> str:
        if isinstance(obj, TableMeta):
            data = obj.model_dump(exclude={"columns", "indexes"})
        else:
            data = obj.model_dump()
        return json.dumps(data, ensure_ascii=False, default=str)

    # ---------- 业务元数据写入（M3） ----------

    async def save_enrichments(self, instance_id: int, enriched: list) -> dict:
        """保存 LLM 补全结果，返回统计"""
        stats = {"tables": 0, "columns": 0, "code_dicts": 0}
        async with self.session_factory() as session:
            for table, enrich in enriched:
                await self._upsert_table_biz(session, instance_id, table, enrich)
                stats["tables"] += 1
                col_map = {ce.column_name: ce for ce in enrich.column_enrich}
                for col in table.columns:
                    ce = col_map.get(col.column_name)
                    if ce is None:
                        continue
                    await self._upsert_column_biz(session, instance_id, table, col, ce)
                    stats["columns"] += 1
                    if ce.enum_values:
                        for code_value, code_label in ce.enum_values.items():
                            await self._upsert_code_dict(
                                session, instance_id, table, col.column_name, code_value, code_label
                            )
                            stats["code_dicts"] += 1
            await session.commit()
        return stats

    async def _upsert_table_biz(self, session, instance_id, table, enrich):
        sql = text(
            """
            INSERT INTO md_table_biz
                (instance_id, database_name, table_name, table_biz_desc, business_domain, owner, ai_generated)
            VALUES
                (:instance_id, :database_name, :table_name, :table_biz_desc, :business_domain, :owner, 1)
            ON CONFLICT(instance_id, database_name, table_name) DO UPDATE SET
                table_biz_desc = CASE WHEN ai_generated = 0 THEN table_biz_desc ELSE excluded.table_biz_desc END,
                business_domain = CASE WHEN ai_generated = 0 THEN business_domain ELSE excluded.business_domain END,
                owner = CASE WHEN ai_generated = 0 THEN owner ELSE excluded.owner END,
                ai_generated = CASE WHEN ai_generated = 0 THEN 0 ELSE 1 END,
                updated_at = CURRENT_TIMESTAMP
            """
        )
        await session.execute(
            sql,
            {
                "instance_id": instance_id,
                "database_name": table.database_name,
                "table_name": table.table_name,
                "table_biz_desc": enrich.table_biz_desc,
                "business_domain": enrich.business_domain,
                "owner": enrich.owner,
            },
        )

    async def _upsert_column_biz(self, session, instance_id, table, col, ce):
        sql = text(
            """
            INSERT INTO md_column_biz
                (instance_id, database_name, table_name, column_name, biz_desc, sensitivity, ai_generated)
            VALUES
                (:instance_id, :database_name, :table_name, :column_name, :biz_desc, :sensitivity, 1)
            ON CONFLICT(instance_id, database_name, table_name, column_name) DO UPDATE SET
                biz_desc = CASE WHEN ai_generated = 0 THEN biz_desc ELSE excluded.biz_desc END,
                sensitivity = CASE WHEN ai_generated = 0 THEN sensitivity ELSE excluded.sensitivity END,
                ai_generated = CASE WHEN ai_generated = 0 THEN 0 ELSE 1 END,
                updated_at = CURRENT_TIMESTAMP
            """
        )
        await session.execute(
            sql,
            {
                "instance_id": instance_id,
                "database_name": table.database_name,
                "table_name": table.table_name,
                "column_name": col.column_name,
                "biz_desc": ce.desc,
                "sensitivity": ce.sensitivity,
            },
        )

    async def _upsert_code_dict(
        self, session, instance_id, table, column_name, code_value, code_label
    ):
        sql = text(
            """
            INSERT INTO md_code_dict
                (instance_id, database_name, table_name, column_name, code_value, code_label, ai_generated)
            VALUES
                (:instance_id, :database_name, :table_name, :column_name, :code_value, :code_label, 1)
            ON CONFLICT(instance_id, database_name, table_name, column_name, code_value) DO UPDATE SET
                code_label = excluded.code_label,
                ai_generated = 1
            """
        )
        await session.execute(
            sql,
            {
                "instance_id": instance_id,
                "database_name": table.database_name,
                "table_name": table.table_name,
                "column_name": column_name,
                "code_value": str(code_value),
                "code_label": code_label,
            },
        )
