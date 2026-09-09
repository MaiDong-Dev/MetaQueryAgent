"""M2：增量同步差异比对器

diff() 为纯比对逻辑（不碰数据库），sync() 负责编排
「读现有记录 → 比对 → 应用差异」，数据库读写由 agent.repo.meta_repo 完成。
"""

from dataclasses import dataclass, field

from agent.collector.models import ColumnMeta, DatabaseMeta, TableMeta


@dataclass
class DiffResult:
    """一次采集与元数据库的差异集合"""

    added_tables: list[TableMeta] = field(default_factory=list)
    modified_tables: list[tuple[TableMeta, TableMeta]] = field(default_factory=list)  # (old, new)
    deleted_tables: list[TableMeta] = field(default_factory=list)  # old
    added_columns: list[tuple[str, str, ColumnMeta]] = field(default_factory=list)  # (db, table, col)
    modified_columns: list[tuple[str, str, ColumnMeta, ColumnMeta]] = field(default_factory=list)  # (db, table, old, new)
    deleted_columns: list[tuple[str, str, ColumnMeta]] = field(default_factory=list)  # (db, table, old col)

    @property
    def has_changes(self) -> bool:
        return any([
            self.added_tables, self.modified_tables, self.deleted_tables,
            self.added_columns, self.modified_columns, self.deleted_columns,
        ])

    def summary(self) -> dict:
        return {
            "added_tables": len(self.added_tables),
            "modified_tables": len(self.modified_tables),
            "deleted_tables": len(self.deleted_tables),
            "added_columns": len(self.added_columns),
            "modified_columns": len(self.modified_columns),
            "deleted_columns": len(self.deleted_columns),
        }


class Differ:
    """差异比对器"""

    def __init__(self, repo):
        self.repo = repo
        self.instance_id = None

    async def sync(self, instance_conf, metas: list[DatabaseMeta]) -> DiffResult:
        """完整增量同步：读现有 → 比对 → 应用，返回差异集合"""
        self.instance_id = await self.repo.get_or_create_instance(instance_conf)
        old_tables, old_columns = await self.repo.load_existing(self.instance_id)
        diff = self.diff(metas, old_tables, old_columns)
        await self.repo.apply_diff(self.instance_id, metas, diff)
        return diff

    def diff(
        self,
        metas: list[DatabaseMeta],
        old_tables: dict[tuple[str, str], TableMeta],
        old_columns: dict[tuple[str, str, str], ColumnMeta],
    ) -> DiffResult:
        """纯比对：返回差异集合"""
        result = DiffResult()

        new_tables: dict[tuple[str, str], TableMeta] = {}
        for db in metas:
            for t in db.tables:
                new_tables[(t.database_name, t.table_name)] = t

        # 表级对比
        for key, new_t in new_tables.items():
            if key not in old_tables:
                result.added_tables.append(new_t)
            else:
                old_t = old_tables[key]
                if self._table_changed(old_t, new_t):
                    result.modified_tables.append((old_t, new_t))
                # 仅对「两边都存在的表」做字段级对比
                self._diff_columns(key, new_t, old_columns, result)

        for key, old_t in old_tables.items():
            if key not in new_tables:
                result.deleted_tables.append(old_t)

        return result

    def _diff_columns(self, table_key, new_t: TableMeta, old_columns, result: DiffResult):
        db, tbl = table_key
        new_cols = {c.column_name: c for c in new_t.columns}
        old_cols = {
            col_name: col
            for (d, t, col_name), col in old_columns.items()
            if d == db and t == tbl
        }

        for name, new_c in new_cols.items():
            if name not in old_cols:
                result.added_columns.append((db, tbl, new_c))
            elif self._column_changed(old_cols[name], new_c):
                result.modified_columns.append((db, tbl, old_cols[name], new_c))

        for name, old_c in old_cols.items():
            if name not in new_cols:
                result.deleted_columns.append((db, tbl, old_c))

    @staticmethod
    def _table_changed(old: TableMeta, new: TableMeta) -> bool:
        # 表属性对比（排除 columns/indexes，这些单独做字段级对比）
        return old.model_dump(exclude={"columns", "indexes"}) != new.model_dump(
            exclude={"columns", "indexes"}
        )

    @staticmethod
    def _column_changed(old: ColumnMeta, new: ColumnMeta) -> bool:
        # 字段顺序(ordinal_position)变化不算业务变更，排除掉
        return old.model_dump(exclude={"ordinal_position"}) != new.model_dump(
            exclude={"ordinal_position"}
        )
