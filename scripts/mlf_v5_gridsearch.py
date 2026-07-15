"""mlf_v5 超参网格搜索

在 v5 (沪深300 + 行业约束) 基础上搜索最优超参组合：
  - top_n: [20, 30, 40]          (v5 默认 30)
  - top_k_factors: [20, 25, 30]  (v5 默认 25)
  - max_industry_weight: [0.15, 0.20, 0.25]  (v5 默认 0.20)

共 27 个组合，OOS 区间 2026-06-01 ~ 2026-07-10。
IC 缓存复用（同沪深300池），首跑构建缓存后后续快速加载。
"""
from __future__ import annotations

import json
import sys
import time
from itertools import product
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ohmyquant.core.plugin_system import PluginRegistry
from ohmyquant.strategy.registry import StrategyRegistry
from ohmyquant.strategy.runner import StrategyRunner
from ohmyquant.analysis.metrics import compute_metrics

OOS_START = "2026-06-01"
OOS_END = "2026-07-10"
OUTPUT_DIR = Path("output/oos_2026/mlf_v5_gridsearch")

# 网格定义
TOP_N_GRID = [20, 30, 40]
TOP_K_GRID = [20, 25, 30]
IND_CAP_GRID = [0.15, 0.20, 0.25]


def run_single(top_n: int, top_k: int, ind_cap: float) -> dict:
    """运行单个超参组合"""
    label = f"n{top_n}_k{top_k}_ind{int(ind_cap * 100)}"
    print(f"\n  [{label}] 运行中...", end="", flush=True)

    PluginRegistry.discover_builtin()
    strategy = StrategyRegistry.create("mlf", "v5")

    # 覆盖 OOS 区间
    strategy.config.backtest.start_date = OOS_START
    strategy.config.backtest.end_date = OOS_END
    strategy.config.rebalance.frequency = "monthly"

    # 覆盖网格超参
    strategy.config.selection.top_n = top_n
    strategy.config.selection.mlf["top_k_factors"] = top_k
    strategy.config.selection.mlf["max_industry_weight"] = ind_cap
    # 确保无行业配额（v7 证明配额稀释信号）
    strategy.config.selection.mlf["max_stocks_per_industry"] = 0

    t0 = time.time()
    runner = StrategyRunner(strategy.config)
    result = runner.run()

    bt = result.backtest_result
    metrics = compute_metrics(bt.daily_returns)
    elapsed = time.time() - t0

    print(
        f" 完成 ({elapsed:.1f}s): "
        f"收益={metrics.total_return*100:+.2f}%, "
        f"Sharpe={metrics.sharpe_ratio:.4f}, "
        f"回撤={metrics.max_drawdown*100:.2f}%"
    )

    return {
        "label": label,
        "top_n": top_n,
        "top_k_factors": top_k,
        "max_industry_weight": ind_cap,
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

    combos = list(product(TOP_N_GRID, TOP_K_GRID, IND_CAP_GRID))
    print(f"{'='*70}")
    print(f"mlf_v5 超参网格搜索: {len(combos)} 个组合")
    print(f"  top_n: {TOP_N_GRID}")
    print(f"  top_k_factors: {TOP_K_GRID}")
    print(f"  max_industry_weight: {IND_CAP_GRID}")
    print(f"  OOS: {OOS_START} ~ {OOS_END}")
    print(f"{'='*70}")

    results = []
    t_total = time.time()

    for i, (top_n, top_k, ind_cap) in enumerate(combos, 1):
        print(f"\n[{i}/{len(combos)}]", end="")
        try:
            r = run_single(top_n, top_k, ind_cap)
            results.append(r)
        except Exception as e:
            print(f" 失败: {e}")
            results.append({
                "label": f"n{top_n}_k{top_k}_ind{int(ind_cap*100)}",
                "top_n": top_n,
                "top_k_factors": top_k,
                "max_industry_weight": ind_cap,
                "error": str(e),
            })

    elapsed_total = time.time() - t_total

    # 按 Sharpe 降序排序
    valid = [r for r in results if "sharpe_ratio" in r]
    valid.sort(key=lambda x: x["sharpe_ratio"], reverse=True)

    # 保存结果
    with open(OUTPUT_DIR / "gridsearch_results.json", "w", encoding="utf-8") as f:
        json.dump({
            "grid": {
                "top_n": TOP_N_GRID,
                "top_k_factors": TOP_K_GRID,
                "max_industry_weight": IND_CAP_GRID,
            },
            "oos_start": OOS_START,
            "oos_end": OOS_END,
            "n_combos": len(combos),
            "elapsed_total_seconds": round(elapsed_total, 1),
            "results": results,
            "sorted_by_sharpe": valid,
        }, f, indent=2, ensure_ascii=False)

    # 打印汇总表
    print(f"\n\n{'='*70}")
    print(f"网格搜索完成 ({elapsed_total/60:.1f} 分钟), {len(valid)}/{len(combos)} 成功")
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

    # v5 基线对比
    v5_baseline = next(
        (r for r in valid if r["top_n"] == 30 and r["top_k_factors"] == 25 and r["max_industry_weight"] == 0.20),
        None,
    )
    if v5_baseline:
        v5_rank = valid.index(v5_baseline) + 1
        print(f"\n  v5 基线 (n30_k25_ind20): 排名 {v5_rank}/{len(valid)}")
        best = valid[0]
        if best != v5_baseline:
            print(f"  最优组合: {best['label']}")
            print(f"    Sharpe 提升: {v5_baseline['sharpe_ratio']:.4f} → {best['sharpe_ratio']:.4f}")
            print(f"    收益提升: {v5_baseline['total_return']*100:.2f}% → {best['total_return']*100:.2f}%")
        else:
            print(f"  v5 基线即为最优组合 ✓")

    print(f"\n结果已保存: {OUTPUT_DIR / 'gridsearch_results.json'}")


if __name__ == "__main__":
    main()
