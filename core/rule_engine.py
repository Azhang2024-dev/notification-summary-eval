"""
rule_engine.py
--------------
规则引擎：负责加载规则文件并对单条数据执行所有规则，返回每条规则的评测结果。

规则文件格式（YAML）示例见 rules/ 目录。
每条规则支持以下类型：
  - regex      : 正则表达式匹配
  - not_empty  : 字段非空检查
  - length     : 字段长度范围检查
  - contains   : 字段包含指定子串
  - not_contains: 字段不包含指定子串
  - custom     : 调用外部 Python 函数（需在 rules/ 下提供同名 .py 文件）
"""

import re
import importlib.util
import os
from typing import Any

import yaml


class RuleLoadError(Exception):
    """规则文件加载失败"""


class RuleEngine:
    def __init__(self, rule_file: str):
        """
        Parameters
        ----------
        rule_file : str
            YAML 规则文件路径
        """
        self.rule_file = rule_file
        self.rules: list[dict] = []
        self._load_rules()

    # ------------------------------------------------------------------
    # 加载
    # ------------------------------------------------------------------
    def _load_rules(self) -> None:
        if not os.path.isfile(self.rule_file):
            raise RuleLoadError(f"规则文件不存在: {self.rule_file}")
        with open(self.rule_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict) or "rules" not in data:
            raise RuleLoadError("规则文件格式错误：顶层必须包含 'rules' 键")
        self.rules = data["rules"]
        # 预编译正则
        for rule in self.rules:
            if rule.get("type") == "regex" and "pattern" in rule:
                rule["_compiled"] = re.compile(rule["pattern"], re.DOTALL)

    # ------------------------------------------------------------------
    # 评测单条记录
    # ------------------------------------------------------------------
    def evaluate(self, record: dict) -> list[dict]:
        """
        对一条数据记录执行所有规则。

        Returns
        -------
        list[dict]
            每个元素对应一条规则的结果：
            {
                "rule_id"   : str,
                "rule_name" : str,
                "field"     : str,
                "passed"    : bool,
                "message"   : str,
                "severity"  : str   # "error" | "warning" | "info"
            }
        """
        results = []
        for rule in self.rules:
            result = self._apply_rule(rule, record)
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # 单条规则执行
    # ------------------------------------------------------------------
    def _apply_rule(self, rule: dict, record: dict) -> dict:
        rule_id   = rule.get("id", "unknown")
        rule_name = rule.get("name", rule_id)
        field     = rule.get("field", "")
        severity  = rule.get("severity", "error")
        rtype     = rule.get("type", "")

        base = {
            "rule_id"   : rule_id,
            "rule_name" : rule_name,
            "field"     : field,
            "severity"  : severity,
        }

        try:
            value = self._get_field(record, field)
            passed, message = self._check(rtype, rule, value, record)
        except Exception as exc:  # noqa: BLE001
            passed  = False
            message = f"规则执行异常: {exc}"

        return {**base, "passed": passed, "message": message}

    # ------------------------------------------------------------------
    # 字段取值（支持点号路径，如 "meta.author"）
    # ------------------------------------------------------------------
    @staticmethod
    def _get_field(record: dict, field: str) -> Any:
        if not field:
            return record
        parts = field.split(".")
        val = record
        for part in parts:
            if isinstance(val, dict):
                val = val.get(part)
            else:
                return None
        return val

    # ------------------------------------------------------------------
    # 规则类型分发
    # ------------------------------------------------------------------
    def _check(self, rtype: str, rule: dict, value: Any, record: dict) -> tuple[bool, str]:
        if rtype == "not_empty":
            return self._check_not_empty(value, rule)
        elif rtype == "regex":
            return self._check_regex(value, rule)
        elif rtype == "length":
            return self._check_length(value, rule)
        elif rtype == "contains":
            return self._check_contains(value, rule)
        elif rtype == "not_contains":
            return self._check_not_contains(value, rule)
        elif rtype == "custom":
            return self._check_custom(value, rule, record)
        else:
            return False, f"未知规则类型: {rtype}"

    # ------------------------------------------------------------------
    # 各类型实现
    # ------------------------------------------------------------------
    @staticmethod
    def _check_not_empty(value: Any, rule: dict) -> tuple[bool, str]:
        passed = value is not None and str(value).strip() != ""
        msg = rule.get("message_pass", "字段非空 ✓") if passed else rule.get("message_fail", "字段为空或缺失")
        return passed, msg

    @staticmethod
    def _check_regex(value: Any, rule: dict) -> tuple[bool, str]:
        compiled = rule.get("_compiled")
        if compiled is None:
            compiled = re.compile(rule.get("pattern", ""), re.DOTALL)
        text = str(value) if value is not None else ""
        passed = bool(compiled.search(text))
        msg = rule.get("message_pass", "正则匹配成功 ✓") if passed else rule.get("message_fail", f"不符合正则: {rule.get('pattern')}")
        return passed, msg

    @staticmethod
    def _check_length(value: Any, rule: dict) -> tuple[bool, str]:
        text = str(value) if value is not None else ""
        length = len(text)
        min_len = rule.get("min", 0)
        max_len = rule.get("max", float("inf"))
        passed = min_len <= length <= max_len
        msg = (
            rule.get("message_pass", f"长度 {length} 符合要求 ✓")
            if passed
            else rule.get("message_fail", f"长度 {length} 不在 [{min_len}, {max_len}] 范围内")
        )
        return passed, msg

    @staticmethod
    def _check_contains(value: Any, rule: dict) -> tuple[bool, str]:
        text = str(value) if value is not None else ""
        keyword = rule.get("keyword", "")
        passed = keyword in text
        msg = rule.get("message_pass", f"包含关键词 '{keyword}' ✓") if passed else rule.get("message_fail", f"未包含关键词 '{keyword}'")
        return passed, msg

    @staticmethod
    def _check_not_contains(value: Any, rule: dict) -> tuple[bool, str]:
        text = str(value) if value is not None else ""
        keyword = rule.get("keyword", "")
        passed = keyword not in text
        msg = rule.get("message_pass", f"不含禁用词 '{keyword}' ✓") if passed else rule.get("message_fail", f"包含禁用词 '{keyword}'")
        return passed, msg

    def _check_custom(self, value: Any, rule: dict, record: dict) -> tuple[bool, str]:
        """
        加载 rules/<func_module>.py 并调用其中的 evaluate(value, record, rule) 函数。
        """
        func_module = rule.get("func_module", "")
        rules_dir = os.path.dirname(self.rule_file)
        module_path = os.path.join(rules_dir, f"{func_module}.py")
        if not os.path.isfile(module_path):
            return False, f"自定义模块不存在: {module_path}"
        spec = importlib.util.spec_from_file_location(func_module, module_path)
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if not hasattr(mod, "evaluate"):
            return False, f"模块 {func_module} 中未找到 evaluate() 函数"
        return mod.evaluate(value, record, rule)
