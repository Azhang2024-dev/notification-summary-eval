@echo off
chcp 65001 >nul
title 通知摘要 LLM 评测工具

:: ── 检查 Python ──────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.9 及以上版本。
    echo 下载地址：https://www.python.org/downloads/
    echo 安装时请勾选 "Add Python to PATH"
    pause
    exit /b 1
)

:: ── 检查并安装依赖 ───────────────────────────────────────────────────
echo 正在检查依赖...
pip show openai >nul 2>&1
if errorlevel 1 (
    echo 首次运行，正在安装依赖（需要网络，约 1-2 分钟）...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请检查网络连接后重试。
        pause
        exit /b 1
    )
    echo 依赖安装完成。
)

:: ── 启动程序 ─────────────────────────────────────────────────────────
python gui_eval.py
