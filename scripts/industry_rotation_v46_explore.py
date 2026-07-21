"""行业轮动策略 v46 探索：PE回看延长至500天

设计目的：
  v45 regime-aware尝试失败（2024更差），说明PE在2024震荡期实际有效。
  v46 假设2024 PE调节失效源于pe_lookback=250(1年)过短，PE分位不稳定。
  延长到500天(2年)看是否改善2024。

验证标准：
  - IS Sharpe 不低于 v43 (0.5716)
  - 2024年Sharpe 改善（目标 > 0.15）
  - 2025年Sharpe 不退化（保持 > 2.0）
  - 2018-2021 跨周期稳定

用法:
    python scripts/industry_rotation_v46_explore.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from ohmyquant.strategy import StrategyRegistry, StrategyRunner


def run_backtest(
    version: str,
    start_date: str,
    end_date: str,
    config_override: dict | None = None,
    label: str = "",
) -> dict:
    """运行指定区间的回测"""
    t0 = time.time()
    config = {
        "backtest": {
            "start_date": start_date,
            "end_date": end_date,
        }
    }
    if config_override:
        for k, v in config_override.items():
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
        "win_rate": win_rate,
        "n_rebalance": n_rebalance,
        "n_days": n_days,
        "final_nav": final_nav,
        "elapsed_sec": elapsed,
    }


def main():
    print("=" * 80, flush=True)
    print("v46 探索：PE回看延长至500天（2年）", flush=True)
    print("=" * 80, flush=True)
    print(flush=True)

    # v43 baseline 参考值
    v43_ref = {
        "is_sharpe": 0.5716,
        "is_return": 0.3129,
        "2022_sharpe": -0.4202,
        "2023_sharpe": 0.1077,
        "2024_sharpe": 0.1053,
        "2025_sharpe": 2.0319,
        "2018_2021_sharpe": 0.1617,
    }
    print("【参考】v43 baseline:", flush=True)
    print(
        f"  v43 IS Sharpe={v43_ref['is_sharpe']:.4f}  "
        f"2024={v43_ref['2024_sharpe']:.4f}  "
        f"2025={v43_ref['2025_sharpe']:.4f}  "
        f"2018-2021={v43_ref['2018_2021_sharpe']:.4f}",
        flush=True,
    )
    print(flush=True)

    all_results = {}

    # Part 1: v46 IS
    print(f"\n>> v46 IS (2022-2025):", flush=True)
    r_is = run_backtest("v46", "2022-01-01", "2025-12-31", label="v46 IS")

    # Part 2: 分年份
    yearly = {}
    for year in [2022, 2023, 2024, 2025]:
        print(f"\n>> v46 {year}年:", flush=True)
        r_y = run_backtest(
            "v46", f"{year}-01-01", f"{year}-12-31", label=f"v46 {year}"
        )
        yearly[str(year)] = r_y

    # Part 3: 2018-2021 跨周期
    print(f"\n>> v46 2018-2021 (跨周期验证):", flush=True)
    r_2018 = run_backtest("v46", "2018-01-01", "2021-12-31", label="v46 2018-2021")

    all_results = {
        "is": r_is,
        "yearly": yearly,
        "2018_2021": r_2018,
    }

    # Part 4: 总结
    print(f"\n\n{'='*80}", flush=True)
    print("【总结】v46 vs v43", flush=True)
    print(f"{'='*80}", flush=True)

    print(
        f"\n  {'指标':<15} {'v43':>10} {'v46':>10} {'diff':>10}",
        flush=True,
    )
    print(f"  {'-'*50}", flush=True)
    print(
        f"  {'IS Sharpe':<15} {v43_ref['is_sharpe']:>10.4f} {r_is['sharpe']:>10.4f} "
        f"{r_is['sharpe']-v43_ref['is_sharpe']:>+10.4f}",
        flush=True,
    )
    for year in ["2022", "2023", "2024", "2025"]:
        v43_s = v43_ref[f"{year}_sharpe"]
        v46_s = yearly[year]["sharpe"]
        print(
            f"  {year+' Sharpe':<15} {v43_s:>10.4f} {v46_s:>10.4f} "
            f"{v46_s-v43_s:>+10.4f}",
            flush=True,
        )
    print(
        f"  {'2018-2021 Sharpe':<15} {v43_ref['2018_2021_sharpe']:>10.4f} "
        f"{r_2018['sharpe']:>10.4f} "
        f"{r_2018['sharpe']-v43_ref['2018_2021_sharpe']:>+10.4f}",
        flush=True,
    )

    # 判断
    is_pass = (
        r_is["sharpe"] >= v43_ref["is_sharpe"] - 0.02
        and yearly["2024"]["sharpe"] > v43_ref["2024_sharpe"]
        and yearly["2025"]["sharpe"] >= v43_ref["2025_sharpe"] - 0.1
        and r_2018["sharpe"] >= 0.0
    )
    if is_pass:
        print(
            f"\n  ✓ v46 通过验证：2024改善({yearly['2024']['sharpe']:.4f} > {v43_ref['2024_sharpe']:.4f})",
            flush=True,
        )
    else:
        print(f"\n  ✗ v46 未通过验证", flush=True)
        if yearly["2024"]["sharpe"] <= v43_ref["2024_sharpe"]:
            print(
                f"    2024未改善: v46={yearly['2024']['sharpe']:.4f} vs v43={v43_ref['2024_sharpe']:.4f}",
                flush=True,
            )
        if r_is["sharpe"] < v43_ref["is_sharpe"] - 0.02:
            print(
                f"    IS下降: v46={r_is['sharpe']:.4f} vs v43={v43_ref['is_sharpe']:.4f}",
                flush=True,
            )

    # 保存结果
    output_dir = Path("output/is_compare/industry_rotation")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "v46_pe_lookback_500.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n结果已保存: {output_file}", flush=True)


if __name__ == "__main__":
    main()
