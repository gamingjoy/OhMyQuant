"""mlf 样本内超参搜索 (IS: 2022-2025)

基于 IS 候选池对比确认沪深300后，搜索关键超参组合。
IC 缓存已构建 (沪深300, 2018-2025)，后续回测只需加载缓存。

搜索组合 (精简版, 避免过拟合):
  1. n30_k25_ind20  (v5基线, 已有 IS 结果 Sharpe=0.18)
  2. n20_k30_ind25  (v8 OOS最优配置)
  3. n30_k25_ind0   (无行业约束, 检验行业约束是否有用)
  4. n30_k30_ind25  (更多因子+更松约束)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ohmyquant.core.plugin_system import PluginRegistry
from ohmyquant.strategy.registry import StrategyRegistry
from ohmyquant.strategy.runner import StrategyRunner
from ohmyquant.analysis.metrics import compute_metrics

IS_START = "2022-01-01"
IS_END = "2025-12-31"
DATA_START = "2018-01-01"
OUTPUT_DIR = Path("output/is_compare/mlf")

# 超参组合
COMBOS = [
    {"label": "n30_k25_ind20", "top_n": 30, "top_k": 25, "ind_cap": 0.20},
    {"label": "n20_k30_ind25", "top_n": 20, "top_k": 30, "ind_cap": 0.25},
    {"label": "n30_k25_ind0",  "top_n": 30, "top_k": 25, "ind_cap": 0.0},
    {"label": "n30_k30_ind25", "top_n": 30, "top_k": 30, "ind_cap": 0.25},
]


def run_is_backtest(combo: dict) -> dict:
    label = combo["label"]
    print(f"\n{'='*70}")
    print(f"IS 回测: {label}")
    print(f"  top_n={combo['top_n']}, k={combo['top_k']}, ind={combo['ind_cap']}")
    print(f"{'='*70}")

    PluginRegistry.discover_builtin()
    strategy = StrategyRegistry.create("mlf", "v5")

    strategy.config.backtest.start_date = IS_START
    strategy.config.backtest.end_date = IS_END
    strategy.config.backtest.data_start_date = DATA_START
    strategy.config.rebalance.frequency = "monthly"

    strategy.config.pools = {"stocks": {"index": "000300.XSHG"}}
    strategy.config.selection.top_n = combo["top_n"]
    strategy.config.selection.mlf["top_k_factors"] = combo["top_k"]
    strategy.config.selection.mlf["max_industry_weight"] = combo["ind_cap"]
    strategy.config.selection.mlf["max_stocks_per_industry"] = 0

    t0 = time.time()
    runner = StrategyRunner(strategy.config)
    result = runner.run()

    bt = result.backtest_result
    metrics = compute_metrics(bt.daily_returns)
    elapsed = time.time() - t0

    print(f"\n  完成 ({elapsed:.1f}s):")
    print(f"  总收益: {metrics.total_return*100:.2f}%, Sharpe: {metrics.sharpe_ratio:.4f}")
    print(f"  最大回撤: {metrics.max_drawdown*100:.2f}%, 胜率: {metrics.win_rate*100:.1f}%")

    return {
        "label": label,
        "top_n": combo["top_n"],
        "top_k_factors": combo["top_k"],
        "max_industry_weight": combo["ind_cap"],
        "total_return": round(float(metrics.total_return), 4),
        "annualized_return": round(float(metrics.annualized_return), 4),
        "sharpe_ratio": round(float(metrics.sharpe_ratio), 4),
        "max_drawdown": round(float(metrics.max_drawdown), 4),
        "win_rate": round(float(metrics.win_rate), 4),
        "final_nav": round(float(bt.final_nav), 4),
        "elapsed_seconds": round(elapsed, 1),
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"{'='*70}")
    print(f"mlf 样本内超参搜索: {len(COMBOS)} 个组合")
    print(f"  IS: {IS_START} ~ {IS_END}, 池: 沪深300")
    print(f"{'='*70}")

    results = []
    t_total = time.time()

    for i, combo in enumerate(COMBOS, 1):
        print(f"\n[{i}/{len(COMBOS)}]", end="")
        try:
            r = run_is_backtest(combo)
            results.append(r)
        except Exception as e:
            print(f"  失败: {e}")
            import traceback
            traceback.print_exc()

    elapsed_total = time.time() - t_total

    # 按 Sharpe 降序
    valid = [r for r in results if "sharpe_ratio" in r]
    valid.sort(key=lambda x: x["sharpe_ratio"], reverse=True)

    with open(OUTPUT_DIR / "is_gridsearch.json", "w", encoding="utf-8") as f:
        json.dump({
            "is_start": IS_START,
            "is_end": IS_END,
            "pool": "沪深300",
            "n_combos": len(COMBOS),
            "elapsed_total_seconds": round(elapsed_total, 1),
            "results": results,
            "sorted_by_sharpe": valid,
        }, f, indent=2, ensure_ascii=False)

    # 汇总
    print(f"\n\n{'='*70}")
    print(f"IS 超参搜索完成 ({elapsed_total/60:.1f} 分钟)")
    print(f"{'='*70}")
    print(f"\n{'排名':>4} {'标签':<20} {'收益':>8} {'Sharpe':>8} {'回撤':>8}")
    print(f"{'-'*52}")
    for rank, r in enumerate(valid, 1):
        marker = " ★" if rank == 1 else ""
        print(
            f"{rank:>4} {r['label']:<20} "
            f"{r['total_return']*100:>+7.2f}% "
            f"{r['sharpe_ratio']:>8.4f} "
            f"{r['max_drawdown']*100:>+7.2f}%{marker}"
        )

    print(f"\n结果已保存: {OUTPUT_DIR / 'is_gridsearch.json'}")


if __name__ == "__main__":
    main()
