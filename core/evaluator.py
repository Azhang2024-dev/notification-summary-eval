"""
evaluator.py
------------
评测执行模块：将数据加载、规则引擎、结果汇总串联起来，
对整个数据集执行评测并返回结构化结果。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from core.data_loader import DataLoader
from core.rule_engine import RuleEngine


# ------------------------------------------------------------------
# 数据结构
# ------------------------------------------------------------------

@dataclass
class RecordResult:
    """单条记录的评测结果"""
    row_index : int
    record    : dict
    rule_results: list[dict]          # 来自 RuleEngine.evaluate()
    passed    : bool = field(init=False)
    error_count  : int = field(init=False)
    warning_count: int = field(init=False)

    def __post_init__(self):
        self.error_count   = sum(1 for r in self.rule_results if not r["passed"] and r["severity"] == "error")
        self.warning_count = sum(1 for r in self.rule_results if not r["passed"] and r["severity"] == "warning")
        self.passed = self.error_count == 0


@dataclass
class EvalSummary:
    """整体评测摘要"""
    total_records  : int = 0
    passed_records : int = 0
    failed_records : int = 0
    total_errors   : int = 0
    total_warnings : int = 0
    pass_rate      : float = 0.0
    elapsed_seconds: float = 0.0
    rule_stats     : dict = field(default_factory=dict)
    # rule_stats 结构: { rule_id: {"pass": int, "fail": int} }


@dataclass
class EvalReport:
    """完整评测报告"""
    summary : EvalSummary
    records : list[RecordResult]


# ------------------------------------------------------------------
# 评测器
# ------------------------------------------------------------------

class Evaluator:
    def __init__(
        self,
        data_file : str,
        rule_file : str,
        sheet_name: Optional[str | int] = 0,
        encoding  : str = "utf-8-sig",
    ):
        self.loader = DataLoader(data_file, sheet_name=sheet_name, encoding=encoding)
        self.engine = RuleEngine(rule_file)

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------
    def run(self) -> EvalReport:
        t0 = time.perf_counter()

        records = self.loader.load()
        record_results: list[RecordResult] = []
        rule_stats: dict[str, dict] = {}

        for rec in records:
            row_idx = rec.get("_row_index", 0)
            rule_results = self.engine.evaluate(rec)
            rr = RecordResult(
                row_index    = row_idx,
                record       = rec,
                rule_results = rule_results,
            )
            record_results.append(rr)

            # 累计规则统计
            for r in rule_results:
                rid = r["rule_id"]
                if rid not in rule_stats:
                    rule_stats[rid] = {"name": r["rule_name"], "pass": 0, "fail": 0}
                if r["passed"]:
                    rule_stats[rid]["pass"] += 1
                else:
                    rule_stats[rid]["fail"] += 1

        elapsed = time.perf_counter() - t0

        # 汇总
        total   = len(record_results)
        passed  = sum(1 for r in record_results if r.passed)
        failed  = total - passed
        errors  = sum(r.error_count   for r in record_results)
        warnings= sum(r.warning_count for r in record_results)

        summary = EvalSummary(
            total_records   = total,
            passed_records  = passed,
            failed_records  = failed,
            total_errors    = errors,
            total_warnings  = warnings,
            pass_rate       = round(passed / total * 100, 2) if total else 0.0,
            elapsed_seconds = round(elapsed, 3),
            rule_stats      = rule_stats,
        )

        return EvalReport(summary=summary, records=record_results)
