"""mlf_v5 OOS 回测 + 行业分析

运行 mlf_v5 (沪深300 + 20%行业上限) OOS 回测，对比 v2。
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ohmyquant.core.plugin_system import PluginRegistry
from ohmyquant.strategy.registry import StrategyRegistry
from ohmyquant.strategy.runner import StrategyRunner
from ohmyquant.analysis.metrics import compute_metrics

OOS_START = "2026-06-01"
OOS_END = "2026-07-10"
DATA_ROOT = "D:/Work/Project/download_a_share/data"
INDUSTRY_FILE = f"{DATA_ROOT}/parquet/stock_industry/year=2026/data.parquet"
V2_RESULTS = Path("output/oos_2026/mlf_v2/results.json")
V4_RESULTS = Path("output/oos_2026/mlf_v4/results.json")
V5_OUTPUT_DIR = Path("output/oos_2026/mlf_v5")


def run_v5_oos() -> dict:
    print(f"\n{'='*70}")
    print(f"运行 mlf_v5 OOS 回测 ({OOS_START} ~ {OOS_END})")
    print(f"  候选池: 沪深300, 行业上限: 20%, k25_w1008")
    print(f"{'='*70}")

    t0 = time.time()
    PluginRegistry.discover_builtin()
    strategy = StrategyRegistry.create("mlf", "v5")
    strategy.config.backtest.start_date = OOS_START
    strategy.config.backtest.end_date = OOS_END
    strategy.config.rebalance.frequency = "monthly"

    runner = StrategyRunner(strategy.config)
    result = runner.run()

    bt = result.backtest_result
    returns = bt.daily_returns
    metrics = compute_metrics(returns)
    elapsed = time.time() - t0

    print(f"\n  完成 ({elapsed:.1f}s): 净值={bt.final_nav:.4f}")
    print(f"  总收益: {metrics.total_return*100:.2f}%")
    print(f"  Sharpe: {metrics.sharpe_ratio:.4f}")
    print(f"  最大回撤: {metrics.max_drawdown*100:.2f}%")

    rebalance_log = []
    stock_weights_by_date = getattr(bt, "stock_weights_by_date", {}) or {}
    for entry in getattr(bt, "pool_weight_log", []):
        date_str = str(entry.get("date", ""))
        holdings = stock_weights_by_date.get(date_str, {})
        rebalance_log.append({
            "date": date_str,
            "holdings": {k: round(v, 4) for k, v in holdings.items()},
        })

    nav_series = [round(float(x), 4) for x in bt.nav] if hasattr(bt, "nav") else []

    return {
        "strategy": "mlf_v5",
        "version": "v5",
        "oos_start": OOS_START,
        "oos_end": OOS_END,
        "n_days": int(bt.n_days),
        "final_nav": round(float(bt.final_nav), 4),
        "total_return": round(float(metrics.total_return), 4),
        "annualized_return": round(float(metrics.annualized_return), 4),
        "sharpe_ratio": round(float(metrics.sharpe_ratio), 4),
        "max_drawdown": round(float(metrics.max_drawdown), 4),
        "win_rate": round(float(metrics.win_rate), 4),
        "rebalance_log": rebalance_log,
        "elapsed_seconds": round(elapsed, 1),
    }


def load_industry_map():
    df = pl.read_parquet(INDUSTRY_FILE)
    from ohmyquant.data.base import DataSource
    df = df.with_columns(
        pl.col("code").map_elements(DataSource.denormalize_code, return_dtype=pl.Utf8).alias("code")
    )
    return {row["code"]: row.get("sw_l1_name") or "未分类" for row in df.iter_rows(named=True)}


def analyze_industry(holdings, industry_map, label):
    sw_counter = Counter()
    sw_count = Counter()
    for code, weight in holdings.items():
        ind = industry_map.get(code, "未分类")
        sw_counter[ind] += weight
        sw_count[ind] += 1

    total = sum(holdings.values())
    print(f"\n  [{label}] 行业分布:")
    print(f"  {'行业':<20} {'股票数':>6} {'权重':>8}")
    print(f"  {'-'*36}")
    for ind, w in sw_counter.most_common():
        print(f"  {ind:<20} {sw_count[ind]:>6} {w/total*100:>7.1f}%")

    financial = sw_counter.get("银行I", 0) + sw_counter.get("非银金融I", 0)
    print(f"  >>> 金融合计: {financial/total*100:.1f}%")


def main():
    V5_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 运行 v5
    v5_result = run_v5_oos()
    with open(V5_OUTPUT_DIR / "results.json", "w", encoding="utf-8") as f:
        json.dump(v5_result, f, indent=2, ensure_ascii=False)

    # 2. 加载 v2, v4
    with open(V2_RESULTS, "r", encoding="utf-8") as f:
        v2 = json.load(f)
    v4 = None
    if V4_RESULTS.exists():
        with open(V4_RESULTS, "r", encoding="utf-8") as f:
            v4 = json.load(f)

    # 3. 对比
    print(f"\n\n{'='*70}")
    print("v2 vs v4 vs v5 对比")
    print(f"{'='*70}")
    print(f"\n{'指标':<14} {'v2(无约束)':>14} {'v4(中证800)':>14} {'v5(行业20%)':>14}")
    print(f"{'-'*58}")
    print(f"{'候选池':<14} {'沪深300':>14} {'中证800':>14} {'沪深300':>14}")
    print(f"{'行业约束':<14} {'无':>14} {'无':>14} {'20%':>14}")
    print(f"{'总收益':<14} {v2['total_return']*100:>13.2f}% {v4['total_return']*100 if v4 else 0:>13.2f}% {v5_result['total_return']*100:>13.2f}%")
    print(f"{'Sharpe':<14} {v2['sharpe_ratio']:>14.4f} {v4['sharpe_ratio'] if v4 else 0:>14.4f} {v5_result['sharpe_ratio']:>14.4f}")
    print(f"{'最大回撤':<14} {v2['max_drawdown']*100:>13.2f}% {v4['max_drawdown']*100 if v4 else 0:>13.2f}% {v5_result['max_drawdown']*100:>13.2f}%")

    # 4. 行业分析
    print(f"\n\n{'='*70}")
    print("行业分布对比")
    print(f"{'='*70}")

    industry_map = load_industry_map()
    for label, data in [("v2", v2), ("v4", v4), ("v5", v5_result)]:
        if data is None:
            continue
        for entry in data.get("rebalance_log", []):
            holdings = entry.get("holdings", {})
            if holdings:
                analyze_industry(holdings, industry_map, f"{label}_{entry['date']}")

    # 5. v5 持仓明细 + 换手
    print(f"\n\n{'='*70}")
    print("v5 持仓明细")
    print(f"{'='*70}")
    for entry in v5_result.get("rebalance_log", []):
        date = entry["date"]
        holdings = entry.get("holdings", {})
        sorted_h = sorted(holdings.items(), key=lambda x: x[1], reverse=True)
        print(f"\n  {date}: {len(holdings)} 只, 总权重 {sum(holdings.values()):.2%}")
        print(f"  前10: {', '.join(f'{c}:{w:.2%}' for c, w in sorted_h[:10])}")

    v5_rebal = v5_result.get("rebalance_log", [])
    if len(v5_rebal) >= 2:
        h1 = set(v5_rebal[0].get("holdings", {}).keys())
        h2 = set(v5_rebal[1].get("holdings", {}).keys())
        added = h2 - h1
        removed = h1 - h2
        print(f"\n  v5 换手 (6/1 → 7/1):")
        print(f"    新增: {len(added)} 只, 剔除: {len(removed)} 只")
        if added:
            print(f"    新增: {sorted(added)}")
        if removed:
            print(f"    剔除: {sorted(removed)}")


if __name__ == "__main__":
    main()
