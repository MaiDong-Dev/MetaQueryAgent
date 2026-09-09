# 07 · M7 指标 / 同义词 / 取值样本 + SchemaRAG 演进规划

## 一、背景与目标

参照 NL2SQLAgent 的元知识体系，为 Meta-Builder-Agent 补齐三大能力，使其从「元数据底座」逐步进化为「NL2SQL 可查询的数据智能体」。

| 能力 | 借鉴来源 | 价值 |
|---|---|---|
| 指标定义（metric） | NL2SQLAgent `MetricInfo` | 沉淀业务口径，是 NL2SQL 最核心的知识 |
| 字段同义词（alias） | NL2SQLAgent `ColumnInfo.alias` | 提升检索命中率 |
| 字段取值样本（examples） | NL2SQLAgent `ColumnInfo.examples` | 检索 + 生成 SQL 的 few-shot 依据 |

后续方向：SchemaRAG（schema 结构 + 向量召回）→ NL2SQL（召回 → 生成 SQL → 校验 → 执行）。

## 二、现状盘点

### 已有元数据（SQLite `md_*` 表）

**技术元数据**（SQL 采集 information_schema）：
- `md_instance` / `md_database` / `md_table` / `md_column` / `md_index` / `md_change_log`

**业务元数据**（LLM 补全，M3）：
- `md_table_biz`：表描述、业务域、负责人
- `md_column_biz`：字段描述、敏感度、业务域
- `md_code_dict`：枚举码值 → 含义

**向量库**（Milvus，M5）：
- `column_domain`：字段语义向量（`db table column` → `business_domain`）

### 差距

| 能力 | 现状 |
|---|---|
| 指标 metric | ❌ 无 |
| 字段同义词 alias | ❌ 无 |
| 字段取值样本 examples | ❌ 无（仅有 LLM 推断的 `enum_values` 码值字典，非实际采样） |

## 三、三大能力设计

### 3.1 字段同义词（alias）

**采集方式**：LLM 生成（由字段名 + 表注释 + 字段注释推断同义表达）。

**表结构**（独立表，一别名一行，便于人工增删）：

```sql
CREATE TABLE IF NOT EXISTS md_column_alias (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  instance_id   INTEGER NOT NULL,
  database_name TEXT NOT NULL,
  table_name    TEXT NOT NULL,
  column_name   TEXT NOT NULL,
  alias         TEXT NOT NULL,
  source        TEXT NOT NULL DEFAULT 'ai',   -- ai / manual
  created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(instance_id, database_name, table_name, column_name, alias)
);
```

**写入方式**：扩展 `ColumnEnrich` 增加 `aliases: list[str] | None`，`save_enrichments` 时逐条 upsert（沿用 `ai_generated` 保护思路，人工改过则不覆盖）。

### 3.2 字段取值样本（examples）

**采集方式**：SQL 采样（`SELECT DISTINCT col FROM t LIMIT N`）+ 可选 LLM 标注业务含义。

> 关键差异：`md_code_dict` 是 LLM **推断**的枚举码值；`md_column_value` 是**实际采样**的真实取值，两者互补。

**采样策略**（避免大表慢查询）：
1. 仅对「低基数」字段采样：`varchar`/`char`/`enum`/`int`/`tinyint` 等，跳过 `text`/`blob`/`json`/大字段；
2. 先 `SELECT COUNT(DISTINCT col)` 判断基数，基数 > 阈值（如 1000）则不采样；
3. 每字段取 Top-N（默认 20）distinct 值，附频次。

**表结构**：

```sql
CREATE TABLE IF NOT EXISTS md_column_value (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  instance_id   INTEGER NOT NULL,
  database_name TEXT NOT NULL,
  table_name    TEXT NOT NULL,
  column_name   TEXT NOT NULL,
  value_text    TEXT NOT NULL,
  value_label   TEXT,                          -- LLM 标注的业务含义（可选）
  freq          INTEGER,
  source        TEXT NOT NULL DEFAULT 'sample', -- sample / ai / manual
  created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(instance_id, database_name, table_name, column_name, value_text)
);
```

