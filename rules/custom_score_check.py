"""
rules/custom_score_check.py
---------------------------
自定义规则示例：检查 score 字段是否在指定范围内。

所有自定义规则模块必须实现：
    evaluate(value, record, rule) -> tuple[bool, str]

Parameters
----------
value  : 当前字段的值（已从 record 中提取）
record : 完整的数据行 dict
rule   : 规则配置 dict（来自 YAML）

Returns
-------
(passed: bool, message: str)
"""


def evaluate(value, record: dict, rule: dict) -> tuple[bool, str]:
    min_score = rule.get("min_score", 0)
    max_score = rule.get("max_score", 100)

    if value is None or str(value).strip() == "":
        return False, "评分字段为空"

    try:
        score = float(value)
    except (ValueError, TypeError):
        return False, f"评分值 '{value}' 无法转换为数字"

    if min_score <= score <= max_score:
        return True, f"评分 {score} 在合规范围 [{min_score}, {max_score}] ✓"
    else:
        return False, f"评分 {score} 超出范围 [{min_score}, {max_score}]"
