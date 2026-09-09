"""M3 LLM Prompt 构造"""

SYSTEM_PROMPT = """你是数据库元数据补全助手。根据给定的表名、字段名和类型，推断业务含义。

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
1. 只基于表名/字段名推断，不编造真实业务数据；
2. 无法判断的字段填 null，不要猜测；
3. sensitivity 取值仅限 high / medium / low / null；
4. 不要输出多余字段。
"""


def build_user_prompt(table) -> str:
    """根据表结构构造用户提示：只传表名/字段名/类型，不传真实数据"""
    lines = [
        f"数据库: {table.database_name}",
        f"表名: {table.table_name}",
    ]
    if table.table_comment:
        lines.append(f"表注释: {table.table_comment}")
    lines.append("字段列表:")
    for col in table.columns:
        lines.append(f"  - {col.column_name} ({col.column_type or col.data_type})")
    return "\n".join(lines)
