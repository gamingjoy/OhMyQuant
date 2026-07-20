"""行业轮动策略 v41 RRG 投票权重网格搜索

v40 使用经验值 [0.5, 0.3, 0.2]，v41 网格搜索更细粒度组合。
参数选择仅基于 IS 表现（2022-2025），OOS 仅用于最终验证。

约束：
- 权重和 = 1.0
- 短期权重 >= 中期权重 >= 长期权重（动量时效性假设）
- 每个权重 >= 0.0

用法:
    python scripts/industry_rotation_v41_weight_grid.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ohmyquant.strategy import StrategyRegistry, StrategyRunner

# 网格搜索权重组合（短期, 中期, 长期），权重和=1.0
# 约束：w_short >= w_mid >= w_long >= 0.0
WEIGHT_CANDIDATES = [
    # baseline (v40)
    (0.5, 0.3, 0.2),
    # 短期更主导
    (0.6, 0.3, 0.1),
    (0.7, 0.2, 0.1),
    (0.6, 0.2, 0.2),
    (0.5, 0.4, 0.1),
    (0.4, 0.4, 0.2),
    # 中期更主导
    (0.4, 0.3, 0.3),
    (0.3, 0.4, 0.3),
    (0.4, 0.5, 0.1),
    # 短期极端主导
    (0.8, 0.1, 0.1),
    (0.7, 0.3, 0.0),
    # 接近等权
    (0.4, 0.3, 0.3),  # 同上重复
]

# 去重保持顺序
seen = set()
WEIGHT_CANDIDATES = [
    w for w in WEIGHT_CANDIDATES
    if not (w in seen or seen.add(w))
]

BASE_VERSION = "v40"  # 在 v40 基础上做权重调优
IS_START = "2022-01-01"
IS_END = "2025-12-31"
OOS_START = "2026-06-01"
OOS_END = "2026-07-16"


def run_backtest(
    weights: tuple[float, float, float],
    start_date: str,
    end_date: str,
) -> dict:
    """运行单个权重组合的回测"""
    config_override = {
        "backtest": {
            "start_date": start_date,
            "end_date": end_date,
        },
        "selection": {
            "industry_rotation": {
                "rs_momentum_vote_weights": list(weights),
            }
        }
    }
    strategy = StrategyRegistry.create(
        "industry_rotation", BASE_VERSION, config_override
    )
    runner = StrategyRunner(strategy.config)
    result = runner.run()

    bt = result.backtest_result
    nav = bt.nav
    daily_returns = bt.daily_returns

    import numpy as np

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

    win_rate = float(np.mean(rets > 0)) if len(rets) > 0 else 0.0
    n_rebalance = len(bt.pool_weight_log)

    return {
        "total_return": total_return,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "n_rebalance": n_rebalance,
        "final_nav": final_nav,
        "n_days": n_days,
    }


def main():
    print("=" * 80)
    print(f"v41 RRG 投票权重网格搜索 (baseline={BASE_VERSION})")
    print(f"IS: {IS_START} ~ {IS_END}")
    print(f"OOS: {OOS_START} ~ {OOS_END}")
    print(f"权重候选数: {len(WEIGHT_CANDIDATES)}")
    print("=" * 80)

    results = []
    for i, weights in enumerate(WEIGHT_CANDIDATES, 1):
        tag = f"w{weights[0]:.1f}_{weights[1]:.1f}_{weights[2]:.1f}"
        print(f"\n[{i}/{len(WEIGHT_CANDIDATES)}] {tag} IS 回测开始...")

        is_result = run_backtest(weights, IS_START, IS_END)
        print(
            f"  IS: 收益={is_result['total_return']*100:+.2f}%  "
            f"Sharpe={is_result['sharpe']:.4f}  "
            f"MaxDD={is_result['max_drawdown']*100:.2f}%  "
            f"调仓={is_result['n_rebalance']}"
        )

        results.append({
            "tag": tag,
            "weights": list(weights),
            "is": is_result,
        })

    # IS 汇总（按 Sharpe 降序）
    print("\n" + "=" * 80)
    print("IS 网格搜索汇总（按Sharpe降序）:")
    print("=" * 80)
    print(
        f"{'tag':<20} {'权重':<22} "
        f"{'IS收益':>10} {'IS Sharpe':>11} {'IS MaxDD':>10} {'胜率':>7}"
    )
    print("-" * 80)
    sorted_results = sorted(results, key=lambda x: x["is"]["sharpe"], reverse=True)
    for r in sorted_results:
        w = r["weights"]
        is_r = r["is"]
        print(
            f"{r['tag']:<20} [{w[0]:.1f},{w[1]:.1f},{w[2]:.1f}]    "
            f"{is_r['total_return']*100:>+9.2f}% "
            f"{is_r['sharpe']:>11.4f} "
            f"{is_r['max_drawdown']*100:>+9.2f}% "
            f"{is_r['win_rate']*100:>6.2f}%"
        )

    best = sorted_results[0]
    baseline = next(r for r in results if tuple(r["weights"]) == (0.5, 0.3, 0.2))
    print(f"\n最优组合(IS): {best['tag']} (Sharpe={best['is']['sharpe']:.4f})")
    print(f"  权重: {best['weights']}")
    print(f"  IS收益: {best['is']['total_return']*100:+.2f}%")
    print(f"\nbaseline (v40=[0.5,0.3,0.2]): Sharpe={baseline['is']['sharpe']:.4f}")

    # 对最优组合做 OOS 验证
    if tuple(best["weights"]) != (0.5, 0.3, 0.2):
        print(f"\n>>> 对最优组合 {best['tag']} 进行 OOS 验证...")
        oos_best = run_backtest(tuple(best["weights"]), OOS_START, OOS_END)
        oos_baseline = run_backtest((0.5, 0.3, 0.2), OOS_START, OOS_END)
        print(
            f"  最优 OOS: 收益={oos_best['total_return']*100:+.2f}%  "
            f"Sharpe={oos_best['sharpe']:.4f}  MaxDD={oos_best['max_drawdown']*100:.2f}%"
        )
        print(
            f"  v40  OOS: 收益={oos_baseline['total_return']*100:+.2f}%  "
            f"Sharpe={oos_baseline['sharpe']:.4f}  MaxDD={oos_baseline['max_drawdown']*100:.2f}%"
        )

        if oos_best["total_return"] >= oos_baseline["total_return"] - 0.001:
            print(f"\n>>> OOS 验证通过！{best['tag']} 可作为新 FINAL")
            best["oos"] = oos_best
            best["oos_baseline"] = oos_baseline
            best["oos_pass"] = True
        else:
            print(f"\n>>> OOS 验证失败！{best['tag']} OOS 收益低于 v40，过拟合")
            best["oos"] = oos_best
            best["oos_baseline"] = oos_baseline
            best["oos_pass"] = False
    else:
        print(f"\n>>> 最优组合 = baseline v40，无需 OOS 验证，权重搜索无效")
        best["oos_pass"] = None

    # 保存结果
    output_dir = Path("output/is_compare/industry_rotation")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "v41_weight_grid_search.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "baseline": BASE_VERSION,
            "candidates": WEIGHT_CANDIDATES,
            "results": sorted_results,
            "best": best,
        }, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n结果已保存: {output_file}")


if __name__ == "__main__":
    main()
