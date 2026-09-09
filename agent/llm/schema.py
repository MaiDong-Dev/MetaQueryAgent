"""M3 LLM 输出校验模型（pydantic）

约束 LLM 输出的结构化 JSON，作为解析校验与兜底依据。
"""

from pydantic import BaseModel, Field


class ColumnEnrich(BaseModel):
    """单字段的业务补全结果"""
    column_name: str
    sensitivity: str | None = None        # high / medium / low / null
    desc: str | None = None
    enum_values: dict[str, str] | None = None   # 枚举码值 -> 含义


class TableEnrich(BaseModel):
    """单表的业务补全结果"""
    table_biz_desc: str | None = None
    business_domain: str | None = None
    owner: str | None = None
    column_enrich: list[ColumnEnrich] = Field(default_factory=list)
