# Agent 开发方案：基于 MySQL 业务库自动生成元数据表（已完善版）

整体目标：开发一个 Agent，**连接业务 MySQL，采集库表结构，自动写入自建元数据库的元数据表**，同时支持 AI 补全业务元数据（注释、业务域、敏感标记）。

> 架构：Agent + 采集模块 + LLM 推理模块 + 元数据库存储。
> 输出产物：一套 `md_*` 元数据表。

## 一、核心问题

1. 技术元数据：直接读 MySQL 系统表，不需要大模型；
2. 业务元数据：MySQL 注释经常为空，交给 LLM 补全；
3. 增量采集：不是每次全量覆盖，识别新增/修改/删除的表、字段；
4. 多实例支持：管理多个业务 MySQL 实例；
5. 变更记录：DDL 变化写入变更日志表；
6. 输出：完整可使用的数据字典。

## 二、整体架构

```
业务MySQL(待采集)
      ↓
采集器：读取 information_schema
      ↓
Agent核心：
  1）结构化原始元数据
  2）调用LLM生成业务元数据（业务注释、敏感标签、业务域、枚举）
  3）去重、对比变更（DDL变更检测）
      ↓
写入【自建元数据库 metadata_db】，写入 md_database / md_table / md_column …元数据表
```

## 三、技术栈选型（已对齐现有代码，不再变更）

| 模块 | 选型 | 说明 |
|---|---|---|
| 数据库驱动 | `aiomysql` + `SQLAlchemy async` | **与现有 `client/mysql_client_manager.py` 保持一致，禁止混入同步 `pymysql`** |
| 元数据库 ORM | `SQLAlchemy`（异步） | 操作 `metadata_db` |
| Agent 框架 | **初期：普通 async 流程函数；后续功能复杂再引入 `LangGraph`** | 先不引入重框架，避免过早复杂化 |
| LLM | DeepSeek（`conf.yaml` 已配 `deepseek-v4-flash`） | 负责业务元数据推断 |
| 向量库 | Milvus（**保留，后续阶段启用**） | 用于字段语义相似度归类业务域 |
| 配置管理 | `OmegaConf` + `dataclass` | 与现有 `config/client_conf.py` 一致，扩展 `InstanceConf` |

> 说明：现有基础设施已就绪 —— `client/mysql_client_manager.py`（async engine/session 生命周期）、`config/client_conf.py`（配置结构体）、`agent/database_service.py`（库表清单服务）。Agent 在此之上迭代，不重复造轮子。

## 四、Agent 执行流程

定义流转数据状态：

```python
class MetaAgentState(TypedDict):
    instance_id: str                 # 业务实例ID
    connection_conf: dict            # 业务库连接配置 host port user password db
    raw_schemas: List[dict]          # 从 information_schema 拉出的原始技术元数据
    enrich_schemas: List[dict]       # LLM 补全后的业务元数据
    diff_result: dict                # 与元数据库对比的差异：新增/更新/删除表、字段
    crawl_time: datetime             # 采集时间
```

### 步骤 1：连接业务 MySQL，采集原始技术元数据（无 LLM）

直接查询 `information_schema`：`SCHEMATA`、`TABLES`、`COLUMNS`、`STATISTICS`、`KEY_COLUMN_USAGE`、`PARTITIONS`。

> 关键点：过滤系统库 `information_schema, mysql, sys, performance_schema`。

**采集必须包含的字段细节（MySQL 8）：**
- 表：`TABLE_TYPE`（区分表/视图）、`ENGINE`、`TABLE_COMMENT`、字符集/排序规则；
- 列：`COLUMN_DEFAULT`、`IS_NULLABLE`、`CHARACTER_SET_NAME`、`COLLATION_NAME`、`EXTRA`（自增/生成列）、`COLUMN_COMMENT`；
- 索引/约束：`STATISTICS`（索引名、唯一性、列顺序）、`KEY_COLUMN_USAGE`（主外键约束）。

### 步骤 2：Agent 差异比对（增量同步核心）

本次采集结果与元数据库 `md_table`、`md_column` 对比：

- 新增表/字段；
- 修改：字段类型、长度、注释发生变更；
- 删除：业务库已不存在，标记 `is_deleted=1`，**不物理删除**。

输出 `diff_result`，后续只处理变更部分。

### 步骤 3：LLM 补全业务元数据（智能核心）

输入：表名、表注释、字段列表（字段名、字段类型），**不传真实业务数据**。

**Prompt 目标：让模型输出结构化 JSON，不要自然语言。**

