"""M4 采集报告"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class SyncReport:
    """单实例一次同步的报告"""

    instance_name: str
    added_tables: int = 0
    modified_tables: int = 0
    deleted_tables: int = 0
    added_columns: int = 0
    modified_columns: int = 0
    deleted_columns: int = 0
    enriched_tables: int = 0
    enriched_columns: int = 0
    llm_failed: int = 0
    vectors_written: int = 0
    vectors_error: str | None = None
    error: str | None = None
    crawl_time: str = ""

    def __post_init__(self):
        if not self.crawl_time:
            self.crawl_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def format(self) -> str:
        lines = [
            "========== 采集报告 ==========",
            f"实例: {self.instance_name}",
            f"时间: {self.crawl_time}",
        ]
        if self.error:
            lines.append(f"状态: 失败 ({self.error})")
        else:
            lines.append(f"新增表: {self.added_tables}")
            lines.append(f"修改表: {self.modified_tables}")
            lines.append(f"删除表: {self.deleted_tables}")
            lines.append(f"新增字段: {self.added_columns}")
            lines.append(f"修改字段: {self.modified_columns}")
            lines.append(f"删除字段: {self.deleted_columns}")
            lines.append(f"AI 补全表: {self.enriched_tables} / 失败: {self.llm_failed}")
            lines.append(f"向量写入: {self.vectors_written} 条")
            if self.vectors_error:
                lines.append(f"向量错误: {self.vectors_error}")
        lines.append("==============================")
        return "\n".join(lines)
