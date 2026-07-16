"""mlf_v4 OOS 回测 + 行业分析

运行 mlf_v4 (中证800候选池) OOS 回测，对比 v2 (沪深300)。
首次运行需为中证800重建 IC 缓存（约15-20分钟）。
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
V3_RESULTS = Path("output/oos_2026/mlf_v3/results.json")
V4_OUTPUT_DIR = Path("output/oos_2026/mlf_v4")


def run_v4_oos() -> dict:
    """运行 mlf_v4 OOS 回测"""
    print(f"\n{'='*70}")
    print(f"运行 mlf_v4 OOS 回测 ({OOS_START} ~ {OOS_END})")
    print(f"  候选池: 中证800 (000819.XSHG)")
    print(f"  配置: top_n=30, max_weight=4%, k25_w1008")
    print(f"{'='*70}")

    t0 = time.time()
    PluginRegistry.discover_builtin()

    strategy = StrategyRegistry.create("mlf", "v4")
    strategy.config.backtest.start_date = OOS_START
    strategy.config.backtest.end_date = OOS_END
    strategy.config.rebalance.frequency = "monthly"

    print(f"  池: {list(strategy.config.pools.keys())}")
    pool_cfg = strategy.config.pools.get("stocks", {})
    if isinstance(pool_cfg, dict):
        print(f"  指数: {pool_cfg.get('index', 'N/A')}")
    else:
        print(f"  指数: {getattr(pool_cfg, 'index', 'N/A')}")

    runner = StrategyRunner(strategy.config)
    result = runner.run()

    bt = result.backtest_result
    returns = bt.daily_returns
    metrics = compute_metrics(returns)

    elapsed = time.time() - t0
    print(f"\n  完成 ({elapsed:.1f}s): 净值={bt.final_nav:.4f}, 天数={bt.n_days}")
    print(f"  总收益: {metrics.total_return*100:.2f}%")
    print(f"  Sharpe: {metrics.sharpe_ratio:.4f}")
    print(f"  最大回撤: {metrics.max_drawdown*100:.2f}%")

    rebalance_log = []
    stock_weights_by_date = getattr(bt, "stock_weights_by_date", {}) or {}
    for entry in getattr(bt, "pool_weight_log", []):
        date_str = str(entry.get("date", ""))
        pool_weights = entry.get("pool_weights", {})
        holdings = stock_weights_by_date.get(date_str, {})
        rebalance_log.append({
            "date": date_str,
            "pool_weights": {k: round(v, 4) for k, v in pool_weights.items()},
            "holdings": {k: round(v, 4) for k, v in holdings.items()},
        })

    nav_series = [round(float(x), 4) for x in bt.nav] if hasattr(bt, "nav") else []

    return {
        "strategy": "mlf_v4",
        "strategy_type": "mlf",
        "version": "v4",
        "oos_start": OOS_START,
        "oos_end": OOS_END,
        "n_days": int(bt.n_days),
        "final_nav": round(float(bt.final_nav), 4),
        "total_return": round(float(metrics.total_return), 4),
        "annualized_return": round(float(metrics.annualized_return), 4),
        "annualized_volatility": round(float(metrics.annualized_volatility), 4),
        "sharpe_ratio": round(float(metrics.sharpe_ratio), 4),
        "max_drawdown": round(float(metrics.max_drawdown), 4),
        "win_rate": round(float(metrics.win_rate), 4),
        "daily_returns": [round(float(x), 6) for x in returns],
        "dates": [str(d) for d in bt.dates] if hasattr(bt, "dates") and bt.dates else [],
        "nav_series": nav_series,
        "rebalance_log": rebalance_log,
        "elapsed_seconds": round(elapsed, 1),
    }


def load_industry_map() -> dict[str, dict[str, str]]:
    """加载股票行业分类"""
    fp = Path(INDUSTRY_FILE)
    if not fp.exists():
        return {}

    df = pl.read_parquet(fp)
    from ohmyquant.data.base import DataSource
    df = df.with_columns(
        pl.col("code").map_elements(DataSource.denormalize_code, return_dtype=pl.Utf8).alias("code")
    )

    industry_map = {}
    for row in df.iter_rows(named=True):
        code = row["code"]
        industry_map[code] = {
            "sw_l1": row.get("sw_l1_name") or "未分类",
            "jq_l1": row.get("jq_l1_name") or "未分类",
        }
    return industry_map


def analyze_industry(holdings, industry_map, label):
    """分析行业分布"""
    sw_counter = Counter()
    for code, weight in holdings.items():
        ind = industry_map.get(code, {"sw_l1": "未分类"})
        sw_counter[ind["sw_l1"]] += weight

    sw_count = Counter()
    for code in holdings:
        ind = industry_map.get(code, {"sw_l1": "未分类"})
        sw_count[ind["sw_l1"]] += 1

    total = sum(holdings.values())
    print(f"\n  [{label}] 行业分布 (申万一级):")
    print(f"  {'行业':<20} {'股票数':>6} {'权重':>8}")
    print(f"  {'-'*36}")
    for ind, w in sw_counter.most_common():
        pct = w / total * 100 if total > 0 else 0
        n = sw_count.get(ind, 0)
        print(f"  {ind:<20} {n:>6} {pct:>7.1f}%")

    # 金融占比
    financial = sw_counter.get("银行I", 0) + sw_counter.get("非银金融I", 0)
    fin_pct = financial / total * 100 if total > 0 else 0
    print(f"  >>> 金融合计: {fin_pct:.1f}%")

    return {k: round(v / total, 4) for k, v in sw_counter.most_common()}, fin_pct


def main():
    V4_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 运行 v4
    v4_result = run_v4_oos()
    with open(V4_OUTPUT_DIR / "results.json", "w", encoding="utf-8") as f:
        json.dump(v4_result, f, indent=2, ensure_ascii=False)

    # 2. 加载 v2/v3
    with open(V2_RESULTS, "r", encoding="utf-8") as f:
        v2_result = json.load(f)
    v3_result = None
    if V3_RESULTS.exists():
        with open(V3_RESULTS, "r", encoding="utf-8") as f:
            v3_result = json.load(f)

    # 3. 对比表
    print(f"\n\n{'='*70}")
    print("v2 vs v3 vs v4 全面对比")
    print(f"{'='*70}")
    print(f"\n{'指标':<16} {'v2(CSI300,4%)':>16} {'v3(CSI300,2.5%)':>16} {'v4(CSI800,4%)':>16}")
    print(f"{'-'*66}")
    print(f"{'候选池':<16} {'沪深300(361)':>16} {'沪深300(361)':>16} {'中证800(~800)':>16}")
    print(f"{'股票数':<16} {30:>16} {50:>16} {30:>16}")
    print(f"{'权重上限':<16} {'4%':>16} {'2.5%':>16} {'4%':>16}")
    print(f"{'总收益':<16} {v2_result['total_return']*100:>15.2f}% {v3_result['total_return']*100:>15.2f}% {v4_result['total_return']*100:>15.2f}%")
    print(f"{'Sharpe':<16} {v2_result['sharpe_ratio']:>16.4f} {v3_result['sharpe_ratio']:>16.4f} {v4_result['sharpe_ratio']:>16.4f}")
    print(f"{'最大回撤':<16} {v2_result['max_drawdown']*100:>15.2f}% {v3_result['max_drawdown']*100:>15.2f}% {v4_result['max_drawdown']*100:>15.2f}%")
    print(f"{'胜率':<16} {v2_result['win_rate']*100:>15.2f}% {v3_result['win_rate']*100:>15.2f}% {v4_result['win_rate']*100:>15.2f}%")

    # 4. 行业分析
    print(f"\n\n{'='*70}")
    print("行业分布对比")
    print(f"{'='*70}")

    industry_map = load_industry_map()
    if not industry_map:
        print("  行业数据加载失败")
        return

    for label, data in [("v2", v2_result), ("v3", v3_result), ("v4", v4_result)]:
        if data is None:
            continue
        for entry in data.get("rebalance_log", []):
            date = entry["date"]
            holdings = entry.get("holdings", {})
            key = f"{label}_{date}"
            if holdings:
                analyze_industry(holdings, industry_map, key)

    # 5. v4 持仓明细
    print(f"\n\n{'='*70}")
    print("v4 持仓明细")
    print(f"{'='*70}")
    for entry in v4_result.get("rebalance_log", []):
        date = entry["date"]
        holdings = entry.get("holdings", {})
        sorted_h = sorted(holdings.items(), key=lambda x: x[1], reverse=True)
        print(f"\n  {date}: {len(holdings)} 只, 总权重 {sum(holdings.values()):.2%}")
        print(f"  前10: {', '.join(f'{c}:{w:.2%}' for c, w in sorted_h[:10])}")

    # v4 换手
    v4_rebal = v4_result.get("rebalance_log", [])
    if len(v4_rebal) >= 2:
        h1 = set(v4_rebal[0].get("holdings", {}).keys())
        h2 = set(v4_rebal[1].get("holdings", {}).keys())
        added = h2 - h1
        removed = h1 - h2
        print(f"\n  v4 换手 (6/1 → 7/1):")
        print(f"    新增: {len(added)} 只, 剔除: {len(removed)} 只")
        if added:
            print(f"    新增: {sorted(added)}")
        if removed:
            print(f"    剔除: {sorted(removed)}")


if __name__ == "__main__":
    main()
