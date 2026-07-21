"""行业轮动策略 v43 跨周期一致性验证 + 分年份表现分析

不做参数搜索，仅验证v43参数在不同区间的稳定性：
1. 分年份IS表现（2022/2023/2024/2025）- 看近两年是否需要优化
2. 跨周期验证（2018-2021）- 验证参数稳定性，避免过拟合

用法:
    python scripts/industry_rotation_v43_stability.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from ohmyquant.strategy import StrategyRegistry, StrategyRunner


def run_period_backtest(
    version: str,
    start_date: str,
    end_date: str,
    config_override: dict | None = None,
) -> dict:
    """运行指定区间的回测"""
    strategy = StrategyRegistry.create(
        "industry_rotation", version, config_override
    )
    runner = StrategyRunner(strategy.config)
    result = runner.run()

    bt = result.backtest_result
    nav = bt.nav
    daily_returns = bt.daily_returns

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

    return {
        "version": version,
        "start_date": start_date,
        "end_date": end_date,
        "total_return": total_return,
        "annualized_return": annualized_return,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "n_rebalance": n_rebalance,
        "n_days": n_days,
        "final_nav": final_nav,
    }


def print_result(label: str, r: dict) -> None:
    print(
        f"  {label:<25} "
        f"收益={r['total_return']*100:>+7.2f}%  "
        f"Sharpe={r['sharpe']:>6.4f}  "
        f"MaxDD={r['max_drawdown']*100:>+6.2f}%  "
        f"调仓={r['n_rebalance']:>3}"
    )


def main():
    print("=" * 80)
    print("v43 跨周期一致性验证 + 分年份表现分析")
    print("=" * 80)

    # ========== Part 1: 分年份IS表现 ==========
    print("\n【Part 1】v43 分年份IS表现 (2022/2023/2024/2025)")
    print("-" * 80)

    years = [(2022, 2022), (2023, 2023), (2024, 2024), (2025, 2025)]
    v43_yearly = []
    v41_yearly = []

    for year_start, year_end in years:
        start_date = f"{year_start}-01-01"
        end_date = f"{year_end}-12-31"
        config = {"backtest": {"start_date": start_date, "end_date": end_date}}

        print(f"\n  >> {year_start}年:")
        r_v43 = run_period_backtest("v43", start_date, end_date, config)
        r_v41 = run_period_backtest("v41", start_date, end_date, config)
        print_result("v43", r_v43)
        print_result("v41 (旧final)", r_v41)
        v43_yearly.append({"year": year_start, **r_v43})
        v41_yearly.append({"year": year_start, **r_v41})

    print("\n  分年份对比汇总:")
    print(f"  {'年份':<6} {'v43 Sharpe':>12} {'v41 Sharpe':>12} {'v43 收益':>10} {'v41 收益':>10} {'差异':>10}")
    for v43_y, v41_y in zip(v43_yearly, v41_yearly):
        diff = v43_y["sharpe"] - v41_y["sharpe"]
        print(
            f"  {v43_y['year']:<6} "
            f"{v43_y['sharpe']:>12.4f} "
            f"{v41_y['sharpe']:>12.4f} "
            f"{v43_y['total_return']*100:>+9.2f}% "
            f"{v41_y['total_return']*100:>+9.2f}% "
            f"{diff*100:>+9.4f}"
        )

    # ========== Part 2: 跨周期验证 (2018-2021) ==========
    print("\n\n【Part 2】v43 跨周期验证 (2018-2021)")
    print("-" * 80)
    print("  目的: 验证v43参数在IS区间之前的稳定性，避免过拟合")

    config_2018_2021 = {
        "backtest": {
            "start_date": "2018-01-01",
            "end_date": "2021-12-31",
        }
    }
    print("\n  >> 2018-2021 (4年):")
    r_v43_2018 = run_period_backtest(
        "v43", "2018-01-01", "2021-12-31", config_2018_2021
    )
    r_v41_2018 = run_period_backtest(
        "v41", "2018-01-01", "2021-12-31", config_2018_2021
    )
    print_result("v43", r_v43_2018)
    print_result("v41 (旧final)", r_v41_2018)

    # 2018-2021 分年份
    print("\n  >> 2018-2021 分年份:")
    years_pre = [(2018, 2018), (2019, 2019), (2020, 2020), (2021, 2021)]
    for year_start, year_end in years_pre:
        start_date = f"{year_start}-01-01"
        end_date = f"{year_end}-12-31"
        config = {"backtest": {"start_date": start_date, "end_date": end_date}}
        r_v43_y = run_period_backtest("v43", start_date, end_date, config)
        r_v41_y = run_period_backtest("v41", start_date, end_date, config)
        print(f"\n  >> {year_start}年:")
        print_result("v43", r_v43_y)
        print_result("v41", r_v41_y)

    # ========== Part 3: 总结 ==========
    print("\n\n【Part 3】总结与判断")
    print("-" * 80)

    # 近两年vs前两年
    v43_2024_2025 = [y for y in v43_yearly if y["year"] in [2024, 2025]]
    v43_2022_2023 = [y for y in v43_yearly if y["year"] in [2022, 2023]]

    avg_sharpe_recent = np.mean([y["sharpe"] for y in v43_2024_2025])
    avg_sharpe_early = np.mean([y["sharpe"] for y in v43_2022_2023])

    print(f"  v43 近两年(2024-2025)平均Sharpe: {avg_sharpe_recent:.4f}")
    print(f"  v43 前两年(2022-2023)平均Sharpe: {avg_sharpe_early:.4f}")
    print(f"  差异: {avg_sharpe_recent - avg_sharpe_early:+.4f}")

    if r_v43_2018["n_days"] > 100:
        print(f"\n  v43 跨周期(2018-2021)Sharpe: {r_v43_2018['sharpe']:.4f}")
        print(f"  v43 跨周期(2018-2021)收益: {r_v43_2018['total_return']*100:+.2f}%")

    # 保存结果
    output_dir = Path("output/is_compare/industry_rotation")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "v43_stability_analysis.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "v43_yearly_is": v43_yearly,
            "v41_yearly_is": v41_yearly,
            "v43_2018_2021": r_v43_2018,
            "v41_2018_2021": r_v41_2018,
        }, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n结果已保存: {output_file}")


if __name__ == "__main__":
    main()
