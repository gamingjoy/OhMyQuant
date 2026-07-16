"""行业轮动策略 IS 回测验证（通用版）

支持运行指定版本，并可对比多个版本。

用法:
    python scripts/ind_is.py v1           # 运行 v1
    python scripts/ind_is.py v2           # 运行 v2
    python scripts/ind_is.py v1 v2        # 对比 v1 vs v2
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ohmyquant.strategy import StrategyRegistry, StrategyRunner


def run_version(version: str) -> dict:
    """运行指定版本的 IS 回测"""
    print("=" * 60)
    print(f"行业轮动策略 {version} - IS 回测")
    print("=" * 60)

    strategy = StrategyRegistry.create("ind", version)
    print(f"策略: {strategy.config.strategy_name}")
    print(f"描述: {strategy.config.description}")
    print(f"调仓频率: {strategy.config.rebalance.frequency}")
    print(f"风控方法: {strategy.config.risk.method}")
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
    print(f"IS 回测结果 ({version}):")
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
    if stock_weights:
        last_date = sorted(stock_weights.keys())[-1]
        last_holdings = stock_weights[last_date]
        print(f"  最后持仓日:     {last_date}")
        print(f"  持仓股票数:     {len(last_holdings)}")
        if last_holdings:
            weights = list(last_holdings.values())
            print(f"  总权重:         {sum(weights):.4f}")
            print(f"  权重范围:       [{min(weights):.4f}, {max(weights):.4f}]")

            # 行业分布
            try:
                from ohmyquant.data.sources.duckdb_source import DuckDBSource

                source = DuckDBSource(
                    {"data_root": "D:/Work/Project/download_a_share/data"}
                )
                industry_map = source.load_industry_map()
                industry_weights: dict[str, float] = {}
                for code, w in last_holdings.items():
                    ind = industry_map.get(code, "未知")
                    industry_weights[ind] = industry_weights.get(ind, 0.0) + w
                print(f"  行业数:         {len(industry_weights)}")
                for ind, w in sorted(
                    industry_weights.items(), key=lambda x: x[1], reverse=True
                ):
                    print(f"    {ind}: {w:.4f} ({w*100:.2f}%)")
            except Exception as e:
                print(f"  行业分布分析失败: {e}")
    print()

    result_data = {
        "strategy": f"ind_{version}",
        "version": version,
        "is_start": "2022-01-01",
        "is_end": "2025-12-31",
        "n_days": n_days,
        "final_nav": final_nav,
        "total_return": total_return,
        "annualized_return": annualized_return,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "n_rebalance": n_rebalance,
    }

    output_dir = Path("output/is_compare/ind")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{version}_is.json"
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
    print("版本对比:")
    print("=" * 60)
    print(f"{'版本':<8} {'总收益':>10} {'年化':>10} {'Sharpe':>8} {'最大回撤':>10} {'胜率':>8} {'调仓次数':>8}")
    print("-" * 60)
    for r in results:
        print(
            f"{r['version']:<8} "
            f"{r['total_return']*100:>+9.2f}% "
            f"{r['annualized_return']*100:>+9.2f}% "
            f"{r['sharpe_ratio']:>8.4f} "
            f"{r['max_drawdown']*100:>+9.2f}% "
            f"{r['win_rate']*100:>7.2f}% "
            f"{r['n_rebalance']:>8d}"
        )


if __name__ == "__main__":
    versions = sys.argv[1:] if len(sys.argv) > 1 else ["v1"]
    results = []
    for v in versions:
        r = run_version(v)
        results.append(r)
    compare_versions(results)
