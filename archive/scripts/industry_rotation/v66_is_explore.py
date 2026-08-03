"""v66 IS 验证：v64 + regime-aware hk_hold（熊市禁用北向因子）

用法: python scripts/industry_rotation_v66_is_explore.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from ohmyquant.strategy import StrategyRegistry, StrategyRunner


def run_backtest(version, start_date, end_date, label=""):
    t0 = time.time()
    config = {"backtest": {"start_date": start_date, "end_date": end_date}}
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
    n_rebalance = len(bt.pool_weight_log)
    elapsed = time.time() - t0
    print(
        f"  [{label:<25}] 收益={total_return*100:>+7.2f}%  "
        f"Sharpe={sharpe:>6.4f}  MaxDD={max_drawdown*100:>+6.2f}%  "
        f"调仓={n_rebalance:>3}  ({elapsed:.0f}s)",
        flush=True,
    )
    return {
        "total_return": total_return,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "n_rebalance": n_rebalance,
        "n_days": n_days,
        "final_nav": final_nav,
        "elapsed_sec": elapsed,
    }


def main():
    v53_ref = {
        "is_sharpe": 0.6269,
        "2022_sharpe": -0.1834,
        "2023_sharpe": 0.1824,
        "2024_sharpe": 0.1153,
        "2025_sharpe": 2.0359,
        "2018_2021_sharpe": 0.1669,
    }
    v64_ref = {
        "is_sharpe": 0.6480,
        "2022_sharpe": -0.4223,
        "2023_sharpe": 0.2868,
        "2024_sharpe": 0.1925,
        "2025_sharpe": 2.0860,
        "2018_2021_sharpe": 0.2108,
    }

    print("=" * 80, flush=True)
    print("v66 IS 验证：v64 + regime-aware hk_hold（熊市禁用）", flush=True)
    print("=" * 80, flush=True)
    print(f"参考 v53: IS={v53_ref['is_sharpe']:.4f} 2022={v53_ref['2022_sharpe']:.4f} "
          f"2025={v53_ref['2025_sharpe']:.4f}", flush=True)
    print(f"参考 v64: IS={v64_ref['is_sharpe']:.4f} 2022={v64_ref['2022_sharpe']:.4f} "
          f"2025={v64_ref['2025_sharpe']:.4f}", flush=True)
    print(flush=True)

    results = {}

    print(f">> v66 IS (2022-2025):", flush=True)
    r_is = run_backtest("v66", "2022-01-01", "2025-12-31", label="v66 IS")

    if r_is["sharpe"] < 0.3:
        print(f"\n  ⚠ v66 IS Sharpe={r_is['sharpe']:.4f} < 0.3，早停", flush=True)
        results = {"is": r_is, "early_stopped": True}
        _save(results)
        return

    yearly = {}
    for year in [2022, 2023, 2024, 2025]:
        print(f"\n>> v66 {year}年:", flush=True)
        yearly[str(year)] = run_backtest(
            "v66", f"{year}-01-01", f"{year}-12-31", label=f"v66 {year}"
        )

    print(f"\n>> v66 2018-2021 (跨周期验证):", flush=True)
    r_2018 = run_backtest("v66", "2018-01-01", "2021-12-31", label="v66 2018-2021")

    results = {"is": r_is, "yearly": yearly, "2018_2021": r_2018}

    print(f"\n\n{'='*80}", flush=True)
    print(f"【总结】v53 vs v64 vs v66", flush=True)
    print(f"{'='*80}", flush=True)
    print(f"\n  {'指标':<15} {'v53':>10} {'v64':>10} {'v66':>10} {'v66-v53':>10}", flush=True)
    print(f"  {'-'*60}", flush=True)
    print(f"  {'IS Sharpe':<15} {v53_ref['is_sharpe']:>10.4f} {v64_ref['is_sharpe']:>10.4f} "
          f"{r_is['sharpe']:>10.4f} {r_is['sharpe']-v53_ref['is_sharpe']:>+10.4f}", flush=True)
    for year in ["2022", "2023", "2024", "2025"]:
        v53_s = v53_ref[f"{year}_sharpe"]
        v64_s = v64_ref[f"{year}_sharpe"]
        v_s = yearly[year]["sharpe"]
        print(f"  {year+' Sharpe':<15} {v53_s:>10.4f} {v64_s:>10.4f} "
              f"{v_s:>10.4f} {v_s-v53_s:>+10.4f}", flush=True)
    print(f"  {'2018-2021':<15} {v53_ref['2018_2021_sharpe']:>10.4f} "
          f"{v64_ref['2018_2021_sharpe']:>10.4f} "
          f"{r_2018['sharpe']:>10.4f} "
          f"{r_2018['sharpe']-v53_ref['2018_2021_sharpe']:>+10.4f}", flush=True)

    is_pass = (
        r_is["sharpe"] >= v53_ref["is_sharpe"] - 0.02
        and yearly["2025"]["sharpe"] >= v53_ref["2025_sharpe"] - 0.1
        and r_2018["sharpe"] >= -0.05
    )
    all_years_ok = (
        is_pass
        and r_is["sharpe"] > v53_ref["is_sharpe"]
        and yearly["2022"]["sharpe"] >= v53_ref["2022_sharpe"] - 0.02
        and yearly["2023"]["sharpe"] >= v53_ref["2023_sharpe"] - 0.02
        and r_2018["sharpe"] >= v53_ref["2018_2021_sharpe"] - 0.05
    )
    if all_years_ok:
        print(f"\n  ★ v66 全面超越v53！", flush=True)
    elif is_pass:
        print(f"\n  ○ v66 通过基本验证", flush=True)
    else:
        print(f"\n  ✗ v66 未通过验证", flush=True)

    _save(results)


def _save(results):
    output_dir = Path("output/is_compare/industry_rotation")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "v66_hk_hold_ra.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n结果已保存: {output_file}", flush=True)


if __name__ == "__main__":
    main()
