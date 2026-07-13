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


def _json_safe(obj):
    """将 numpy 类型转为 JSON 可序列化的 Python 原生类型"""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return [_json_safe(v) for v in obj.tolist()]
    return obj


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

        output_dir = args.output or f"./output/{args.strategy_type}_{args.version}"
        os.makedirs(output_dir, exist_ok=True)

        result_dict = {
            "strategy_type": args.strategy_type,
            "version": args.version,
            "metrics": _json_safe(metrics.__dict__) if 'metrics' in dir() else {},
            "daily_returns": _json_safe(returns.tolist() if hasattr(returns, "tolist") else list(returns)),
            "dates": _json_safe(result.backtest_result.dates) if result.backtest_result and hasattr(result.backtest_result, 'dates') else [],
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

        output_dir = args.output or f"./output/{args.strategy}_{args.version}"
        os.makedirs(output_dir, exist_ok=True)

        with open(os.path.join(output_dir, "backtest_results.json"), "w", encoding="utf-8") as f:
            json.dump({
                "strategy": args.strategy,
                "version": args.version,
                "metrics": _json_safe(metrics.__dict__),
                "daily_returns": _json_safe(returns.tolist() if hasattr(returns, "tolist") else list(returns)),
                "dates": _json_safe(result.backtest_result.dates) if result.backtest_result and hasattr(result.backtest_result, 'dates') else [],
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
    """列出已注册插件"""
    from ..core.plugin_system import PluginRegistry, PluginType

    PluginRegistry.discover_builtin()

    if args.type == "strategies":
        print("可用策略:")
        strategies = VersionManager.list_strategy_types()
        for strategy_type in strategies:
            versions = VersionManager.list_versions(strategy_type)
            print(f"  {strategy_type}: {', '.join(versions)}")
        return

    type_map = {
        "factors": PluginType.FACTOR,
        "selectors": PluginType.SELECTOR,
        "allocators": PluginType.ALLOCATOR,
        "risk_managers": PluginType.RISK_MANAGER,
        "rebalancers": PluginType.REBALANCER,
        "cost_models": PluginType.COST_MODEL,
        "data_sources": PluginType.DATA_SOURCE,
        "schedulers": PluginType.SCHEDULER,
        "models": PluginType.MODEL,
    }

    pt = type_map[args.type]
    plugins = PluginRegistry.list_plugins(pt)
    print(f"可用{args.type} ({len(plugins)}):")
    for name in plugins:
        try:
            meta = PluginRegistry.get_meta(pt, name)
            desc = f"  # {meta.description}" if meta.description else ""
        except Exception:
            desc = ""
        print(f"  {name}{desc}")


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


def optimize_command(args) -> None:
    """策略优化"""
    if args.optimize_command == "walk-forward":
        _optimize_walk_forward(args)
    elif args.optimize_command == "param-search":
        _optimize_param_search(args)
    else:
        print("请指定优化方法: walk-forward 或 param-search")


def _optimize_walk_forward(args) -> None:
    """Walk-Forward 滚动验证"""
    from ..optimization.walk_forward import StrategyWalkForward

    print(f"Walk-Forward: {args.strategy_type} {args.version}")
    print(f"  窗口: {args.window}, 步长: {args.step}")

    try:
        wf = StrategyWalkForward(test_window=args.window, step=args.step)
        report = wf.run(args.strategy_type, args.version)
        print(report.summary())

        if args.output:
            os.makedirs(args.output, exist_ok=True)
            output_path = os.path.join(args.output, f"walk_forward_{args.strategy_type}_{args.version}.txt")
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(report.summary())
            print(f"\n报告已保存: {output_path}")

    except Exception as e:
        print(f"Walk-Forward 失败: {e}")


def _optimize_param_search(args) -> None:
    """参数搜索"""
    import json as json_module
    from ..optimization.param_search import ParamSearcher

    print(f"参数搜索: {args.strategy_type} {args.version}")
    print(f"  试验数: {args.n_trials}, 指标: {args.metric}")

    try:
        param_space = json_module.loads(args.params)
    except json_module.JSONDecodeError as e:
        print(f"参数空间 JSON 解析失败: {e}")
        return

    try:
        ps = ParamSearcher(n_trials=args.n_trials, metric=args.metric)
        report = ps.search(args.strategy_type, args.version, param_space)
        print(report.summary())

        if args.output:
            os.makedirs(args.output, exist_ok=True)
            output_path = os.path.join(args.output, f"param_search_{args.strategy_type}_{args.version}.json")
            with open(output_path, "w", encoding="utf-8") as f:
                json_module.dump({
                    "best_params": report.best_params,
                    "best_value": report.best_value,
                    "best_metrics": report.best_metrics,
                    "n_trials": report.n_trials,
                    "backend": report.backend,
                }, f, indent=2, ensure_ascii=False)
            print(f"\n结果已保存: {output_path}")

    except Exception as e:
        print(f"参数搜索失败: {e}")


def compare_command(args) -> None:
    """策略对比"""
    import numpy as np
    from ..analysis.compare import StrategyComparator
    from ..analysis.report import ReportGenerator

    print(f"策略对比: {args.result1} vs {args.result2}")

    try:
        with open(args.result1, "r", encoding="utf-8") as f:
            r1 = json.load(f)
        with open(args.result2, "r", encoding="utf-8") as f:
            r2 = json.load(f)

        name1 = f"{r1.get('strategy_type', r1.get('strategy', 'A'))}_{r1.get('version', '')}"
        name2 = f"{r2.get('strategy_type', r2.get('strategy', 'B'))}_{r2.get('version', '')}"

        ret1 = np.array(r1.get("daily_returns", []))
        ret2 = np.array(r2.get("daily_returns", []))

        if len(ret1) == 0 or len(ret2) == 0:
            print("错误: 结果文件缺少 daily_returns 数据。请确保使用 omq run/backtest 生成结果。")
            return

        comparator = StrategyComparator({name1: ret1, name2: ret2})

        print("-" * 60)
        print("指标对比")
        print("-" * 60)
        print(comparator.get_comparison_table())

        print("-" * 60)
        print("相关性矩阵")
        print("-" * 60)
        print(comparator.compute_correlation_matrix())

        print("-" * 60)
        print("策略排名")
        print("-" * 60)
        for name, value in comparator.rank_strategies(metric="sharpe_ratio"):
            print(f"  {name}: sharpe={value:.4f}")

        if args.report:
            generator = ReportGenerator(
                strategy_name=f"{name1} vs {name2}",
                strategy_version="comparison",
            )
            generator.generate_html_report(ret1, args.report)
            print(f"\nHTML 报告已生成: {args.report}")

    except Exception as e:
        print(f"对比失败: {e}")


def signal_command(args) -> None:
    """获取策略最新持仓信号"""
    print(f"持仓信号: {args.strategy_type} {args.version}")

    try:
        strategy = StrategyRegistry.create(args.strategy_type, args.version)
        positions = strategy.get_latest_positions()

        if not positions:
            print("  (空 — 当前策略尚未实现持仓信号逻辑)")
            print("  提示: get_latest_positions() 需在策略迭代中实现")
        else:
            print(f"  持仓 ({len(positions)}):")
            for code, weight in sorted(positions.items(), key=lambda x: -x[1]):
                print(f"    {code}: {weight:.2%}")

    except Exception as e:
        print(f"获取信号失败: {e}")


def ensemble_command(args) -> None:
    """多策略集成"""
    from ..optimization.ensemble import StrategyEnsemble

    weighting = args.weighting
    strategies = args.strategies

    # 解析策略名为结果文件路径
    result_files = []
    for s in strategies:
        if "/" in s or "\\" in s or s.endswith(".json"):
            result_files.append(s)
        else:
            result_files.append(f"./output/{s}/results.json")

    print(f"策略集成: {' + '.join(strategies)}")
    print(f"加权方式: {weighting}")
    print("-" * 60)

    try:
        ens = StrategyEnsemble.from_results(
            result_files=result_files,
            weighting=weighting,
        )
        result = ens.run_from_results()

        print(f"集成天数: {len(result.dates)}")
        print(f"成分策略:")
        for c in result.constituents:
            print(f"  {c['strategy']}: weight={c['weight']:.4f}, sharpe={c['sharpe']:.4f}")

        print("-" * 60)
        print("集成绩效:")
        print_metrics(result.metrics)

        # 保存结果
        output_dir = args.output or "./output/ensemble"
        os.makedirs(output_dir, exist_ok=True)
        result_dict = {
            "weighting": result.weighting,
            "metrics": _json_safe(result.metrics.__dict__),
            "nav": result.nav,
            "dates": result.dates,
            "constituents": result.constituents,
        }
        with open(os.path.join(output_dir, "ensemble_results.json"), "w", encoding="utf-8") as f:
            json.dump(result_dict, f, indent=2, ensure_ascii=False)
        print(f"\n结果已保存到: {output_dir}")

    except Exception as e:
        print(f"集成失败: {e}")
