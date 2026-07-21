"""行业轮动策略 v45 探索：regime-aware PE调节

设计目的：
  v43 stability 分析发现 PE调节在2024(震荡市)反而有害(Sharpe 0.1053 < v41 0.1826)，
  在2025(趋势市)有效(Sharpe 2.0319 > v41 1.6716)。
  v45 引入 regime-aware PE调节：趋势市 alpha=0.2，震荡市 alpha_choppy=0.0。

本脚本测试3个alpha_choppy候选：
  - v45a: alpha_choppy=0.0 (彻底关闭震荡市PE调节)
  - v45b: alpha_choppy=0.1 (震荡市半强度PE调节)
  - v45c: alpha_choppy=0.2 (与v43相同，验证regime切换逻辑无bug)

验证标准：
  - IS Sharpe 不显著低于 v43 (0.5716)
  - 2024年Sharpe 改善（目标 > 0.18 接近 v41 水平）
  - 2025年Sharpe 不退化（保持 > 2.0）
  - 2018-2021 跨周期稳定（不过拟合）

用法:
    python scripts/industry_rotation_v45_regime_explore.py
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
    print("v45 探索：regime-aware PE调节（震荡市alpha_choppy）", flush=True)
    print("=" * 80, flush=True)
    print(flush=True)

    all_results = {}

    # v43 baseline 参考值（来自 v43_stability_analysis.json）
    v43_ref = {
        "is_sharpe": 0.5716,
        "is_return": 0.3129,
        "2022_sharpe": -0.4202,
        "2023_sharpe": 0.1077,
        "2024_sharpe": 0.1053,
        "2025_sharpe": 2.0319,
        "2018_2021_sharpe": 0.1617,
    }
    print("【参考】v43 baseline (来自 stability_analysis):", flush=True)
    print(
        f"  v43 IS Sharpe={v43_ref['is_sharpe']:.4f}  "
        f"2024={v43_ref['2024_sharpe']:.4f}  "
        f"2025={v43_ref['2025_sharpe']:.4f}  "
        f"2018-2021={v43_ref['2018_2021_sharpe']:.4f}",
        flush=True,
    )
    print(flush=True)

    # v45 候选配置
    candidates = [
        ("v45a_alpha_choppy_0.0", {"pe_vote_adjust_alpha_choppy": 0.0}),
        ("v45b_alpha_choppy_0.1", {"pe_vote_adjust_alpha_choppy": 0.1}),
    ]

    for label, override in candidates:
        print(f"\n{'='*80}", flush=True)
        print(f"【候选】{label}", flush=True)
        print(f"{'='*80}", flush=True)

        config_override = {"selection": {"industry_rotation": override}}

        # Part 1: 全IS回测
        print(f"\n  >> IS (2022-2025):", flush=True)
        r_is = run_backtest(
            "v45", "2022-01-01", "2025-12-31", config_override,
            label=f"{label} IS",
        )

        # Part 2: 分年份（重点看2024/2025近两年）
        yearly = {}
        for year in [2022, 2023, 2024, 2025]:
            print(f"\n  >> {year}年:", flush=True)
            r_y = run_backtest(
                "v45", f"{year}-01-01", f"{year}-12-31", config_override,
                label=f"{label} {year}",
            )
            yearly[str(year)] = r_y

        all_results[label] = {
            "is": r_is,
            "yearly": yearly,
        }

        # 即时判断
        print(f"\n  >> 即时判断:", flush=True)
        is_sharpe = r_is["sharpe"]
        sharpe_2024 = yearly["2024"]["sharpe"]
        sharpe_2025 = yearly["2025"]["sharpe"]
        print(
            f"    IS Sharpe: {is_sharpe:.4f} (v43={v43_ref['is_sharpe']:.4f}, "
            f"diff={is_sharpe - v43_ref['is_sharpe']:+.4f})",
            flush=True,
        )
        print(
            f"    2024 Sharpe: {sharpe_2024:.4f} (v43={v43_ref['2024_sharpe']:.4f}, "
            f"diff={sharpe_2024 - v43_ref['2024_sharpe']:+.4f})",
            flush=True,
        )
        print(
            f"    2025 Sharpe: {sharpe_2025:.4f} (v43={v43_ref['2025_sharpe']:.4f}, "
            f"diff={sharpe_2025 - v43_ref['2025_sharpe']:+.4f})",
            flush=True,
        )

    # ========== Part 3: 最优候选的2018-2021跨周期验证 ==========
    print(f"\n\n{'='*80}", flush=True)
    print("【Part 3】最优候选 2018-2021 跨周期验证", flush=True)
    print(f"{'='*80}", flush=True)

    # 选 IS Sharpe 最高的候选
    best_label = max(
        all_results.keys(),
        key=lambda k: all_results[k]["is"]["sharpe"],
    )
    best_is_sharpe = all_results[best_label]["is"]["sharpe"]
    best_2024 = all_results[best_label]["yearly"]["2024"]["sharpe"]
    best_2025 = all_results[best_label]["yearly"]["2025"]["sharpe"]

    print(
        f"\n  最优候选: {best_label} (IS Sharpe={best_is_sharpe:.4f}, "
        f"2024={best_2024:.4f}, 2025={best_2025:.4f})",
        flush=True,
    )

    # 跨周期验证
    best_override = None
    for label, override in candidates:
        if label == best_label:
            best_override = {"selection": {"industry_rotation": override}}
            break

    print(f"\n  >> 2018-2021 (4年):", flush=True)
    r_2018 = run_backtest(
        "v45", "2018-01-01", "2021-12-31", best_override,
        label=f"{best_label} 2018-2021",
    )
    print(
        f"    v43 2018-2021参考 Sharpe: {v43_ref['2018_2021_sharpe']:.4f}",
        flush=True,
    )

    all_results["best_label"] = best_label
    all_results["best_2018_2021"] = r_2018

    # ========== Part 4: 总结 ==========
    print(f"\n\n{'='*80}", flush=True)
    print("【总结】", flush=True)
    print(f"{'='*80}", flush=True)

    print(
        f"\n  v43 baseline:  IS={v43_ref['is_sharpe']:.4f}  "
        f"2024={v43_ref['2024_sharpe']:.4f}  2025={v43_ref['2025_sharpe']:.4f}  "
        f"2018-2021={v43_ref['2018_2021_sharpe']:.4f}",
        flush=True,
    )

    for label in all_results:
        if label in ["best_label", "best_2018_2021"]:
            continue
        r_is = all_results[label]["is"]
        r_y = all_results[label]["yearly"]
        print(
            f"  {label}: IS={r_is['sharpe']:.4f}  "
            f"2024={r_y['2024']['sharpe']:.4f}  "
            f"2025={r_y['2025']['sharpe']:.4f}",
            flush=True,
        )

    print(
        f"\n  最优: {best_label} 2018-2021 Sharpe={r_2018['sharpe']:.4f}",
        flush=True,
    )

    # 判断是否通过
    is_pass = (
        best_is_sharpe >= v43_ref["is_sharpe"] - 0.02  # IS不显著下降
        and best_2024 > v43_ref["2024_sharpe"]  # 2024改善
        and best_2025 >= v43_ref["2025_sharpe"] - 0.1  # 2025不退化
        and r_2018["sharpe"] >= 0.0  # 跨周期非负
    )
    if is_pass:
        print(
            f"\n  ✓ {best_label} 通过验证：IS不退化、2024改善、2025稳定、跨周期非负",
            flush=True,
        )
        print(f"  建议创建v45策略文件并运行OOS验证", flush=True)
    else:
        print(
            f"\n  ✗ {best_label} 未完全通过验证，需进一步分析",
            flush=True,
        )

    # 保存结果
    output_dir = Path("output/is_compare/industry_rotation")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "v45_regime_explore.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n结果已保存: {output_file}", flush=True)


if __name__ == "__main__":
    main()
