"""
data_loader.py
--------------
数据加载模块：支持从 CSV / Excel 文件读取数据集，
返回统一的 list[dict] 格式，方便后续评测模块处理。
"""

import os
from typing import Optional

import pandas as pd


class DataLoadError(Exception):
    """数据加载失败"""


class DataLoader:
    SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}

    def __init__(
        self,
        file_path: str,
        sheet_name: Optional[str | int] = 0,
        encoding: str = "utf-8-sig",
    ):
        """
        Parameters
        ----------
        file_path  : 数据文件路径（CSV 或 Excel）
        sheet_name : Excel 工作表名称或索引（CSV 忽略此参数）
        encoding   : CSV 文件编码，默认 utf-8-sig（兼容 BOM）
        """
        self.file_path  = file_path
        self.sheet_name = sheet_name
        self.encoding   = encoding
        self._df: Optional[pd.DataFrame] = None

    # ------------------------------------------------------------------
    # 加载
    # ------------------------------------------------------------------
    def load(self) -> list[dict]:
        """
        读取文件并返回 list[dict]，每个 dict 对应一行数据。
        同时在每条记录中注入 _row_index（从 1 开始的行号）。
        """
        ext = os.path.splitext(self.file_path)[1].lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            raise DataLoadError(
                f"不支持的文件格式: {ext}，支持: {self.SUPPORTED_EXTENSIONS}"
            )
        if not os.path.isfile(self.file_path):
            raise DataLoadError(f"文件不存在: {self.file_path}")

        if ext == ".csv":
            self._df = pd.read_csv(
                self.file_path,
                encoding=self.encoding,
                dtype=str,          # 全部读为字符串，避免类型推断干扰
                keep_default_na=False,
            )
        else:
            self._df = pd.read_excel(
                self.file_path,
                sheet_name=self.sheet_name,
                dtype=str,
                keep_default_na=False,
            )

        # 清理列名首尾空格
        self._df.columns = [str(c).strip() for c in self._df.columns]

        records = self._df.to_dict(orient="records")
        # 注入行号（方便报告定位）
        for idx, rec in enumerate(records, start=1):
            rec["_row_index"] = idx

        return records

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------
    @property
    def columns(self) -> list[str]:
        """返回列名列表（需先调用 load()）"""
        if self._df is None:
            raise DataLoadError("请先调用 load() 方法")
        return list(self._df.columns)

    @property
    def row_count(self) -> int:
        """返回数据行数（需先调用 load()）"""
        if self._df is None:
            raise DataLoadError("请先调用 load() 方法")
        return len(self._df)
