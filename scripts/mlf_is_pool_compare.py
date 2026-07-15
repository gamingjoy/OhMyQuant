"""mlf 样本内候选池对比 (IS: 2022-2025)

用样本内数据对比沪深300 vs 中证800，避免前视偏差。
IS 期间: 2022-01-01 ~ 2025-12-31 (4年)
训练数据: 2018-01-01 起 (提供 train_window=1008 天历史)
基础配置: v5 (top_n=30, k=25, ind=20%)

注意: 首次运行需构建 IC 缓存 (2018-2025, ~2000天), 较慢。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ohmyquant.core.plugin_system import PluginRegistry
from ohmyquant.strategy.registry import StrategyRegistry
from ohmyquant.strategy.runner import StrategyRunner
from ohmyquant.analysis.metrics import compute_metrics

IS_START = "2022-01-01"
IS_END = "2025-12-31"
DATA_START = "2018-01-01"
OUTPUT_DIR = Path("output/is_compare/mlf")


def run_is_backtest(pool_name: str, pool_index: str) -> dict:
    """运行样本内回测"""
    print(f"\n{'='*70}")
    print(f"样本内回测: {pool_name} ({pool_index})")
    print(f"  IS: {IS_START} ~ {IS_END}, 数据: {DATA_START}~")
    print(f"{'='*70}")

    PluginRegistry.discover_builtin()
    strategy = StrategyRegistry.create("mlf", "v5")

    # 覆盖为 IS 区间
    strategy.config.backtest.start_date = IS_START
    strategy.config.backtest.end_date = IS_END
    strategy.config.backtest.data_start_date = DATA_START
    strategy.config.rebalance.frequency = "monthly"

    # 覆盖候选池
    strategy.config.pools = {"stocks": {"index": pool_index}}

    # 使用 v5 基础配置 (top_n=30, k=25, ind=20%)
    strategy.config.selection.top_n = 30
    strategy.config.selection.mlf["top_k_factors"] = 25
    strategy.config.selection.mlf["max_industry_weight"] = 0.20
    strategy.config.selection.mlf["max_stocks_per_industry"] = 0

    t0 = time.time()
    runner = StrategyRunner(strategy.config)
    result = runner.run()

    bt = result.backtest_result
    metrics = compute_metrics(bt.daily_returns)
    elapsed = time.time() - t0

    # 提取月度收益
    daily_rets = bt.daily_returns
    dates = bt.dates if hasattr(bt, "dates") else []

    print(f"\n  完成 ({elapsed:.1f}s):")
    print(f"  总收益: {metrics.total_return*100:.2f}%")
    print(f"  年化收益: {metrics.annualized_return*100:.2f}%")
    print(f"  Sharpe: {metrics.sharpe_ratio:.4f}")
    print(f"  最大回撤: {metrics.max_drawdown*100:.2f}%")
    print(f"  胜率: {metrics.win_rate*100:.1f}%")

    return {
        "pool": pool_name,
        "pool_index": pool_index,
        "is_start": IS_START,
        "is_end": IS_END,
        "n_days": int(bt.n_days),
        "final_nav": round(float(bt.final_nav), 4),
        "total_return": round(float(metrics.total_return), 4),
        "annualized_return": round(float(metrics.annualized_return), 4),
        "sharpe_ratio": round(float(metrics.sharpe_ratio), 4),
        "max_drawdown": round(float(metrics.max_drawdown), 4),
        "win_rate": round(float(metrics.win_rate), 4),
        "elapsed_seconds": round(elapsed, 1),
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    pools = [
        ("沪深300", "000300.XSHG"),
        ("中证800", "000819.XSHG"),
    ]

    results = []
    for pool_name, pool_index in pools:
        try:
            r = run_is_backtest(pool_name, pool_index)
            results.append(r)
        except Exception as e:
            print(f"\n  {pool_name} 失败: {e}")
            import traceback
            traceback.print_exc()
            results.append({"pool": pool_name, "error": str(e)})

    # 保存结果
    with open(OUTPUT_DIR / "is_pool_compare.json", "w", encoding="utf-8") as f:
        json.dump({
            "is_start": IS_START,
            "is_end": IS_END,
            "data_start": DATA_START,
            "results": results,
        }, f, indent=2, ensure_ascii=False)

    # 对比
    print(f"\n\n{'='*70}")
    print("样本内候选池对比 (IS: 2022-2025)")
    print(f"{'='*70}")
    print(f"\n{'指标':<14} {'沪深300':>14} {'中证800':>14}")
    print(f"{'-'*44}")
    valid = [r for r in results if "sharpe_ratio" in r]
    if len(valid) == 2:
        r1, r2 = valid[0], valid[1]
        print(f"{'总收益':<14} {r1['total_return']*100:>13.2f}% {r2['total_return']*100:>13.2f}%")
        print(f"{'年化收益':<14} {r1['annualized_return']*100:>13.2f}% {r2['annualized_return']*100:>13.2f}%")
        print(f"{'Sharpe':<14} {r1['sharpe_ratio']:>14.4f} {r2['sharpe_ratio']:>14.4f}")
        print(f"{'最大回撤':<14} {r1['max_drawdown']*100:>13.2f}% {r2['max_drawdown']*100:>13.2f}%")
        print(f"{'胜率':<14} {r1['win_rate']*100:>13.1f}% {r2['win_rate']*100:>13.1f}%")

        better = "沪深300" if r1["sharpe_ratio"] >= r2["sharpe_ratio"] else "中证800"
        print(f"\n  IS 表现更优: {better} (Sharpe)")

    print(f"\n结果已保存: {OUTPUT_DIR / 'is_pool_compare.json'}")


if __name__ == "__main__":
    main()
