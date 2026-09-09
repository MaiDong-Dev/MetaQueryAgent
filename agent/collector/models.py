"""M1 采集器的 pydantic 数据规约（结构化模型）

与采集逻辑分离：本文件只定义数据模型，不包含任何 SQL / IO 逻辑。
采集逻辑见 agent.collector.schema_collector。
"""

from pydantic import BaseModel, Field


class IndexMeta(BaseModel):
    """索引元数据"""
    index_name: str
    non_unique: bool
    seq_in_index: int
    column_name: str | None = None
    index_type: str | None = None


class ColumnMeta(BaseModel):
    """字段技术元数据"""
    column_name: str
    ordinal_position: int | None = None
    column_default: str | None = None
    is_nullable: str | None = None
    data_type: str | None = None
    column_type: str | None = None
    char_max_length: int | None = None
    numeric_precision: int | None = None
    numeric_scale: int | None = None
    charset: str | None = None
    collation: str | None = None
    column_extra: str | None = None
    column_comment: str | None = None


class TableMeta(BaseModel):
    """表技术元数据"""
    database_name: str
    table_name: str
    table_type: str | None = None
    engine: str | None = None
    table_comment: str | None = None
    charset: str | None = None
    collation: str | None = None
    columns: list[ColumnMeta] = Field(default_factory=list)
    indexes: list[IndexMeta] = Field(default_factory=list)


class DatabaseMeta(BaseModel):
    """库技术元数据"""
    database_name: str
    charset: str | None = None
    collation: str | None = None
    tables: list[TableMeta] = Field(default_factory=list)
