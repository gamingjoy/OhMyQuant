"""v9 策略稳健性快速分析（仅OOS+少量IS关键对比）

分析内容：
1. IS分段（每年，验证参数稳定性，识别哪年表现好/差）
2. 周几调仓OOS对比（5个，每个~1分钟）
3. 调仓频率OOS对比（4个，每个~1分钟）
4. RRG窗口OOS敏感性（3个关键窗口，每个~1分钟）

用法:
    python scripts/industry_rotation_v9_robustness.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from ohmyquant.strategy import StrategyRegistry, StrategyRunner


def _metrics(bt) -> dict:
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
    max_dd = float(np.min(drawdown))
    return {
        "n_days": n_days,
        "final_nav": final_nav,
        "total_return": total_return,
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "n_rebalance": len(bt.pool_weight_log),
    }


def run_variant(overrides: dict, label: str, start: str, end: str) -> dict:
    """跑参数变体"""
    cfg = {
        "backtest": {
            "start_date": start,
            "end_date": end,
            "data_start_date": "2018-01-01",
        }
    }
    cfg.update(overrides)
    strategy = StrategyRegistry.create("industry_rotation", "v9", cfg)
    runner = StrategyRunner(strategy.config)
    result = runner.run()
    m = _metrics(result.backtest_result)
    print(f"  [{label}] 收益={m['total_return']:+.2%} Sharpe={m['sharpe']:.4f} "
          f"最大回撤={m['max_drawdown']:.2%} 调仓={m['n_rebalance']}")
    return m


def main():
    print("=" * 70)
    print("v9 策略稳健性快速分析")
    print("=" * 70)

    IS_START, IS_END = "2022-01-01", "2025-12-31"
    OOS_START, OOS_END = "2026-06-01", "2026-07-16"

    results = {}

    # ============================================
    # 1. IS 分段表现（按年，验证参数稳定性）
    # ============================================
    print("\n### 1. IS 分段表现（v9 参数固定，按年分段）###")
    seg_results = {}
    for s, e, lbl in [
        ("2022-01-01", "2022-12-31", "2022年"),
        ("2023-01-01", "2023-12-31", "2023年"),
        ("2024-01-01", "2024-12-31", "2024年"),
        ("2025-01-01", "2025-12-31", "2025年"),
    ]:
        print(f"\n--- {lbl} ---")
        seg_results[lbl] = run_variant({}, lbl, s, e)
    results["is_segments"] = seg_results

    # ============================================
    # 2. 周几调仓 OOS 对比
    # ============================================
    print("\n### 2. 周几调仓对比（OOS）###")
    weekday_names = ["周一", "周二", "周三", "周四", "周五"]
    weekday_oos = {}
    for wd in range(5):
        print(f"\n--- {weekday_names[wd]}调仓 ---")
        m = run_variant(
            {"rebalance": {"frequency": "weekly", "weekday": wd,
                           "method": "cost_benefit", "cost_model": {"name": "stock_cn"}}},
            f"OOS weekday={wd}", OOS_START, OOS_END
        )
        weekday_oos[weekday_names[wd]] = m
    results["weekday_oos"] = weekday_oos

    # ============================================
    # 3. 调仓频率 OOS 对比
    # ============================================
    print("\n### 3. 调仓频率对比（OOS）###")
    freq_oos = {}
    for freq in ["daily", "weekly", "biweekly", "monthly"]:
        print(f"\n--- {freq}调仓 ---")
        m = run_variant(
            {"rebalance": {"frequency": freq, "weekday": 0,
                           "method": "cost_benefit", "cost_model": {"name": "stock_cn"}}},
            f"OOS {freq}", OOS_START, OOS_END
        )
        freq_oos[freq] = m
    results["frequency_oos"] = freq_oos

    # ============================================
    # 4. RRG 窗口 OOS 敏感性（10/20/30/40/60）
    # ============================================
    print("\n### 4. RRG RS-Momentum 窗口 OOS 敏感性 ###")
    rrg_oos = {}
    for w in [10, 20, 30, 40, 60]:
        print(f"\n--- rs_momentum_window={w} ---")
        m = run_variant(
            {"selection": {"industry_rotation": {"rs_momentum_window": w}}},
            f"OOS rrg_w={w}", OOS_START, OOS_END
        )
        rrg_oos[f"window_{w}"] = m
    results["rrg_window_oos"] = rrg_oos

    # ============================================
    # 汇总
    # ============================================
    print("\n" + "=" * 70)
    print("汇总")
    print("=" * 70)

    print("\n## IS 分段表现（v9 参数固定）:")
    print(f"{'区间':<10} {'收益':>10} {'Sharpe':>8} {'最大回撤':>10} {'调仓':>6}")
    for lbl, m in seg_results.items():
        print(f"{lbl:<10} {m['total_return']*100:>+9.2f}% {m['sharpe']:>8.4f} "
              f"{m['max_drawdown']*100:>+9.2f}% {m['n_rebalance']:>6d}")

    print("\n## 周几调仓对比 (OOS):")
    print(f"{'周几':<8} {'收益':>10} {'Sharpe':>8} {'最大回撤':>10} {'调仓':>6}")
    for wd, m in weekday_oos.items():
        print(f"{wd:<8} {m['total_return']*100:>+9.2f}% {m['sharpe']:>8.4f} "
              f"{m['max_drawdown']*100:>+9.2f}% {m['n_rebalance']:>6d}")

    print("\n## 调仓频率对比 (OOS):")
    print(f"{'频率':<10} {'收益':>10} {'Sharpe':>8} {'最大回撤':>10} {'调仓':>6}")
    for freq, m in freq_oos.items():
        print(f"{freq:<10} {m['total_return']*100:>+9.2f}% {m['sharpe']:>8.4f} "
              f"{m['max_drawdown']*100:>+9.2f}% {m['n_rebalance']:>6d}")

    print("\n## RRG 窗口敏感性 (OOS):")
    print(f"{'窗口':<10} {'收益':>10} {'Sharpe':>8} {'最大回撤':>10} {'调仓':>6}")
    for w, m in rrg_oos.items():
        print(f"{w:<12} {m['total_return']*100:>+9.2f}% {m['sharpe']:>8.4f} "
              f"{m['max_drawdown']*100:>+9.2f}% {m['n_rebalance']:>6d}")

    # 保存
    out_path = Path("output/robustness/v9_analysis.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n结果已保存: {out_path}")


if __name__ == "__main__":
    main()
