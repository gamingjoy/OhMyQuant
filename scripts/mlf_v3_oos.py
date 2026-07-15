"""mlf_v3 OOS 回测 + v2/v3 行业分布分析

1. 运行 mlf_v3 (2.5%权重上限, 50只股票) OOS 回测
2. 对比 v2 vs v3 的建仓/调仓明细
3. 分析 v2/v3 持仓的行业分布（申万一级）
4. 回答候选股票池问题
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ohmyquant.core.plugin_system import PluginRegistry, PluginType
from ohmyquant.strategy.registry import StrategyRegistry
from ohmyquant.strategy.runner import StrategyRunner
from ohmyquant.analysis.metrics import compute_metrics

OOS_START = "2026-06-01"
OOS_END = "2026-07-10"
DATA_ROOT = "D:/Work/Project/download_a_share/data"
INDUSTRY_FILE = f"{DATA_ROOT}/parquet/stock_industry/year=2026/data.parquet"

V2_RESULTS = Path("output/oos_2026/mlf_v2/results.json")
V3_OUTPUT_DIR = Path("output/oos_2026/mlf_v3")


def run_v3_oos() -> dict:
    """运行 mlf_v3 OOS 回测"""
    print(f"\n{'='*70}")
    print(f"运行 mlf_v3 OOS 回测 ({OOS_START} ~ {OOS_END})")
    print(f"  配置: top_n=50, max_stock_weight=2.5%, top_k_factors=25, train_window=1008")
    print(f"{'='*70}")

    t0 = time.time()
    PluginRegistry.discover_builtin()

    strategy = StrategyRegistry.create("mlf", "v3")
    strategy.config.backtest.start_date = OOS_START
    strategy.config.backtest.end_date = OOS_END
    strategy.config.rebalance.frequency = "monthly"

    print(f"  池: {list(strategy.config.pools.keys())}")
    print(f"  选股: {strategy.config.selection.method}, top_n={strategy.config.selection.top_n}")
    print(f"  权重上限: {strategy.config.selection.max_stock_weight}")

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
        "strategy": "mlf_v3",
        "strategy_type": "mlf",
        "version": "v3",
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
    """加载股票行业分类（申万一级 + 聚宽一级）"""
    fp = Path(INDUSTRY_FILE)
    if not fp.exists():
        print(f"  行业数据不存在: {fp}")
        return {}

    df = pl.read_parquet(fp)
    # code 格式: 000001.XSHE → 转为常规代码
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
            "zjw": row.get("zjw_name") or "未分类",
        }
    return industry_map


def analyze_industry_distribution(
    holdings: dict[str, float],
    industry_map: dict[str, dict[str, str]],
    label: str,
) -> dict:
    """分析持仓的行业分布"""
    sw_l1_counter = Counter()
    jq_l1_counter = Counter()

    for code, weight in holdings.items():
        ind = industry_map.get(code, {"sw_l1": "未分类", "jq_l1": "未分类"})
        sw_l1_counter[ind["sw_l1"]] += weight
        jq_l1_counter[ind["jq_l1"]] += weight

    total = sum(holdings.values())

    print(f"\n  [{label}] 行业分布 (申万一级, 按权重排序):")
    print(f"  {'行业':<20} {'股票数':>6} {'权重占比':>10}")
    print(f"  {'-'*40}")

    sw_stock_count = Counter()
    for code in holdings:
        ind = industry_map.get(code, {"sw_l1": "未分类"})
        sw_stock_count[ind["sw_l1"]] += 1

    for industry, weight in sw_l1_counter.most_common():
        pct = weight / total * 100 if total > 0 else 0
        n = sw_stock_count.get(industry, 0)
        print(f"  {industry:<20} {n:>6} {pct:>9.1f}%")

    return {
        "sw_l1": {k: round(v / total, 4) for k, v in sw_l1_counter.most_common()},
        "sw_l1_stock_count": dict(sw_stock_count.most_common()),
        "jq_l1": {k: round(v / total, 4) for k, v in jq_l1_counter.most_common()},
    }


def compare_v2_v3(v2_data: dict, v3_data: dict) -> None:
    """对比 v2 vs v3"""
    print(f"\n\n{'='*70}")
    print("v2 vs v3 对比")
    print(f"{'='*70}")

    print(f"\n{'指标':<20} {'v2 (4%上限,30只)':>20} {'v3 (2.5%上限,50只)':>20}")
    print(f"{'-'*62}")
    print(f"{'总收益':<20} {v2_data['total_return']*100:>19.2f}% {v3_data['total_return']*100:>19.2f}%")
    print(f"{'Sharpe':<20} {v2_data['sharpe_ratio']:>20.4f} {v3_data['sharpe_ratio']:>20.4f}")
    print(f"{'最大回撤':<20} {v2_data['max_drawdown']*100:>19.2f}% {v3_data['max_drawdown']*100:>19.2f}%")
    print(f"{'胜率':<20} {v2_data['win_rate']*100:>19.2f}% {v3_data['win_rate']*100:>19.2f}%")

    # 建仓对比
    for i, (v2_entry, v3_entry) in enumerate(
        zip(v2_data.get("rebalance_log", []), v3_data.get("rebalance_log", []))
    ):
        date = v2_entry["date"]
        v2_h = v2_entry.get("holdings", {})
        v3_h = v3_entry.get("holdings", {})

        print(f"\n  {date} 建仓/调仓对比:")
        print(f"    v2: {len(v2_h)} 只, 总权重 {sum(v2_h.values()):.2%}")
        print(f"    v3: {len(v3_h)} 只, 总权重 {sum(v3_h.values()):.2%}")

        # v2 vs v3 持仓差异
        v2_only = set(v2_h.keys()) - set(v3_h.keys())
        v3_only = set(v3_h.keys()) - set(v2_h.keys())
        common = set(v2_h.keys()) & set(v3_h.keys())

        if v2_only:
            print(f"    v2独有: {sorted(v2_only)[:10]}{'...' if len(v2_only) > 10 else ''}")
        if v3_only:
            print(f"    v3独有: {sorted(v3_only)[:10]}{'...' if len(v3_only) > 10 else ''}")
        print(f"    共同: {len(common)} 只")

        # v3 前10
        v3_top10 = sorted(v3_h.items(), key=lambda x: x[1], reverse=True)[:10]
        print(f"    v3 前10: {', '.join(f'{c}:{w:.2%}' for c, w in v3_top10)}")

    # v3 换手分析
    v3_rebal = v3_data.get("rebalance_log", [])
    if len(v3_rebal) >= 2:
        h1 = set(v3_rebal[0].get("holdings", {}).keys())
        h2 = set(v3_rebal[1].get("holdings", {}).keys())
        added = h2 - h1
        removed = h1 - h2
        print(f"\n  v3 换手分析 (6/1 → 7/1):")
        print(f"    新增: {len(added)} 只, 剔除: {len(removed)} 只")
        if added:
            print(f"    新增标的: {sorted(added)}")
        if removed:
            print(f"    剔除标的: {sorted(removed)}")


def main():
    V3_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 运行 v3 OOS
    v3_result = run_v3_oos()

    # 保存 v3 结果
    v3_file = V3_OUTPUT_DIR / "results.json"
    with open(v3_file, "w", encoding="utf-8") as f:
        json.dump(v3_result, f, indent=2, ensure_ascii=False)
    print(f"\n  v3 结果已保存: {v3_file}")

    # 2. 加载 v2 结果
    with open(V2_RESULTS, "r", encoding="utf-8") as f:
        v2_result = json.load(f)

    # 3. 对比 v2 vs v3
    compare_v2_v3(v2_result, v3_result)

    # 4. 行业分析
    print(f"\n\n{'='*70}")
    print("行业分布分析")
    print(f"{'='*70}")

    industry_map = load_industry_map()
    if not industry_map:
        print("  行业数据加载失败，跳过行业分析")
        return

    print(f"  行业数据加载成功: {len(industry_map)} 只股票")

    industry_analysis = {}

    for label, data in [("v2", v2_result), ("v3", v3_result)]:
        for entry in data.get("rebalance_log", []):
            date = entry["date"]
            holdings = entry.get("holdings", {})
            key = f"{label}_{date}"
            print(f"\n  --- {label.upper()} {date} ({len(holdings)} 只) ---")
            dist = analyze_industry_distribution(holdings, industry_map, key)
            industry_analysis[key] = dist

    # 保存行业分析
    ind_file = V3_OUTPUT_DIR / "industry_analysis.json"
    with open(ind_file, "w", encoding="utf-8") as f:
        json.dump(industry_analysis, f, indent=2, ensure_ascii=False)
    print(f"\n  行业分析已保存: {ind_file}")

    # 5. 候选股票池信息
    print(f"\n\n{'='*70}")
    print("候选股票池分析")
    print(f"{'='*70}")
    print(f"  当前配置: pools.stocks.index = '000300.XSHG' (沪深300)")
    print(f"  候选股票: 沪深300成分股 (~361 只)")
    print(f"  非全部A股 (~5000+ 只)")
    print(f"  ")
    print(f"  如需扩展到全部A股，修改 config.yaml:")
    print(f"    pools:")
    print(f"      stocks:")
    print(f"        universe: all_a_share  # 替代 index: '000300.XSHG'")
    print(f"  ")
    print(f"  注意: 全A股会增加噪声，可能需要调整 top_k_factors 和 top_n")


if __name__ == "__main__":
    main()
