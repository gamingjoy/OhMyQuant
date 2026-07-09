"""命令实现

提供 OhMyQuant CLI 的命令实现：
  - run: 运行策略回测
  - backtest: 执行回测
  - analyze: 分析回测结果
  - list: 列出策略/因子
  - init: 初始化项目
  - config: 配置管理
"""
from __future__ import annotations

import json
import os
from typing import Any

import numpy as np

from ..analysis.metrics import compute_metrics, print_metrics
from ..strategy.registry import StrategyRegistry
from ..strategy.runner import StrategyRunner
from ..strategy.version_manager import VersionManager


def run_command(args) -> None:
    """运行策略"""
    print(f"运行策略: {args.strategy_type} v{args.version}")

    try:
        result = StrategyRunner.run_strategy(
            strategy_type=args.strategy_type,
            version=args.version,
        )

        if result.backtest_result:
            returns = result.backtest_result.daily_returns
            metrics = compute_metrics(returns)
            print("-" * 60)
            print("回测结果")
            print("-" * 60)
            print_metrics(metrics)

        output_dir = args.output or "./output"
        os.makedirs(output_dir, exist_ok=True)

        result_dict = {
            "strategy_type": args.strategy_type,
            "version": args.version,
            "metrics": metrics.__dict__ if 'metrics' in dir() else {},
        }
        with open(os.path.join(output_dir, "results.json"), "w", encoding="utf-8") as f:
            json.dump(result_dict, f, indent=2, ensure_ascii=False)

        print(f"\n结果已保存到: {output_dir}")

    except Exception as e:
        print(f"运行策略失败: {e}")


def backtest_command(args) -> None:
    """执行回测"""
    print(f"执行回测: {args.strategy} v{args.version}")

    try:
        strategy = StrategyRegistry.create(
            strategy_type=args.strategy,
            version=args.version,
        )

        config: dict = {}
        if args.start:
            config["start_date"] = args.start
        if args.end:
            config["end_date"] = args.end

        runner = StrategyRunner(strategy.config)
        result = runner.run()

        if result.backtest_result:
            returns = result.backtest_result.daily_returns
            metrics = compute_metrics(returns)
            print("-" * 60)
            print("回测结果")
            print("-" * 60)
            print_metrics(metrics)

        output_dir = args.output or "./output"
        os.makedirs(output_dir, exist_ok=True)

        with open(os.path.join(output_dir, "backtest_results.json"), "w", encoding="utf-8") as f:
            json.dump({
                "strategy": args.strategy,
                "version": args.version,
                "metrics": metrics.__dict__,
            }, f, indent=2, ensure_ascii=False)

        print(f"\n回测完成")

    except Exception as e:
        print(f"回测失败: {e}")


def analyze_command(args) -> None:
    """分析回测结果"""
    print(f"分析回测结果: {args.results}")

    try:
        with open(args.results, "r", encoding="utf-8") as f:
            results = json.load(f)

        if args.metrics:
            if "metrics" in results:
                print("-" * 60)
                print("绩效指标")
                print("-" * 60)
                for key, value in results["metrics"].items():
                    if isinstance(value, float):
                        print(f"{key}: {value:.4f}")
                    else:
                        print(f"{key}: {value}")

        if args.compare:
            print("\n" + "-" * 60)
            print("对比分析")
            print("-" * 60)
            with open(args.compare, "r", encoding="utf-8") as f:
                compare_results = json.load(f)

            for key in ["total_return", "annualized_return", "sharpe_ratio", "max_drawdown"]:
                v1 = results["metrics"].get(key, 0)
                v2 = compare_results["metrics"].get(key, 0)
                diff = v1 - v2
                print(f"{key}: {v1:.4f} vs {v2:.4f} (差异: {diff:.4f})")

        if args.report:
            from ..analysis.report import ReportGenerator

            returns = np.array(results.get("daily_returns", []))
            generator = ReportGenerator(
                strategy_name=results.get("strategy", ""),
                strategy_version=results.get("version", ""),
            )
            generator.generate_html_report(returns, args.report)
            print(f"\n报告已生成: {args.report}")

    except Exception as e:
        print(f"分析失败: {e}")


def list_command(args) -> None:
    """列出策略/因子"""
    if args.type == "strategies":
        print("可用策略:")
        strategies = VersionManager.list_strategy_types()
        for strategy_type in strategies:
            versions = VersionManager.list_versions(strategy_type)
            print(f"  {strategy_type}: {', '.join(versions)}")

    elif args.type == "factors":
        print("可用因子:")
        print("  alpha1, alpha5, alpha101")

    elif args.type == "data_sources":
        print("可用数据源:")
        print("  jqdata, tushare, akshare, local_parquet")


def init_command(args) -> None:
    """初始化项目/策略"""
    print(f"初始化: {args.name}")

    if args.type == "strategy":
        strategy_dir = os.path.join("./strategies", args.name)
        os.makedirs(strategy_dir, exist_ok=True)

        v1_dir = os.path.join(strategy_dir, "v1")
        os.makedirs(v1_dir, exist_ok=True)

        strategy_template = f'''"""策略实现 - {args.name} v1"""
from ohmyquant.strategy.base import BaseStrategy
from ohmyquant.strategy import register_strategy


@register_strategy("{args.name}", "v1")
class {args.name.capitalize()}StrategyV1(BaseStrategy):
    def run(self):
        return {{}}
    
    def get_latest_positions(self):
        return {{}}
    
    @classmethod
    def from_version(cls, strategy_type, version, config=None):
        return cls(config or {{}})
'''
        with open(os.path.join(v1_dir, "strategy.py"), "w", encoding="utf-8") as f:
            f.write(strategy_template)

        config_template = f'''# {args.name} v1 配置
strategy_type: "{args.name}"
version: "v1"
'''
        with open(os.path.join(v1_dir, "config.yaml"), "w", encoding="utf-8") as f:
            f.write(config_template)

        print(f"策略模板已创建: {strategy_dir}")

    elif args.type == "project":
        project_dir = args.name
        os.makedirs(project_dir, exist_ok=True)

        init_files = [
            ("config.yaml", "# 项目配置\n"),
            ("main.py", "# 主入口\nfrom ohmyquant.strategy.runner import StrategyRunner\n\nif __name__ == \"__main__\":\n    result = StrategyRunner.run_strategy(\"ycj\", \"v1\")\n    print(result)\n"),
            (".gitignore", "__pycache__/\n*.pyc\n*.egg-info/\n.vscode/\n"),
        ]

        for filename, content in init_files:
            with open(os.path.join(project_dir, filename), "w", encoding="utf-8") as f:
                f.write(content)

        print(f"项目已初始化: {project_dir}")


def config_command(args) -> None:
    """配置管理"""
    config_file = os.path.expanduser("~/.ohmyquant/config.json")

    if args.action == "show":
        if os.path.exists(config_file):
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            for key, value in config.items():
                print(f"{key}: {value}")
        else:
            print("配置文件不存在")

    elif args.action == "set":
        if not args.key or not args.value:
            print("请提供 --key 和 --value")
            return

        os.makedirs(os.path.dirname(config_file), exist_ok=True)

        if os.path.exists(config_file):
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
        else:
            config = {}

        config[args.key] = args.value

        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

        print(f"配置已设置: {args.key} = {args.value}")

    elif args.action == "reset":
        if os.path.exists(config_file):
            os.remove(config_file)
            print("配置已重置")
        else:
            print("配置文件不存在")
