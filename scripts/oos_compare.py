"""样本外回测对比：2026-06-01 建仓，2026-07-01 月度调仓

8 个策略在 2026-06-01 ~ 2026-07-10 期间的样本外表现。
模型训练数据截止 train_end（历史），选股仅在样本外窗口执行。
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import polars as pl

# 确保项目根目录在 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ohmyquant.core.plugin_system import PluginRegistry
from ohmyquant.strategy.registry import StrategyRegistry
from ohmyquant.strategy.runner import StrategyRunner
from ohmyquant.analysis.metrics import compute_metrics

OOS_START = "2026-06-01"
OOS_END = "2026-07-10"

STRATEGIES = [
    ("ycj", "v1"),
    ("ycj", "v2"),
    ("dh", "v1"),
    ("etf", "v1"),
    ("etf", "v2"),
    ("etf", "v3"),
    ("dl", "v1"),
    ("rl", "v1"),
]

OUTPUT_DIR = Path("output/oos_2026")


def run_oos_strategy(strategy_type: str, version: str) -> dict | None:
    """运行单个策略的样本外回测"""
    name = f"{strategy_type}_{version}"
    print(f"\n{'='*60}")
    print(f"运行样本外回测: {name} ({OOS_START} ~ {OOS_END})")
    print(f"{'='*60}")

    t0 = time.time()
    try:
        PluginRegistry.discover_builtin()

        # 创建策略实例（加载原始 config）
        strategy = StrategyRegistry.create(strategy_type, version)

        # 修改回测日期为样本外窗口，统一月度调仓（6/1 建仓 + 7/1 调仓）
        original_start = strategy.config.backtest.start_date
        original_end = strategy.config.backtest.end_date
        strategy.config.backtest.start_date = OOS_START
        strategy.config.backtest.end_date = OOS_END
        strategy.config.rebalance.frequency = "monthly"

        print(f"  原回测区间: {original_start} ~ {original_end}")
        print(f"  样本外区间: {OOS_START} ~ {OOS_END}")
        print(f"  训练截止:   {strategy.config.backtest.train_end}")

        # 运行回测
        runner = StrategyRunner(strategy.config)
        result = runner.run()

        bt = result.backtest_result
        returns = bt.daily_returns
        metrics = compute_metrics(returns)

        elapsed = time.time() - t0
        print(f"  完成 ({elapsed:.1f}s): 净值={bt.final_nav:.4f}, 天数={bt.n_days}")

        # 提取调仓日志：pool_weight_log 记录调仓日的池间权重，
        # stock_weights_by_date 记录每日有效持仓（调仓日 = 持仓变更日）
        rebalance_log = []
        stock_weights_by_date = getattr(bt, "stock_weights_by_date", {}) or {}
        for entry in getattr(bt, "pool_weight_log", []):
            date_str = str(entry.get("date", ""))
            pool_weights = entry.get("pool_weights", {})
            holdings = stock_weights_by_date.get(date_str, {})
            rebalance_log.append({
                "date": date_str,
                "pool_weights": {k: round(v, 4) for k, v in pool_weights.items()},
                "holdings": {k: round(v, 4) for k, v in holdings.items()},
            })

        # 提取每日净值
        nav_series = []
        if hasattr(bt, "nav"):
            nav_series = [round(float(x), 4) for x in bt.nav]
        elif hasattr(bt, "nav_series"):
            nav_series = [round(float(x), 4) for x in bt.nav_series]

        return {
            "strategy": name,
            "strategy_type": strategy_type,
            "version": version,
            "oos_start": OOS_START,
            "oos_end": OOS_END,
            "n_days": int(bt.n_days),
            "final_nav": round(float(bt.final_nav), 4),
            "total_return": round(float(metrics.total_return), 4),
            "annualized_return": round(float(metrics.annualized_return), 4),
            "annualized_volatility": round(float(metrics.annualized_volatility), 4),
            "sharpe_ratio": round(float(metrics.sharpe_ratio), 4),
            "max_drawdown": round(float(metrics.max_drawdown), 4),
            "win_rate": round(float(metrics.win_rate), 4),
            "daily_returns": [round(float(x), 6) for x in returns],
            "dates": [str(d) for d in bt.dates] if hasattr(bt, "dates") and bt.dates else [],
            "nav_series": nav_series,
            "rebalance_log": rebalance_log,
            "elapsed_seconds": round(elapsed, 1),
        }

    except Exception as e:
        elapsed = time.time() - t0
        print(f"  失败 ({elapsed:.1f}s): {e}")
        import traceback
        traceback.print_exc()
        return None


def print_comparison(results: list[dict]) -> None:
    """打印对比表"""
    print(f"\n\n{'='*80}")
    print(f"样本外对比 ({OOS_START} ~ {OOS_END})")
    print(f"{'='*80}")

    # 按总收益排序
    valid = [r for r in results if r is not None]
    valid.sort(key=lambda x: x["total_return"], reverse=True)

    # 指标表
    print(f"\n{'策略':<12} {'总收益':>8} {'年化收益':>8} {'Sharpe':>8} {'最大回撤':>8} {'胜率':>8} {'天数':>6}")
    print("-" * 70)
    for r in valid:
        print(
            f"{r['strategy']:<12} "
            f"{r['total_return']*100:>7.2f}% "
            f"{r['annualized_return']*100:>7.2f}% "
            f"{r['sharpe_ratio']:>8.4f} "
            f"{r['max_drawdown']*100:>7.2f}% "
            f"{r['win_rate']*100:>7.2f}% "
            f"{r['n_days']:>6d}"
        )

    # 调仓明细
    print(f"\n{'='*80}")
    print("建仓/调仓明细")
    print(f"{'='*80}")
    for r in valid:
        print(f"\n--- {r['strategy']} ---")
        for entry in r.get("rebalance_log", []):
            date = entry["date"]
            pool_weights = entry.get("pool_weights", {})
            holdings = entry.get("holdings", {})
            top_holdings = sorted(holdings.items(), key=lambda x: x[1], reverse=True)[:5]
            holdings_str = ", ".join(f"{k}:{v:.1%}" for k, v in top_holdings)
            pool_str = ", ".join(f"{k}:{v:.0%}" for k, v in pool_weights.items())
            print(f"  {date} 池权重[{pool_str}] 持仓{len(holdings)}只, 前5: {holdings_str}")

    # 净值曲线
    print(f"\n{'='*80}")
    print("每日净值")
    print(f"{'='*80}")
    if valid and valid[0].get("dates"):
        dates = valid[0]["dates"]
        header = f"{'日期':<12}" + "".join(f"{r['strategy']:>10}" for r in valid)
        print(header)
        for i, date in enumerate(dates):
            row = f"{date:<12}"
            for r in valid:
                nav = r["nav_series"][i] if i < len(r["nav_series"]) else 0
                row += f"{nav:>10.4f}"
            print(row)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    for strategy_type, version in STRATEGIES:
        r = run_oos_strategy(strategy_type, version)
        results.append(r)

    # 打印对比
    print_comparison(results)

    # 保存结果
    output_file = OUTPUT_DIR / "oos_comparison.json"
    valid_results = [r for r in results if r is not None]
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(valid_results, f, indent=2, ensure_ascii=False)
    print(f"\n结果已保存: {output_file}")

    # 保存各策略单独结果
    for r in valid_results:
        strategy_dir = OUTPUT_DIR / r["strategy"]
        strategy_dir.mkdir(parents=True, exist_ok=True)
        with open(strategy_dir / "results.json", "w", encoding="utf-8") as f:
            json.dump(r, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
