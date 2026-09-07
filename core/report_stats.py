"""
core/report_stats.py
--------------------
解析已评测的 Excel 文件，计算各模型统计数据：
  - 总行数、平均分、badcase 数量/占比
  - badcase 的问题类型分布

兼容 gui_eval.py 生成的两种输出格式：
  格式 A（ExcelOutputBuilder）：score_{model}、问题标签、comment_{model}
  格式 B（ExcelWriter）：        每个模型块包含 score_r1、问题标签_r1、comment_r1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

VALID_ISSUE_TYPES = ["风格偏离", "重点不突出", "信息冗余", "低价值信息", "其他"]
BADCASE_THRESHOLD = 3   # 分数 < 3 计为 badcase（不含 3 分）
META_COLS         = 5   # id | app_type | app_name | title | content（元数据列数）


@dataclass
class ModelStats:
    name          : str
    total         : int   = 0
    score_sum     : float = 0.0
    badcase_count : int   = 0
    issue_counts  : dict  = field(
        default_factory=lambda: {t: 0 for t in VALID_ISSUE_TYPES})

    @property
    def avg_score(self) -> float:
        return round(self.score_sum / self.total, 2) if self.total else 0.0

    @property
    def badcase_rate(self) -> float:
        return round(self.badcase_count / self.total, 4) if self.total else 0.0

    @property
    def badcase_rate_pct(self) -> str:
        return f"{self.badcase_rate * 100:.1f}%"


def compute_stats(file_path: str, sheet_name: str = "") -> list[ModelStats]:
    """解析已评测的 Excel 文件，返回 ModelStats 列表。"""
    from openpyxl import load_workbook

    # read_only=True 逐行流式读取，不加载全部格式数据，速度更快
    wb = load_workbook(file_path, read_only=True, data_only=True)
    if sheet_name and sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
    else:
        ws = wb.worksheets[0]

    # 读取表头行，比 ws.max_column 更可靠
    first_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ())
    headers = list(first_row)

    if not headers:
        wb.close()
        return []

    # ── 检测列布局 ──────────────────────────────────────────
    # model_map: 模型名 -> (分数列_1based, 问题标签列_1based)
    model_map: dict[str, tuple[int, int]] = {}

    # 格式 A：表头包含 "score_{model}" 模式
    for i, h in enumerate(headers):
        if h and str(h).startswith("score_"):
            model_name = str(h)[6:]          # 去掉 "score_" 前缀
            score_col  = i + 1               # 1-based
            issues_col = i + 2               # 问题标签紧跟其后
            model_map[model_name] = (score_col, issues_col)

    # 格式 B 兜底：找到模型汇总列及其相邻的 score_r1 列
    if not model_map:
        skip = {"score", "问题标签", "issue", "comment"}
        for i, h in enumerate(headers[META_COLS:], start=META_COLS):
            if h is None:
                continue
            h_str = str(h).lower()
            if any(s in h_str for s in skip):
                continue
            # 当前列为模型名，score_r1 在右侧第 2 列
            model_name = str(headers[i])
            score_col  = i + 2   # score_r1 列（1-based）
            issues_col = i + 3   # 问题标签_r1 列
            model_map[model_name] = (score_col, issues_col)

    if not model_map:
        wb.close()
        return []

    stats = {name: ModelStats(name=name) for name in model_map}

    for row in ws.iter_rows(min_row=2, values_only=True):
        for model_name, (score_col, issues_col) in model_map.items():
            si = score_col - 1
            ii = issues_col - 1
            raw_score  = row[si]  if si  < len(row) else None
            raw_issues = row[ii]  if ii  < len(row) else None

            if raw_score is None:
                continue
            try:
                score = int(raw_score)
            except (ValueError, TypeError):
                continue
            if not (1 <= score <= 5):
                continue

            ms = stats[model_name]
            ms.total      += 1
            ms.score_sum  += score

            if score < BADCASE_THRESHOLD:   # 严格小于阈值，不含 3 分
                ms.badcase_count += 1
                if raw_issues:
                    for tag in VALID_ISSUE_TYPES:
                        if tag in str(raw_issues):
                            ms.issue_counts[tag] += 1

    wb.close()
    return [s for s in stats.values() if s.total > 0]
