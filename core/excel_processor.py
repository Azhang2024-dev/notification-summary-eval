"""
core/excel_processor.py
-----------------------
Excel 读取与输出模块。

支持两种输入格式，自动识别：

格式 A（纯摘要列，如 notisum_en_eval_20260612.xlsx）：
  A: id | B: app_type | C: app_name | D: title | E: content
  F: model1 | G: model2 | ... （每列只存摘要文本）
  输出时在每个 modelN 列后插入 score_modelN / 问题标签 / comment_modelN 三列。

格式 B（含评分列，如 notisum_en_eval_20260518.xlsx）：
  A: id | B: app_type | C: app_name | D: title | E: content
  然后每个模型占 10 列：
    [model_name, score_r1, 问题标签_r1, comment_r1, ×3]
  输出时直接写入对应单元格。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import openpyxl
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# ── 常量 ──────────────────────────────────────────────────────────────
META_COLS      = 5    # id, app_type, app_name, title, content
COLS_PER_MODEL = 10   # 格式B：model_name + 3×(score, 问题标签, comment)
HEADER_ROW     = 1
DATA_START_ROW = 2

SCORE_COLORS = {
    1: "FFCCCC",
    2: "FFDDAA",
    3: "FFFFCC",
    4: "CCFFCC",
    5: "99FF99",
}

# 列头样式（输出时新插入的列）
HEADER_FILL  = PatternFill("solid", fgColor="D9E1F2")
HEADER_FONT  = Font(bold=True)
HEADER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)

# 数据行复用的对齐样式（避免每格重复构造对象）
_ALIGN_TOP    = Alignment(wrap_text=True, vertical="top")
_ALIGN_CENTER = Alignment(horizontal="center", vertical="center")
_ALIGN_WRAP   = Alignment(wrap_text=True, vertical="center")

# 评分颜色填充缓存（score 固定为 1-5，提前构造好）
_SCORE_FILLS  = {s: PatternFill("solid", fgColor=c) for s, c in SCORE_COLORS.items()}
_FILL_DEFAULT = PatternFill("solid", fgColor="FFFFFF")


# ── 数据结构 ──────────────────────────────────────────────────────────

@dataclass
class ReviewerScore:
    score       : Optional[int]  = None
    issue_types : list[str]      = field(default_factory=list)
    comment     : Optional[str]  = None


@dataclass
class ModelEntry:
    """一个模型的摘要文本及其评分（col_offset 为原始 sheet 中该列的列号）"""
    model_col_name : str          # 列头，如 "model1"
    summary        : str          # 摘要文本
    src_col        : int          # 原始 sheet 中该列的列号（1-based）
    score_result   : Optional[ReviewerScore] = None


@dataclass
class DataRow:
    row_index : int
    id        : str
    app_type  : str
    app_name  : str
    title     : str
    content   : str
    models    : list[ModelEntry] = field(default_factory=list)


# ── 格式检测 ──────────────────────────────────────────────────────────

def _is_compact_format(headers: list) -> bool:
    """
    判断是否为格式A（紧凑格式）：
    META_COLS 之后的列全部是 modelN 摘要列（无 score_* / 问题标签 / comment_* 列）。
    """
    if len(headers) <= META_COLS:
        return False
    for h in headers[META_COLS:]:
        name = str(h or "").strip().lower()
        if name.startswith("score") or name in ("问题标签", "issue_type") or name.startswith("comment"):
            return False
    return True


# ── 读取 ──────────────────────────────────────────────────────────────

class ExcelReader:
    """读取输入 Excel，自动识别格式 A / B，解析所有数据行"""

    def __init__(self, file_path: str, sheet_name: str | int = 0):
        self.file_path  = file_path
        self.sheet_name = sheet_name
        self.is_compact : bool = False   # True = 格式A

    def load(self) -> tuple[list[DataRow], list[str]]:
        wb = load_workbook(self.file_path, data_only=True)
        ws = (wb.worksheets[self.sheet_name]
              if isinstance(self.sheet_name, int)
              else wb[self.sheet_name])

        # 一次性预加载所有行数据，避免逐格 .cell() 调用
        raw_rows = list(ws.iter_rows(values_only=True))
        wb.close()

        if not raw_rows:
            return [], []

        headers = list(raw_rows[0])
        self.is_compact = _is_compact_format(headers)

        rows: list[DataRow] = []
        warnings: list[str] = []

        # 格式B：model_starts 只需计算一次
        model_starts: list[int] = []
        if not self.is_compact:
            for i, h in enumerate(headers):
                col = i + 1
                if col <= META_COLS:
                    continue
                name = str(h or "").strip().lower()
                if (name.startswith("model")
                        and not name.startswith("score")
                        and not name.startswith("comment")):
                    model_starts.append(col)

        for row_offset, raw in enumerate(raw_rows[1:], start=2):   # row_offset 与原 row_index 含义一致（1-based，从第2行起）
            if not raw or raw[0] is None:
                continue

            dr = DataRow(
                row_index = row_offset,
                id        = str(raw[0]).strip(),
                app_type  = str(raw[1] or "").strip(),
                app_name  = str(raw[2] or "").strip(),
                title     = str(raw[3] or "").strip(),
                content   = str(raw[4] or "").strip(),
            )

            if self.is_compact:
                for col_idx in range(META_COLS + 1, len(headers) + 1):
                    col_name = str(headers[col_idx - 1] or "").strip()
                    summary  = str(raw[col_idx - 1] or "").strip()
                    dr.models.append(ModelEntry(
                        model_col_name = col_name,
                        summary        = summary,
                        src_col        = col_idx,
                    ))
            else:
                for start_col in model_starts:
                    summary  = str(raw[start_col - 1] or "").strip()
                    col_name = str(headers[start_col - 1] or "").strip()
                    dr.models.append(ModelEntry(
                        model_col_name = col_name,
                        summary        = summary,
                        src_col        = start_col,
                    ))

            rows.append(dr)

        return rows, warnings


# ── 写出（格式A：构建新 workbook，插入评分列）────────────────────────

class ExcelOutputBuilder:
    """
    针对格式A（紧凑格式）：
    读取原始文件，在每个 modelN 列后插入
      score_modelN | 问题标签 | comment_modelN
    三列，并将 LLM 评分结果写入，输出新文件。
    """

    def __init__(self, source_path: str, sheet_name: str | int = 0):
        self._source_path = source_path
        self._sheet_name  = sheet_name
        # 用于收集评分结果：{(row_index, src_col): ReviewerScore}
        self._results: dict[tuple[int, int], ReviewerScore] = {}

        # 读取原始数据
        self._src_wb = load_workbook(source_path)
        self._src_ws = (self._src_wb.worksheets[sheet_name]
                        if isinstance(sheet_name, int)
                        else self._src_wb[sheet_name])

    def add_result(self, row_index: int, src_col: int, result: ReviewerScore) -> None:
        """登记一条评分结果"""
        self._results[(row_index, src_col)] = result

    def save(self, output_path: str) -> None:
        """构建输出 workbook 并保存"""
        src_ws = self._src_ws

        # 一次性预加载源数据，避免逐格 .cell() 调用
        src_rows = list(src_ws.iter_rows(values_only=True))
        src_headers = list(src_rows[0]) if src_rows else []

        # 确定模型列（META_COLS+1 之后的所有列）
        model_src_cols = list(range(META_COLS + 1, len(src_headers) + 1))

        # 构建新 workbook
        new_wb = openpyxl.Workbook()
        new_ws = new_wb.active
        new_ws.title = (self._src_ws.title
                        if hasattr(self._src_ws, "title") else "Sheet1")

        # ── 写列头 ────────────────────────────────────────────────────
        out_col = 1
        for c in range(1, META_COLS + 1):
            cell = new_ws.cell(1, out_col)
            cell.value = src_headers[c - 1]
            cell.font  = HEADER_FONT
            cell.fill  = HEADER_FILL
            cell.alignment = HEADER_ALIGN
            out_col += 1

        model_col_map: dict[int, int] = {}
        for src_c in model_src_cols:
            model_name = str(src_headers[src_c - 1] or "").strip()
            model_col_map[src_c] = out_col
            _write_header(new_ws, 1, out_col, model_name)
            out_col += 1
            _write_header(new_ws, 1, out_col, f"score_{model_name}")
            out_col += 1
            _write_header(new_ws, 1, out_col, "问题标签")
            out_col += 1
            _write_header(new_ws, 1, out_col, f"comment_{model_name}")
            out_col += 1

        # ── 写数据行 ──────────────────────────────────────────────────
        for row_offset, raw in enumerate(src_rows[1:], start=2):
            if not raw or raw[0] is None:
                continue

            out_col = 1
            for c in range(1, META_COLS + 1):
                cell = new_ws.cell(row_offset, out_col)
                cell.value     = raw[c - 1]
                cell.alignment = _ALIGN_TOP
                out_col += 1

            for src_c in model_src_cols:
                sum_cell = new_ws.cell(row_offset, out_col)
                sum_cell.value     = raw[src_c - 1]
                sum_cell.alignment = _ALIGN_TOP
                out_col += 1

                result = self._results.get((row_offset, src_c))
                if result:
                    sc = new_ws.cell(row_offset, out_col)
                    sc.value     = result.score
                    sc.fill      = _SCORE_FILLS.get(result.score or 0, _FILL_DEFAULT)
                    sc.alignment = _ALIGN_CENTER
                    out_col += 1

                    iss = new_ws.cell(row_offset, out_col)
                    iss.value     = "、".join(result.issue_types) if result.issue_types else None
                    iss.alignment = _ALIGN_WRAP
                    out_col += 1

                    cmt = new_ws.cell(row_offset, out_col)
                    cmt.value     = result.comment or None
                    cmt.alignment = _ALIGN_WRAP
                    out_col += 1
                else:
                    out_col += 3

        # ── 列宽 ──────────────────────────────────────────────────────
        _auto_col_width(new_ws)

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        new_wb.save(output_path)


def _write_header(ws, row: int, col: int, value: str) -> None:
    cell = ws.cell(row, col)
    cell.value     = value
    cell.font      = HEADER_FONT
    cell.fill      = HEADER_FILL
    cell.alignment = HEADER_ALIGN


def _auto_col_width(ws, max_width: int = 50, sample_rows: int = 50) -> None:
    for col_cells in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col_cells[0].column)
        for cell in col_cells[:sample_rows]:
            try:
                val = str(cell.value or "")
                # 取第一行（不含换行）的长度
                line_len = max(len(ln) for ln in val.split("\n")) if val else 0
                max_len = max(max_len, line_len)
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max(max_len + 2, 8), max_width)


# ── 写出（格式B：原地写入）───────────────────────────────────────────

class ExcelWriter:
    """格式B：直接在克隆的 workbook 中写入评分列"""

    def __init__(self, source_path: str, sheet_name: str | int = 0):
        self._wb = load_workbook(source_path)
        self._ws = (self._wb.worksheets[sheet_name]
                    if isinstance(sheet_name, int)
                    else self._wb[sheet_name])

    def write_scores(
        self,
        row_index   : int,
        model_col   : int,
        reviewer_idx: int,
        score       : int,
        issue_types : list[str],
        comment     : str,
    ) -> None:
        base = model_col + 1 + reviewer_idx * 3
        ws   = self._ws

        sc = ws.cell(row_index, base)
        sc.value     = score
        sc.fill      = _SCORE_FILLS.get(score, _FILL_DEFAULT)
        sc.alignment = _ALIGN_CENTER

        iss = ws.cell(row_index, base + 1)
        iss.value     = "、".join(issue_types) if issue_types else None
        iss.alignment = _ALIGN_WRAP

        cmt = ws.cell(row_index, base + 2)
        cmt.value     = comment or None
        cmt.alignment = _ALIGN_WRAP

    def save(self, output_path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        self._wb.save(output_path)


# ── 工具函数 ──────────────────────────────────────────────────────────

def detect_sheets(file_path: str) -> list[str]:
    wb = load_workbook(file_path, read_only=True, data_only=True)
    names = wb.sheetnames
    wb.close()
    return names


def detect_data_sheet(file_path: str) -> str:
    """优先选含 id/title/content 列头的 sheet，否则返回第一个 sheet"""
    wb = load_workbook(file_path, read_only=True, data_only=True)
    best = wb.sheetnames[0]
    for name in wb.sheetnames:
        ws = wb[name]
        row1 = [str(c.value or "").lower() for c in next(ws.iter_rows(max_row=1))]
        if "id" in row1 and "title" in row1 and "content" in row1:
            best = name
            break
    wb.close()
    return best
