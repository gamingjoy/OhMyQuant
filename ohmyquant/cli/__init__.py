"""命令行接口

提供 OhMyQuant 的命令行工具：
  - omq run: 运行策略回测
  - omq backtest: 执行回测
  - omq analyze: 分析回测结果
  - omq list: 列出策略/因子
  - omq init: 初始化项目
  - omq config: 配置管理

参考：Typer 的设计理念，使用 argparse 实现
"""
from __future__ import annotations

import argparse
import sys

from .commands import (
    analyze_command,
    backtest_command,
    config_command,
    init_command,
    list_command,
    run_command,
)


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        prog="omq",
        description="OhMyQuant - 量化策略开发框架",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  omq run ycj v1
  omq backtest --strategy ycj --version v1 --start 2020-01-01
  omq analyze --results results.json
  omq list strategies
  omq init my_strategy
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    run_parser = subparsers.add_parser("run", help="运行策略")
    run_parser.add_argument("strategy_type", help="策略类型")
    run_parser.add_argument("version", help="策略版本")
    run_parser.add_argument("--config", help="配置文件路径")
    run_parser.add_argument("--output", help="输出目录")

    backtest_parser = subparsers.add_parser("backtest", help="执行回测")
    backtest_parser.add_argument("--strategy", required=True, help="策略类型")
    backtest_parser.add_argument("--version", required=True, help="策略版本")
    backtest_parser.add_argument("--start", help="开始日期")
    backtest_parser.add_argument("--end", help="结束日期")
    backtest_parser.add_argument("--config", help="配置文件路径")
    backtest_parser.add_argument("--output", help="输出目录")

    analyze_parser = subparsers.add_parser("analyze", help="分析回测结果")
    analyze_parser.add_argument("--results", required=True, help="结果文件路径")
    analyze_parser.add_argument("--metrics", action="store_true", help="显示指标")
    analyze_parser.add_argument("--compare", help="对比另一个结果文件")
    analyze_parser.add_argument("--report", help="生成报告文件路径")

    list_parser = subparsers.add_parser("list", help="列出策略/因子")
    list_parser.add_argument("type", choices=["strategies", "factors", "data_sources"], help="列表类型")

    init_parser = subparsers.add_parser("init", help="初始化项目")
    init_parser.add_argument("name", help="项目/策略名称")
    init_parser.add_argument("--type", choices=["strategy", "project"], default="strategy", help="类型")

    config_parser = subparsers.add_parser("config", help="配置管理")
    config_parser.add_argument("action", choices=["show", "set", "reset"], help="操作")
    config_parser.add_argument("--key", help="配置键")
    config_parser.add_argument("--value", help="配置值")

    args = parser.parse_args()

    if args.command == "run":
        run_command(args)
    elif args.command == "backtest":
        backtest_command(args)
    elif args.command == "analyze":
        analyze_command(args)
    elif args.command == "list":
        list_command(args)
    elif args.command == "init":
        init_command(args)
    elif args.command == "config":
        config_command(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
