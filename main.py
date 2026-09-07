"""
main.py
-------
主入口：
  python main.py              → 启动 GUI 评测界面
  python main.py --cli        → 命令行模式（使用默认配置）
  python main.py --cli --data data/sample.csv --rule rules/default_rules.yaml
  python main.py --help
"""

import argparse
import sys
import os

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.evaluator import Evaluator
from utils.report_writer import ReportWriter
from utils.logger import get_logger

logger = get_logger("main")


# ------------------------------------------------------------------
# CLI 参数
# ------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="通知摘要评测工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python main.py                          # 启动 GUI
  python main.py --cli                    # CLI 模式（默认配置）
  python main.py --cli --data data/my_dataset.xlsx
  python main.py --cli --output output/report_v2.xlsx --sheet Sheet2
        """,
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        default=False,
        help="使用命令行模式（不加此参数则启动 GUI）",
    )
    parser.add_argument(
        "--data", "-d",
        default="data/sample.csv",
        help="数据文件路径（CSV 或 Excel），默认: data/sample.csv",
    )
    parser.add_argument(
        "--rule", "-r",
        default="rules/default_rules.yaml",
        help="规则文件路径（YAML），默认: rules/default_rules.yaml",
    )
    parser.add_argument(
        "--output", "-o",
        default="output/",
        help="输出路径（目录或 .xlsx 文件），默认: output/",
    )
    parser.add_argument(
        "--sheet", "-s",
        default="0",
        help="Excel 数据文件的工作表名称或索引（CSV 忽略），默认: 0（第一张）",
    )
    parser.add_argument(
        "--encoding", "-e",
        default="utf-8-sig",
        help="CSV 文件编码，默认: utf-8-sig",
    )
    return parser.parse_args()


# ------------------------------------------------------------------
# 主流程
# ------------------------------------------------------------------

def launch_gui() -> None:
    """启动 GUI 评测界面"""
    # 延迟导入，避免无 tkinter 环境时 CLI 模式报错
    try:
        from gui_eval import EvalApp
    except ImportError as e:
        print(f"[ERROR] 无法导入 GUI 模块: {e}")
        print("请确认 gui_eval.py 存在，且已安装 openai / openpyxl")
        sys.exit(1)
    app = EvalApp()
    app.mainloop()


def run_cli(args) -> None:
    """命令行评测流程"""
    # 解析 sheet 参数（数字 or 字符串）
    sheet = int(args.sheet) if args.sheet.isdigit() else args.sheet

    logger.info("=" * 60)
    logger.info("🚀 自动化评测脚本启动")
    logger.info(f"   数据文件 : {args.data}")
    logger.info(f"   规则文件 : {args.rule}")
    logger.info(f"   输出路径 : {args.output}")
    logger.info("=" * 60)

    # 1. 执行评测
    try:
        evaluator = Evaluator(
            data_file  = args.data,
            rule_file  = args.rule,
            sheet_name = sheet,
            encoding   = args.encoding,
        )
        report = evaluator.run()
    except Exception as exc:
        logger.error(f"评测执行失败: {exc}")
        sys.exit(1)

    # 2. 打印摘要
    s = report.summary
    logger.info("─" * 40)
    logger.info(f"📋 评测完成")
    logger.info(f"   总记录数  : {s.total_records}")
    logger.info(f"   通过记录  : {s.passed_records}  ({s.pass_rate}%)")
    logger.info(f"   失败记录  : {s.failed_records}")
    logger.info(f"   总错误数  : {s.total_errors}")
    logger.info(f"   总警告数  : {s.total_warnings}")
    logger.info(f"   耗时      : {s.elapsed_seconds}s")
    logger.info("─" * 40)
    for rid, stat in s.rule_stats.items():
        total = stat["pass"] + stat["fail"]
        rate  = round(stat["pass"] / total * 100, 1) if total else 0
        status = "✓" if stat["fail"] == 0 else "✗"
        logger.info(f"   {status} [{rid}] {stat['name']}: 通过 {stat['pass']}/{total} ({rate}%)")
    logger.info("─" * 40)

    # 3. 写出报告
    try:
        writer = ReportWriter(args.output)
        out_path = writer.write(report)
        logger.info(f"✅ 报告已生成: {out_path}")
    except Exception as exc:
        logger.error(f"报告写出失败: {exc}")
        sys.exit(1)


def main() -> None:
    args = parse_args()

    # 无 --cli 参数 → 启动 GUI
    if not args.cli:
        launch_gui()
        return

    run_cli(args)

    logger.info("=" * 60)
    logger.info("🚀 自动化评测脚本启动")
    logger.info(f"   数据文件 : {args.data}")
    logger.info(f"   规则文件 : {args.rule}")
    logger.info(f"   输出路径 : {args.output}")
    logger.info("=" * 60)

if __name__ == "__main__":
    main()
