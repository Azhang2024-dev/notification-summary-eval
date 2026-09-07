"""
utils/logger.py
---------------
统一日志工具：提供带颜色的控制台输出 + 文件日志。
"""

import logging
import os
from datetime import datetime


_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")


def get_logger(name: str = "eval", log_to_file: bool = True) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # 避免重复添加 handler

    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台 handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # 文件 handler
    if log_to_file:
        os.makedirs(_LOG_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d")
        log_file = os.path.join(_LOG_DIR, f"eval_{ts}.log")
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger
