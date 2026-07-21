"""行业轮动策略 v45 探索：PE调节强度alpha网格搜索 + PE/PB双估值调节

设计目的：
  v43 alpha=0.2 是经验值，未做系统搜索。
  本脚本在 v43 基础上做两件事：
    1. alpha 网格搜索 [0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5]（单参数，过拟合风险低）
    2. PE/PB 双估值调节（结构改进，PE+PB 同样 alpha=0.1，总强度 0.2 与 v43 相同）
  验证标准：
    - IS Sharpe > v43 IS Sharpe (0.5716)
    - 2018-2021 跨周期稳定（不过拟合）
    - 各年份表现不退化（特别关注2024年）

用法:
    python scripts/industry_rotation_v45_explore.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from ohmyquant.strategy import StrategyRegistry, StrategyRunner


def run_backtest(
    version: str,
    config_override: dict,
    start_date: str = "2022-01-01",
    end_date: str = "2025-12-31",
) -> dict:
    """运行指定配置的回测"""
    config = {
        "backtest": {
            "start_date": start_date,
            "end_date": end_date,
        }
    }
    # 深合并 config_override
    for k, v in (config_override or {}).items():
        if k in config and isinstance(config[k], dict) and isinstance(v, dict):
            config[k].update(v)
        else:
            config[k] = v

    strategy = StrategyRegistry.create("industry_rotation", version, config)
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

    win_rate = float(np.mean(rets > 0)) if len(rets) > 0 else 0.0
    n_rebalance = len(bt.pool_weight_log)

    return {
        "total_return": total_return,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "n_rebalance": n_rebalance,
        "n_days": n_days,
        "final_nav": final_nav,
    }


def print_result(label: str, r: dict) -> None:
    print(
        f"  {label:<30} "
        f"收益={r['total_return']*100:>+7.2f}%  "
        f"Sharpe={r['sharpe']:>6.4f}  "
        f"MaxDD={r['max_drawdown']*100:>+6.2f}%  "
        f"调仓={r['n_rebalance']:>3}"
    )


def main():
    print("=" * 80)
    print("v45 探索：PE调节强度alpha网格搜索 + PE/PB双估值调节")
    print("=" * 80)

    all_results = {}

    # ========== Part 1: alpha 网格搜索 ==========
    print("\n【Part 1】alpha 网格搜索 (2022-2025 IS)")
    print("-" * 80)

    alphas = [0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5]
    alpha_results = []

    for alpha in alphas:
        print(f"\n  >> alpha={alpha}:")
        config_override = {
            "selection": {
                "industry_rotation": {
                    "pe_vote_adjust_alpha": alpha,
                }
            }
        }
        r = run_backtest("v43", config_override, "2022-01-01", "2025-12-31")
        r["alpha"] = alpha
        print_result(f"v43 alpha={alpha}", r)
        alpha_results.append(r)

    print("\n  alpha 网格搜索汇总（按IS Sharpe降序）:")
    print(f"  {'alpha':<8} {'收益':>10} {'Sharpe':>10} {'MaxDD':>10}")
    sorted_alpha = sorted(alpha_results, key=lambda x: x["sharpe"], reverse=True)
    for r in sorted_alpha:
        print(
            f"  {r['alpha']:<8} "
            f"{r['total_return']*100:>+9.2f}% "
            f"{r['sharpe']:>10.4f} "
            f"{r['max_drawdown']*100:>+9.2f}%"
        )
    best_alpha = sorted_alpha[0]["alpha"]
    best_alpha_sharpe = sorted_alpha[0]["sharpe"]
    print(f"\n  最优alpha: {best_alpha} (IS Sharpe {best_alpha_sharpe:.4f})")
    all_results["alpha_grid"] = alpha_results
    all_results["best_alpha"] = best_alpha

    # ========== Part 2: 最优alpha的跨周期验证 ==========
    print(f"\n\n【Part 2】最优alpha={best_alpha} 跨周期验证 (2018-2021)")
    print("-" * 80)

    config_best = {
        "selection": {
            "industry_rotation": {
                "pe_vote_adjust_alpha": best_alpha,
            }
        }
    }
    r_best_2018 = run_backtest("v43", config_best, "2018-01-01", "2021-12-31")
    r_v43_2018 = run_backtest("v43", None, "2018-01-01", "2021-12-31")
    print(f"\n  >> 2018-2021 (4年):")
    print_result(f"v43 alpha={best_alpha}", r_best_2018)
    print_result("v43 alpha=0.2 (baseline)", r_v43_2018)
    all_results["best_alpha_2018_2021"] = r_best_2018
    all_results["v43_2018_2021"] = r_v43_2018

    # ========== Part 3: PE/PB 双估值调节 ==========
    print("\n\n【Part 3】PE/PB 双估值调节（结构改进）")
    print("-" * 80)
    print("  设计: PE alpha=0.1 + PB alpha=0.1，总强度 0.2 与 v43 相同")
    print("  假设: PB提供与企业净资产相关的估值维度，与PE(盈利)互补")
    print()

    # 注：当前selector只支持PE调节，PB调节需要新代码
    # 这里仅记录设计，实际实现需要修改 selector
    print("  [INFO] PB调节需要修改 selector 代码，本脚本仅完成alpha网格搜索")
    print("  [INFO] v45 实际策略文件将基于最优alpha创建")
    print("  [INFO] PB双估值调节作为 v46 方向")

    # ========== Part 4: 最优alpha 分年份表现 ==========
    print(f"\n\n【Part 4】最优alpha={best_alpha} 分年份表现")
    print("-" * 80)

    yearly_results = []
    for year in [2022, 2023, 2024, 2025]:
        start = f"{year}-01-01"
        end = f"{year}-12-31"
        r_best = run_backtest("v43", config_best, start, end)
        r_v43 = run_backtest("v43", None, start, end)
        print(f"\n  >> {year}年:")
        print_result(f"v43 alpha={best_alpha}", r_best)
        print_result("v43 alpha=0.2 (baseline)", r_v43)
        yearly_results.append({
            "year": year,
            "best_alpha": r_best,
            "v43_baseline": r_v43,
        })
    all_results["yearly"] = yearly_results

    # ========== Part 5: 总结与判断 ==========
    print("\n\n【Part 5】总结与判断")
    print("-" * 80)

    v43_baseline_sharpe = next(
        (r["sharpe"] for r in alpha_results if r["alpha"] == 0.2), None
    )
    print(f"  v43 baseline (alpha=0.2) IS Sharpe: {v43_baseline_sharpe:.4f}")
    print(f"  最优 alpha={best_alpha} IS Sharpe: {best_alpha_sharpe:.4f}")
    print(f"  Sharpe 改善: {best_alpha_sharpe - v43_baseline_sharpe:+.4f}")

    if best_alpha_sharpe > v43_baseline_sharpe + 0.005:
        print(f"\n  ✓ 建议创建 v45: alpha={best_alpha}")
        print(f"    IS Sharpe 改善 {best_alpha_sharpe - v43_baseline_sharpe:+.4f}")
        print(f"    2018-2021 跨周期 Sharpe: {r_best_2018['sharpe']:.4f} (v43 baseline: {r_v43_2018['sharpe']:.4f})")
    else:
        print(f"\n  ✗ alpha 网格搜索未显著改善IS，v43 alpha=0.2 已是合适值")
        print(f"    建议: 跳过 v45 alpha优化，直接尝试 v46 双估值调节或其他方向")

    # 保存结果
    output_dir = Path("output/is_compare/industry_rotation")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "v45_alpha_grid_search.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n结果已保存: {output_file}")


if __name__ == "__main__":
    main()