### 3.3 指标定义（metric）

**采集方式**：LLM **库级**推断 + **人工审批**（借鉴 `MetricInfo` + approve/revoke）。

> 关键点：指标是**跨表**的业务口径（如「销售额 = SUM(order.amount)」），不能在「逐表补全」里生成，需独立的**库级指标推断节点**。

**表结构**：

```sql
CREATE TABLE IF NOT EXISTS md_metric (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  instance_id      INTEGER NOT NULL,
  metric_name      TEXT NOT NULL,
  metric_desc      TEXT,
  business_domain  TEXT,
  relevant_columns TEXT,                        -- JSON 数组，如 ["order.amount","customer.name"]
  metric_expr      TEXT,                        -- 表达式/SQL 片段，如 "SUM(order.amount)"
  aliases          TEXT,                        -- JSON 数组，指标别名
  status           TEXT NOT NULL DEFAULT 'pending', -- pending / approved / revoked
  ai_generated     INTEGER NOT NULL DEFAULT 1,
  created_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(instance_id, metric_name)
);
```

**审批机制**（借鉴 approve/revoke）：
- LLM 生成 → `pending`；
- 仅 `approved` 指标进入向量库、参与召回；
- 人工 `revoke` 下线。

## 四、向量库扩展（三路召回，对齐 SchemaRAG）

现有 `column_domain` 单路，扩展为三路：

| 集合 | 内容 | 用途 |
|---|---|---|
| `column_domain`（已有） | 字段名 + 别名 + 描述 → 业务域 | 字段语义召回 |
| `metric`（新增） | 指标名 + 别名 + 描述 → 指标 | 指标召回 |
| `column_value`（新增，内存索引） | 字段取值 → 字段 | 取值精确/子串匹配召回 |

> `column_value` 建议用**内存索引**（启动时装载，字典/前缀树），不用向量——取值是精确匹配，向量反而浪费且不准确（对齐 NL2SQLAgent 的 `value_index` 内存索引做法）。

## 五、SchemaRAG 演进方向

SchemaRAG 核心 = **schema 结构感知 + 检索增强**。分三层落地：

1. **召回层**：字段向量 + 指标向量 + 取值索引三路召回（M7 建好）；
2. **裁剪层**：LLM 对召回结果裁剪，保留最相关表/字段/指标；
3. **生成层**：基于裁剪后的 schema 生成 SQL（后续新增 `generate_sql` / `validate_sql` / `execute_sql` 节点）。

这与 NL2SQLAgent 的 `recall → filter → generate → validate → execute` 拓扑一致，直接复用现有 LangGraph 节点结构（`nodes/` 目录加节点 + `graph.py` 加边即可）。

## 六、实施顺序（建议分 5 个阶段）

| 阶段 | 内容 | 产出 |
|---|---|---|
| 1 | 扩展建表 SQL | `md_column_alias` / `md_column_value` / `md_metric` 三张表 |
| 2 | 扩展 LLM 补全 | `ColumnEnrich.aliases` + 库级指标推断 prompt/节点 |
| 3 | 新增采样采集器 | `ValueSampler`（distinct 采样，独立于 information_schema） |
| 4 | 扩展 repo + 向量 | alias/value/metric 写入 SQLite；指标向量写 Milvus |
| 5 | 审批 + 查询接口 | metric approve/revoke API + 查询展示 |

## 七、待确认决策点

1. **指标审批**：是否引入「人工审批」（approve/revoke），还是纯 LLM 自动生成直接可用？
2. **取值采样范围**：默认 Top-N=20、基数阈值=1000，是否合理？是否需要每字段可配置？
3. **三路召回的接入时机**：先只落表结构 + 写入，还是同步把 `search_domain` 扩展成三路召回接进主流程？
