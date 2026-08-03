"""行业轮动策略 OOS 回测验证

OOS: 2026-06-01 ~ 2026-07-15
IS: 2022-01-01 ~ 2025-12-31 (训练期，不用于超参选择)

用法:
    python scripts/industry_rotation_oos.py v5           # 运行 v5 OOS
    python scripts/industry_rotation_oos.py v4 v5        # 对比 v4 vs v5 OOS
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ohmyquant.strategy import StrategyRegistry, StrategyRunner
import os

OOS_START = "2026-06-01"
OOS_END = "2026-07-16"


def run_version_oos(version: str) -> dict:
    """运行指定版本的 OOS 回测"""
    print("=" * 60)
    print(f"行业轮动策略 {version} - OOS 回测 ({OOS_START} ~ {OOS_END})")
    print("=" * 60)

    # 用深度合并覆盖日期
    config_override = {
        "backtest": {
            "start_date": OOS_START,
            "end_date": OOS_END,
        }
    }
    strategy = StrategyRegistry.create("industry_rotation", version, config_override)
    print(f"策略: {strategy.config.strategy_name}")
    print(f"OOS: {OOS_START} → {OOS_END}")
    print()

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

    print("-" * 60)
    print(f"OOS 回测结果 ({version}):")
    print(f"  回测天数:       {n_days}")
    print(f"  最终净值:       {final_nav:.4f}")
    print(f"  总收益:         {total_return:+.4f} ({total_return*100:+.2f}%)")
    print(f"  年化收益:       {annualized_return:+.4f} ({annualized_return*100:+.2f}%)")
    print(f"  Sharpe:         {sharpe:.4f}")
    print(f"  最大回撤:       {max_drawdown:.4f} ({max_drawdown*100:.2f}%)")
    print(f"  胜率:           {win_rate:.4f} ({win_rate*100:.2f}%)")
    print(f"  调仓次数:       {n_rebalance}")

    # 持仓分析
    stock_weights = bt.stock_weights_by_date
    rebalance_log = []
    if stock_weights:
        for entry in bt.pool_weight_log:
            date_str = str(entry.get("date", ""))
            holdings = stock_weights.get(date_str, {})
            rebalance_log.append({
                "date": date_str,
                "holdings": {k: round(v, 4) for k, v in holdings.items()},
            })

        # 显示每次调仓持仓
        for entry in rebalance_log:
            date_str = entry["date"]
            holdings = entry["holdings"]
            sorted_h = sorted(holdings.items(), key=lambda x: x[1], reverse=True)
            print(f"\n  调仓日 {date_str}: {len(holdings)} 只, 总权重 {sum(holdings.values()):.2%}")
            print(f"  前10: {', '.join(f'{c}:{w:.2%}' for c, w in sorted_h[:10])}")

            # 行业分布
            try:
                from ohmyquant.data.sources.duckdb_source import DuckDBSource

                source = DuckDBSource(
                    {"data_root": os.getenv("DATA_ROOT", "data")}
                )
                industry_map = source.load_industry_map()
                sw_counter = Counter()
                for code, w in holdings.items():
                    ind = industry_map.get(code, "未知")
                    sw_counter[ind] += w
                print(f"  行业分布:")
                for ind, w in sw_counter.most_common():
                    print(f"    {ind}: {w:.4f} ({w*100:.2f}%)")
            except Exception as e:
                print(f"  行业分析失败: {e}")

        # 换手分析
        if len(rebalance_log) >= 2:
            h1 = set(rebalance_log[0]["holdings"].keys())
            h2 = set(rebalance_log[1]["holdings"].keys())
            added = h2 - h1
            removed = h1 - h2
            print(f"\n  换手 ({rebalance_log[0]['date']} → {rebalance_log[1]['date']}):")
            print(f"    新增: {len(added)} 只, 剔除: {len(removed)} 只")
            if added:
                print(f"    新增: {sorted(added)}")
            if removed:
                print(f"    剔除: {sorted(removed)}")
    print()

    result_data = {
        "strategy": f"industry_rotation_{version}",
        "version": version,
        "oos_start": OOS_START,
        "oos_end": OOS_END,
        "n_days": n_days,
        "final_nav": final_nav,
        "total_return": total_return,
        "annualized_return": annualized_return,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "n_rebalance": n_rebalance,
        "rebalance_log": rebalance_log,
    }

    output_dir = Path("output/oos_compare/industry_rotation")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{version}_oos.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=2, ensure_ascii=False)
    print(f"结果已保存: {output_file}")
    print()

    return result_data


def compare_versions(results: list[dict]):
    """对比多个版本"""
    if len(results) < 2:
        return
    print("=" * 60)
    print("OOS 版本对比:")
    print("=" * 60)
    print(
        f"{'版本':<8} {'总收益':>10} {'年化':>10} {'Sharpe':>8} "
        f"{'最大回撤':>10} {'胜率':>8} {'调仓':>6}"
    )
    print("-" * 60)
    for r in results:
        print(
            f"{r['version']:<8} "
            f"{r['total_return']*100:>+9.2f}% "
            f"{r['annualized_return']*100:>+9.2f}% "
            f"{r['sharpe_ratio']:>8.4f} "
            f"{r['max_drawdown']*100:>+9.2f}% "
            f"{r['win_rate']*100:>7.2f}% "
            f"{r['n_rebalance']:>6d}"
        )


if __name__ == "__main__":
    versions = sys.argv[1:] if len(sys.argv) > 1 else ["v5"]
    results = []
    for v in versions:
        r = run_version_oos(v)
        results.append(r)
    compare_versions(results)
