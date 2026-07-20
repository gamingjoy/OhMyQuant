"""行业轮动策略 v39 PE过滤参数网格搜索

网格搜索 pe_lookback × pe_expensive_percentile 的最优组合。
参数选择仅基于IS表现（2022-2025），OOS仅用于最终验证。

用法:
    python scripts/industry_rotation_v39_pe_grid.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ohmyquant.strategy import StrategyRegistry, StrategyRunner

# 网格搜索参数
PE_LOOKBACKS = [250, 500, 750]
PE_EXPENSIVE_PERCENTILES = [0.05, 0.10, 0.15]

BASE_VERSION = "v30"  # 在v30基础上做PE参数调优
IS_START = "2022-01-01"
IS_END = "2025-12-31"


def run_grid_version(
    pe_lookback: int, pe_expensive_percentile: float
) -> dict:
    """运行单个网格点的IS回测"""
    tag = f"pe{pe_lookback}_pct{int(pe_expensive_percentile * 100)}"
    print(f"\n[{tag}] IS 回测开始...")

    config_override = {
        "selection": {
            "industry_rotation": {
                "pe_lookback": pe_lookback,
                "pe_expensive_percentile": pe_expensive_percentile,
            }
        }
    }
    strategy = StrategyRegistry.create(
        "industry_rotation", BASE_VERSION, config_override
    )
    print(f"  pe_lookback={pe_lookback}, pe_expensive_percentile={pe_expensive_percentile}")

    runner = StrategyRunner(strategy.config)
    result = runner.run()

    bt = result.backtest_result
    nav = bt.nav
    daily_returns = bt.daily_returns

    import numpy as np

    n_days = len(nav)
    final_nav = float(nav[-1]) if n_days > 0 else 1.0
    total_return = final_nav - 1.0
    annualized_return = (final_nav ** (242.0 / max(n_days, 1))) - 1.0

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

    print(
        f"  [{tag}] 总收益={total_return*100:+.2f}%  "
        f"Sharpe={sharpe:.4f}  最大回撤={max_drawdown*100:.2f}%  "
        f"调仓={n_rebalance}"
    )

    return {
        "tag": tag,
        "pe_lookback": pe_lookback,
        "pe_expensive_percentile": pe_expensive_percentile,
        "total_return": total_return,
        "annualized_return": annualized_return,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "n_rebalance": n_rebalance,
    }


def main():
    print("=" * 70)
    print(f"v39 PE参数网格搜索 (baseline={BASE_VERSION})")
    print(f"IS: {IS_START} ~ {IS_END}")
    print(f"Grid: pe_lookback={PE_LOOKBACKS} × pe_expensive_percentile={PE_EXPENSIVE_PERCENTILES}")
    print("=" * 70)

    results = []
    for pe_lb in PE_LOOKBACKS:
        for pe_pct in PE_EXPENSIVE_PERCENTILES:
            r = run_grid_version(pe_lb, pe_pct)
            results.append(r)

    # 输出汇总
    print("\n" + "=" * 70)
    print("IS 网格搜索汇总（按Sharpe降序）:")
    print("=" * 70)
    print(
        f"{'tag':<20} {'pe_lb':>6} {'pe_pct':>7} "
        f"{'总收益':>10} {'Sharpe':>8} {'最大回撤':>10} {'胜率':>7}"
    )
    print("-" * 70)
    sorted_results = sorted(results, key=lambda x: x["sharpe"], reverse=True)
    for r in sorted_results:
        print(
            f"{r['tag']:<20} {r['pe_lookback']:>6} "
            f"{r['pe_expensive_percentile']:>7.2f} "
            f"{r['total_return']*100:>+9.2f}% "
            f"{r['sharpe']:>8.4f} "
            f"{r['max_drawdown']*100:>+9.2f}% "
            f"{r['win_rate']*100:>6.2f}%"
        )

    best = sorted_results[0]
    print(f"\n最优组合(IS): {best['tag']} (Sharpe={best['sharpe']:.4f})")
    print(f"  pe_lookback={best['pe_lookback']}")
    print(f"  pe_expensive_percentile={best['pe_expensive_percentile']}")

    # 保存结果
    output_dir = Path("output/is_compare/industry_rotation")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "v39_pe_grid_search.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "baseline": BASE_VERSION,
            "grid": {
                "pe_lookbacks": PE_LOOKBACKS,
                "pe_expensive_percentiles": PE_EXPENSIVE_PERCENTILES,
            },
            "results": sorted_results,
            "best": best,
        }, f, indent=2, ensure_ascii=False)
    print(f"\n结果已保存: {output_file}")


if __name__ == "__main__":
    main()
