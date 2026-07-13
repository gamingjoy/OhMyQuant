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
    compare_command,
    config_command,
    ensemble_command,
    init_command,
    list_command,
    optimize_command,
    run_command,
    signal_command,
)


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        prog="omq",
        description="OhMyQuant - 量化策略开发框架",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  omq run ycj v1                      # 运行策略回测
  omq backtest --strategy ycj --version v1 --start 2020-01-01
  omq list strategies                  # 列出所有策略
  omq compare a.json b.json            # 对比两个策略
  omq ensemble dl_v1 etf_v3 --weighting perf_weight  # 多策略集成
  omq optimize walk-forward ycj v1     # Walk-Forward 验证
  omq signal ycj v1                    # 获取最新持仓信号
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

    list_parser = subparsers.add_parser("list", help="列出策略/因子/插件")
    list_parser.add_argument(
        "type",
        choices=[
            "strategies", "factors", "selectors", "allocators",
            "risk_managers", "rebalancers", "cost_models",
            "data_sources", "schedulers", "models",
        ],
        help="列表类型",
    )

    init_parser = subparsers.add_parser("init", help="初始化项目")
    init_parser.add_argument("name", help="项目/策略名称")
    init_parser.add_argument("--type", choices=["strategy", "project"], default="strategy", help="类型")

    config_parser = subparsers.add_parser("config", help="配置管理")
    config_parser.add_argument("action", choices=["show", "set", "reset"], help="操作")
    config_parser.add_argument("--key", help="配置键")
    config_parser.add_argument("--value", help="配置值")

    # optimize 子命令
    optimize_parser = subparsers.add_parser("optimize", help="策略优化")
    optimize_sub = optimize_parser.add_subparsers(dest="optimize_command", help="优化方法")

    wf_parser = optimize_sub.add_parser("walk-forward", help="Walk-Forward 滚动验证")
    wf_parser.add_argument("strategy_type", help="策略类型")
    wf_parser.add_argument("version", help="策略版本")
    wf_parser.add_argument("--window", default="1Y", help="测试窗口（如 1Y/6M/63D）")
    wf_parser.add_argument("--step", default="1Y", help="滑动步长")
    wf_parser.add_argument("--output", help="输出目录")

    ps_parser = optimize_sub.add_parser("param-search", help="参数搜索")
    ps_parser.add_argument("strategy_type", help="策略类型")
    ps_parser.add_argument("version", help="策略版本")
    ps_parser.add_argument("--params", required=True, help="参数空间 JSON 字符串")
    ps_parser.add_argument("--n-trials", type=int, default=50, help="最大试验数")
    ps_parser.add_argument("--metric", default="sharpe", choices=["sharpe", "total_return", "max_drawdown"])
    ps_parser.add_argument("--output", help="输出目录")

    # compare 子命令
    compare_parser = subparsers.add_parser("compare", help="策略对比")
    compare_parser.add_argument("result1", help="第一个结果 JSON 路径")
    compare_parser.add_argument("result2", help="第二个结果 JSON 路径")
    compare_parser.add_argument("--report", help="HTML 报告输出路径")

    # signal 子命令
    signal_parser = subparsers.add_parser("signal", help="获取策略最新持仓信号")
    signal_parser.add_argument("strategy_type", help="策略类型")
    signal_parser.add_argument("version", help="策略版本")

    # ensemble 子命令
    ensemble_parser = subparsers.add_parser("ensemble", help="多策略集成")
    ensemble_parser.add_argument("strategies", nargs="+", help="策略名（如 ycj_v1）或结果文件路径")
    ensemble_parser.add_argument(
        "--weighting",
        choices=["equal", "perf_weight", "ir_weight"],
        default="perf_weight",
        help="加权方式",
    )
    ensemble_parser.add_argument("--output", help="输出目录")

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
    elif args.command == "optimize":
        optimize_command(args)
    elif args.command == "compare":
        compare_command(args)
    elif args.command == "signal":
        signal_command(args)
    elif args.command == "ensemble":
        ensemble_command(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
