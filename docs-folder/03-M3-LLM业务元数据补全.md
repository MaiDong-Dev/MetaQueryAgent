# 03 · M3 LLM 业务元数据补全

## 一、实现目标

在技术元数据（M1/M2）基础上，用 LLM 补全**业务元数据**：

1. 表业务描述（注释为空时补全）；
2. 归属业务域（用户域/订单域/商品域/支付域等）；
3. 字段敏感标记（身份证/手机号/银行卡等，分等级）；
4. 枚举码值推断（`status` 类字段）；
5. 表负责人（可选）。

产出写入 `md_table_biz / md_column_biz / md_code_dict`，并带 `ai_generated` 标记供人工覆盖。

### 验收标准
- LLM 输出能稳定解析为结构化 JSON；
- 解析失败能重试，最终失败兜底为 null，不影响整批采集；
- 补全结果正确落库，并标记 `ai_generated=1`。

## 二、详细开发过程

### 步骤 1：建业务扩展表（`sql/003_create_biz_tables.sql`）

```sql
USE metadata_db;

CREATE TABLE md_table_biz (
  id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  instance_id     BIGINT UNSIGNED NOT NULL,
  database_name   VARCHAR(128) NOT NULL,
  table_name      VARCHAR(128) NOT NULL,
  table_biz_desc  VARCHAR(512) NULL COMMENT '表业务描述',
  business_domain VARCHAR(128) NULL COMMENT '业务域',
  owner           VARCHAR(128) NULL COMMENT '负责人',
  ai_generated    TINYINT NOT NULL DEFAULT 0 COMMENT '1=AI生成',
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_table_biz (instance_id, database_name, table_name)
) COMMENT='表业务扩展';

CREATE TABLE md_column_biz (
  id             BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  instance_id    BIGINT UNSIGNED NOT NULL,
  database_name  VARCHAR(128) NOT NULL,
  table_name     VARCHAR(128) NOT NULL,
  column_name    VARCHAR(128) NOT NULL,
  biz_desc       VARCHAR(512) NULL COMMENT '字段业务描述',
  sensitivity    VARCHAR(16) NULL COMMENT 'high/medium/low/null',
  business_domain VARCHAR(128) NULL,
  ai_generated   TINYINT NOT NULL DEFAULT 0,
  created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_column_biz (instance_id, database_name, table_name, column_name)
) COMMENT='字段业务扩展';

CREATE TABLE md_code_dict (
  id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  instance_id   BIGINT UNSIGNED NOT NULL,
  database_name VARCHAR(128) NOT NULL,
  table_name    VARCHAR(128) NOT NULL,
  column_name   VARCHAR(128) NOT NULL,
  code_value    VARCHAR(64) NOT NULL COMMENT '码值，如 0',
  code_label    VARCHAR(128) NULL COMMENT '含义，如 待支付',
  ai_generated  TINYINT NOT NULL DEFAULT 0,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_code (instance_id, database_name, table_name, column_name, code_value)
) COMMENT='枚举字典';
```

### 步骤 2：定义 LLM 输出校验模型（`agent/llm/schema.py`）

用 pydantic 严格约束输出结构，作为 JSON 校验与兜底依据：

```python
from pydantic import BaseModel

class ColumnEnrich(BaseModel):
    column_name: str
    sensitivity: str | None = None
    desc: str | None = None
    enum_values: dict[str, str] | None = None

class TableEnrich(BaseModel):
    table_biz_desc: str | None = None
    business_domain: str | None = None
    owner: str | None = None
    column_enrich: list[ColumnEnrich] = []
```

### 步骤 3：构造 Prompt（`agent/llm/prompt.py`）

约束模型只输出 JSON，不输出解释：

```python
SYSTEM_PROMPT = """
你是数据库元数据补全助手。根据给定的表名、字段名和类型，推断业务含义。

严格输出 JSON（不要 markdown 代码块、不要任何解释文字），结构如下：
{
  "table_biz_desc": "表业务描述",
  "business_domain": "业务域",
  "owner": null,
  "column_enrich": [
    {"column_name": "phone", "sensitivity": "high", "desc": "用户手机号"},
    {"column_name": "order_status", "enum_values": {"0": "待支付", "1": "已支付"}}
  ]
}

约束：
1. 只基于表名/字段名推断，不编造真实数据；
2. 无法判断的字段填 null，不要猜测；
3. sensitivity 取值仅限 high/medium/low/null；
4. 不要输出多余字段。
"""
```

### 步骤 4：LLM 客户端（`agent/llm/client.py`）

封装调用 + JSON 解析 + 校验 + 重试 + 兜底：

```python
import json
import httpx
from pydantic import ValidationError

class LlmClient:
    def __init__(self, base_url, api_key, model, max_retries=3):
        ...

    async def enrich_table(self, table_meta) -> TableEnrich:
        for attempt in range(self.max_retries):
            raw = await self._call(prompt)          # 调 DeepSeek
            try:
                data = json.loads(self._extract_json(raw))   # 剥掉可能的代码块
                return TableEnrich.model_validate(data)      # pydantic 校验
            except (json.JSONDecodeError, ValidationError):
                if attempt == self.max_retries - 1:
                    return TableEnrich()            # 兜底：返回空结构，不中断
        return TableEnrich()
```

> `_extract_json`：模型偶尔把 JSON 包在 ``` ```json ... ``` ``` 里，需先剥离。

### 步骤 5：分批补全（`agent/llm/enricher.py`）

大库不能一次全丢给 LLM，按表分批 + 并发限制：

```python
import asyncio

async def enrich_all(self, tables: list, batch_size=10, concurrency=3):
    sem = asyncio.Semaphore(concurrency)
    results = []
    for i in range(0, len(tables), batch_size):
        batch = tables[i:i+batch_size]
        results += await asyncio.gather(
            *(self._enrich_one(t, sem) for t in batch)
        )
    return results
```

### 步骤 6：写入业务表

补全结果写入 `md_table_biz / md_column_biz / md_code_dict`，`ai_generated=1`。

**人工覆盖机制**：当人工在平台修改后，把 `ai_generated` 置 0；下次同步时，`ai_generated=0` 的记录**不被 AI 重新覆盖**。

### 步骤 7：接入主流程

```python
# M2 diff 之后，只对"新增/修改"的表做补全，节省 token
changed_tables = diff.added_tables + diff.modified_tables
enriched = await enricher.enrich_all(changed_tables)
await biz_repo.save(enriched)
```

## 三、关键注意点

- **JSON 稳定性是最大风险**，务必 pydantic 校验 + 重试 + 兜底 null，任何单表失败都不能中断整批；
- **只传表名/字段名/类型**，不传真实数据，保护业务隐私；
- 注意 DeepSeek 的 token/QPS 限制，控制并发与批次大小；
- `ai_generated` 标记是实现"AI 结果可被人工覆盖"的关键，务必贯穿读写逻辑。

## 四、依赖变更

`pyproject.toml` 新增：`pydantic>=2`（M1 已加）、`httpx`（或改用 `openai` SDK）。执行 `uv add httpx`。
