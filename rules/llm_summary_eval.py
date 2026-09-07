"""
rules/llm_summary_eval.py
--------------------------
自定义规则：调用 LLM 对通知摘要进行 1-5 分质量评测。

评测标准来源：rules/llm_scoring_prompt.md
（基于《通知摘要效果评测》评分指南 v1.2）

所有自定义规则模块必须实现：
    evaluate(value, record, rule) -> tuple[bool, str]

Parameters
----------
value  : 当前字段的值（即摘要文本，从 record 中提取）
record : 完整的数据行 dict，需包含 title / content / summary 字段
rule   : 规则配置 dict（来自 YAML），支持以下额外字段：
           - title_field   : 原文标题字段名，默认 "title"
           - content_field : 原文内容字段名，默认 "content"
           - summary_field : 摘要字段名，默认 "summary"
           - min_score     : 最低合格分，默认 3（低于此分视为 error）
           - model         : 调用的模型名称，默认 "gpt-4o"
           - api_base      : OpenAI 兼容 API 地址（可选，用于代理/本地模型）
           - api_key_env   : 存放 API Key 的环境变量名，默认 "OPENAI_API_KEY"
           - prompt_file   : prompt 文件路径，默认 "rules/llm_scoring_prompt.md"

Returns
-------
(passed: bool, message: str)
  passed  : score >= min_score
  message : 包含分数、问题类型和评论的详细说明

依赖：
    pip install openai
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


# ------------------------------------------------------------------
# Prompt 加载（带缓存）
# ------------------------------------------------------------------

_prompt_cache: dict[str, str] = {}


def _load_prompt(prompt_file: str) -> str:
    """加载并缓存 prompt 文件内容"""
    if prompt_file in _prompt_cache:
        return _prompt_cache[prompt_file]

    prompt_path = Path(prompt_file)
    if not prompt_path.is_file():
        # 尝试相对于项目根目录
        root = Path(__file__).parent.parent
        prompt_path = root / prompt_file

    if not prompt_path.is_file():
        raise FileNotFoundError(f"Prompt 文件不存在: {prompt_file}")

    content = prompt_path.read_text(encoding="utf-8")
    _prompt_cache[prompt_file] = content
    return content


# ------------------------------------------------------------------
# LLM 调用
# ------------------------------------------------------------------

def _call_llm(system_prompt: str, user_message: str, rule: dict) -> dict:
    """
    调用 OpenAI 兼容 API，返回解析后的 JSON 结果。

    Returns
    -------
    dict with keys: score (int), issue_types (list[str]), comment (str)
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError(
            "缺少 openai 依赖，请运行: pip install openai"
        )

    api_key_env = rule.get("api_key_env", "OPENAI_API_KEY")
    api_key = os.environ.get(api_key_env, "")
    if not api_key:
        raise EnvironmentError(
            f"未找到 API Key，请设置环境变量: {api_key_env}"
        )

    client_kwargs: dict[str, Any] = {"api_key": api_key}
    if api_base := rule.get("api_base"):
        client_kwargs["base_url"] = api_base

    client = OpenAI(**client_kwargs)

    model = rule.get("model", "gpt-4o")

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content or "{}"
    return json.loads(raw)


# ------------------------------------------------------------------
# 结果解析与校验
# ------------------------------------------------------------------

def _parse_result(raw: dict) -> tuple[int, list[str], str]:
    """
    从 LLM 返回的 dict 中提取并校验 score / issue_types / comment。
    """
    VALID_ISSUE_TYPES = {"风格偏离", "重点不突出", "信息冗余", "低价值信息", "其他"}

    # score
    try:
        score = int(raw.get("score", 0))
    except (ValueError, TypeError):
        score = 0
    score = max(1, min(5, score))  # 限制在 1-5

    # issue_types
    raw_issues = raw.get("issue_types", [])
    if isinstance(raw_issues, str):
        raw_issues = [raw_issues]
    issue_types = [t for t in raw_issues if t in VALID_ISSUE_TYPES]

    # comment
    comment = str(raw.get("comment", "")).strip()

    return score, issue_types, comment


# ------------------------------------------------------------------
# 主入口
# ------------------------------------------------------------------

def evaluate(value, record: dict, rule: dict) -> tuple[bool, str]:
    """
    使用 LLM 对通知摘要进行质量评测。

    Parameters
    ----------
    value  : 摘要文本（从 summary_field 提取）
    record : 完整数据行
    rule   : YAML 规则配置

    Returns
    -------
    (passed, message)
    """
    # ── 字段提取 ──────────────────────────────────────────────────
    title_field   = rule.get("title_field",   "title")
    content_field = rule.get("content_field", "content")
    summary_field = rule.get("summary_field", "summary")
    min_score     = int(rule.get("min_score", 3))
    prompt_file   = rule.get("prompt_file",   "rules/llm_scoring_prompt.md")

    title   = str(record.get(title_field,   "")).strip()
    content = str(record.get(content_field, "")).strip()
    summary = str(value or record.get(summary_field, "")).strip()

    if not summary:
        return False, "摘要字段为空，无法评测"

    # ── 构建 prompt ───────────────────────────────────────────────
    system_prompt = _load_prompt(prompt_file)

    user_message = (
        f"【原文标题 | Original Title】: {title}\n"
        f"【原文内容 | Original Content】: {content}\n"
        f"【摘要 | Summary】: {summary}"
    )

    # ── 调用 LLM ─────────────────────────────────────────────────
    try:
        raw_result = _call_llm(system_prompt, user_message, rule)
    except (ImportError, EnvironmentError) as e:
        return False, f"LLM 调用配置错误: {e}"
    except Exception as e:
        return False, f"LLM 调用失败: {e}"

    # ── 解析结果 ──────────────────────────────────────────────────
    score, issue_types, comment = _parse_result(raw_result)

    passed = score >= min_score

    # ── 构建消息 ──────────────────────────────────────────────────
    issues_str = "、".join(issue_types) if issue_types else "无"
    message_parts = [
        f"LLM 评分: {score}/5",
        f"问题类型: {issues_str}",
    ]
    if comment:
        message_parts.append(f"评论: {comment}")
    message_parts.append(f"（合格线: {min_score}分，{'✓ 通过' if passed else '✗ 未通过'}）")

    return passed, " | ".join(message_parts)