需推断内容：
1. 表业务描述（原注释为空时补全）；
2. 归属业务域：用户域 / 订单域 / 商品域 / 支付域等；
3. 字段敏感标记：身份证、手机号、银行卡（敏感等级）；
4. 枚举码值推断：`status` 类字段推测枚举含义；
5. 表负责人（可选）。

> ⚠️ 约束：不要编造真实业务数据；仅基于表名/字段名推理；无法判断返回 null。

模型输出 JSON 示例：

```json
{
  "table_biz_desc": "订单主表，存储用户下单基础信息",
  "business_domain": "订单域",
  "column_enrich": [
    {"column_name": "phone", "sensitivity": "high", "desc": "用户手机号"},
    {"column_name": "order_status", "enum_values": {"0": "待支付", "1": "已支付", "2": "已取消"}}
  ]
}
```

### 步骤 4：写入元数据库

根据 `diff_result`，把【技术元数据 + LLM 业务元数据】写入元数据表，DDL 变更写入 `md_change_log`。

### 步骤 5：返回采集报告

输出：多少张表新增、多少字段变更、多少业务元数据被 AI 补全。

## 五、关键设计决策（重点，务必先定死）

### 1. LLM 输出稳定性（最大风险）
- 要求结构化 JSON，仍会偶发格式错误/漏字段/多余解释文字；
- **必须**：输出约束 + 强制 JSON 解析 + **pydantic 做 schema 校验**；
- 不合法则重试（最多 N 次），失败兜底为 `null`，**绝不能中断整批采集**。

### 2. 增量唯一键
- `md_table` 唯一键 = `(instance_id, database_name, table_name)`；
- `md_column` 唯一键 = 表键 + `column_name`；
- 字段类型/长度/注释任一变化都算"修改"，删除走 `is_deleted=1` 软删除。

### 3. LLM 分批与限流
- 大库上千张表，按**表**分批（如每批 10~20 张）；
- 加并发限制、失败重试；
- 注意 DeepSeek token/QPS 限制，控制成本。

### 4. `ai_generated` 人工覆盖标记
- 字段 `ai_generated: bool` 标记 AI 生成；
- 人工可在平台修正并覆盖 AI 结果，覆盖后标记为非 AI 生成，防止后续同步再被 AI 覆盖。

### 5. 安全与隐私
- 采集账号单独创建只读账号（仅 `SELECT` 权限），不用 `root`；
- 只传表名/字段名给 LLM，不传真实数据。

## 六、元数据表设计（metadata_db）

核心必选：
1. `md_instance` —— 管理多个 MySQL 实例配置；
2. `md_database` —— 库信息；
3. `md_table` —— 表技术元数据；
4. `md_column` —— 字段技术元数据；
5. `md_index` —— 索引；
6. `md_table_biz` —— 表业务扩展；
7. `md_column_biz` —— 字段业务扩展（含敏感标记、业务域、AI 标记）；
8. `md_code_dict` —— 枚举字典；
9. `md_change_log` —— DDL 变更记录。

> 初期不做血缘、数据质量表；`md_constraint`/`md_index`/`md_partition` 可视需要延后。

## 七、分阶段实施路线（里程碑）

- **M1（先跑通采集链路）**：建 `md_instance / md_database / md_table / md_column` + `information_schema` 采集器（纯技术元数据，无 LLM）；
- **M2（增量同步）**：差异比对 + `md_change_log`；
- **M3（智能补全）**：LLM 补全业务元数据，写 `md_table_biz / md_column_biz / md_code_dict`，加 JSON 校验重试 + `ai_generated` 标记；
- **M4（多实例 + 报告）**：多实例管理 + 采集报告输出；
- **M5（向量库增强）**：引入 Milvus，字段语义相似度归类业务域，提升业务域识别准确率；
- **M6（Agent 化，可选）**：功能复杂后引入 LangGraph，支持工具调用、状态持久化、断点续跑。

## 八、极简伪代码

```python
# 1. 连接业务 mysql，拉取 information_schema
raw_meta = fetch_mysql_metadata(db_conf)

# 2. 对比元数据库获取变更
diff = compare_with_meta_db(raw_meta)

# 3. Agent 调用 LLM 批量补全业务元信息（分批 + 校验重试）
enriched_meta = llm_enrich_agent(diff["changed_tables"])

# 4. 写入元数据库
persist_to_metadata_db(enriched_meta, diff)
```

## 九、后续扩展方向

1. SQL 解析能力：解析 ETL SQL 生成血缘元数据 `md_lineage_table`、`md_lineage_column`；
2. 数据质量规则自动推荐 Agent；
3. 对外 API：导出数据字典 markdown；
4. 引入 LangGraph 构建完整 Agent（状态管理、工具调用、日志、状态持久化）。
