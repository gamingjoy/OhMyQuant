"""v41 OOS 验证：对最优IS组合 [0.3, 0.4, 0.3] 进行 OOS 验证

IS网格搜索已完成，最优组合为 [0.3, 0.4, 0.3] (IS Sharpe 0.4803)。
本脚本仅运行 OOS 验证，避免重复运行11个IS回测。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from ohmyquant.strategy import StrategyRegistry, StrategyRunner

BASE_VERSION = "v40"
OOS_START = "2026-06-01"
OOS_END = "2026-07-16"

# 验证组合
CANDIDATES = [
    ("v40_baseline", [0.5, 0.3, 0.2]),  # baseline
    ("v41_best", [0.3, 0.4, 0.3]),  # IS最优
    ("v41_short_dominant", [0.6, 0.3, 0.1]),  # 短期主导次优
]


def run_oos(weights: list[float], label: str) -> dict:
    """运行OOS回测"""
    config_override = {
        "backtest": {
            "start_date": OOS_START,
            "end_date": OOS_END,
        },
        "selection": {
            "industry_rotation": {
                "rs_momentum_vote_weights": weights,
            }
        },
    }
    strategy = StrategyRegistry.create(
        "industry_rotation", BASE_VERSION, config_override
    )
    runner = StrategyRunner(strategy.config)
    result = runner.run()

    bt = result.backtest_result
    nav = bt.nav
    daily_returns = bt.daily_returns

    n_days = len(nav)
    final_nav = float(nav[-1]) if n_days > 0 else 1.0
    total_return = final_nav - 1.0

    rets = daily_returns.to_numpy()
    rets = rets[~np.isnan(rets)]
    sharpe = (
        float(np.mean(rets) / np.std(rets, ddof=1) * np.sqrt(242))
        if len(rets) > 1 and np.std(rets, ddof=1) > 0
        else 0.0
    )

    nav_arr = nav.to_numpy()
    peak = np.maximum.accumulate(nav_arr)
    drawdown = (nav_arr - peak) / peak
    max_drawdown = float(np.min(drawdown))

    # 获取持仓
    stock_weights = bt.stock_weights_by_date
    last_holdings = {}
    if stock_weights:
        last_date = sorted(stock_weights.keys())[-1]
        last_holdings = stock_weights[last_date]

    print(
        f"  {label:<25} weights={weights}  "
        f"OOS收益={total_return*100:+.2f}%  "
        f"Sharpe={sharpe:.4f}  "
        f"MaxDD={max_drawdown*100:.2f}%  "
        f"持仓={len(last_holdings)}"
    )

    return {
        "label": label,
        "weights": weights,
        "total_return": total_return,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "n_days": n_days,
        "n_holdings": len(last_holdings),
        "holdings": {k: round(v, 4) for k, v in last_holdings.items()},
    }


def main():
    print("=" * 80)
    print(f"v41 OOS 验证 (baseline={BASE_VERSION})")
    print(f"OOS: {OOS_START} ~ {OOS_END}")
    print(f"候选数: {len(CANDIDATES)}")
    print("=" * 80)

    results = []
    for label, weights in CANDIDATES:
        print(f"\n[{label}] OOS 回测开始...")
        result = run_oos(weights, label)
        results.append(result)

    # 汇总
    print("\n" + "=" * 80)
    print("OOS 验证汇总:")
    print("=" * 80)
    print(
        f"{'label':<25} {'权重':<22} "
        f"{'OOS收益':>10} {'OOS Sharpe':>11} {'OOS MaxDD':>10} {'持仓':>6}"
    )
    print("-" * 80)
    for r in results:
        w = r["weights"]
        print(
            f"{r['label']:<25} [{w[0]:.1f},{w[1]:.1f},{w[2]:.1f}]    "
            f"{r['total_return']*100:>+9.2f}% "
            f"{r['sharpe']:>11.4f} "
            f"{r['max_drawdown']*100:>+9.2f}% "
            f"{r['n_holdings']:>6d}"
        )

    # 判断
    baseline = next(r for r in results if r["label"] == "v40_baseline")
    best = next(r for r in results if r["label"] == "v41_best")

    print(f"\n>>> 对比 v41_best vs v40_baseline:")
    print(f"  OOS收益: {best['total_return']*100:+.2f}% vs {baseline['total_return']*100:+.2f}% "
          f"(diff {(best['total_return']-baseline['total_return'])*100:+.2f}pp)")
    print(f"  OOS Sharpe: {best['sharpe']:.4f} vs {baseline['sharpe']:.4f} "
          f"(diff {best['sharpe']-baseline['sharpe']:+.4f})")

    if best["total_return"] >= baseline["total_return"] - 0.001:
        print(f"\n>>> OOS 验证通过！v41_best [0.3,0.4,0.3] 可作为新 FINAL")
    else:
        print(f"\n>>> OOS 验证失败！v41_best OOS 收益低于 v40，过拟合，保持 v40 为 FINAL")

    # 持仓对比
    print(f"\n>>> 持仓对比:")
    print(f"  v40_baseline 持仓: {len(baseline['holdings'])} 只")
    for code, w in sorted(baseline["holdings"].items(), key=lambda x: x[1], reverse=True):
        print(f"    {code:<12} {w:.4f}")
    print(f"  v41_best 持仓: {len(best['holdings'])} 只")
    for code, w in sorted(best["holdings"].items(), key=lambda x: x[1], reverse=True):
        print(f"    {code:<12} {w:.4f}")

    # 保存结果
    output_dir = Path("output/oos_compare/industry_rotation")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "v41_oos_validation.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "baseline": BASE_VERSION,
            "oos_start": OOS_START,
            "oos_end": OOS_END,
            "results": results,
        }, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n结果已保存: {output_file}")


if __name__ == "__main__":
    main()
