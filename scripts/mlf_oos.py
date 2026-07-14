"""mlf_v2 样本外回测 + 与现有策略+沪深300基线对比

1. 运行 mlf_v2 OOS 回测 (2026-06-01 ~ 2026-07-10, 月度调仓)
2. 加载 mlf_v1 修复前基线结果
3. 获取沪深300指数同期收益作为基线
4. 加载已有策略结果，输出完整对比
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ohmyquant.core.plugin_system import PluginRegistry, PluginType
from ohmyquant.data.base import DataCatalog
from ohmyquant.strategy.registry import StrategyRegistry
from ohmyquant.strategy.runner import StrategyRunner
from ohmyquant.analysis.metrics import compute_metrics

OOS_START = "2026-06-01"
OOS_END = "2026-07-10"
OUTPUT_DIR = Path("output/oos_2026/mlf_v2")
EXISTING_COMPARISON = Path("output/oos_2026/oos_comparison.json")
MLF_V1_BASELINE = Path("output/oos_2026/mlf_v1/results.json")


def run_mlf_oos() -> dict:
    """运行 mlf_v2 样本外回测"""
    print(f"\n{'='*60}")
    print(f"运行 mlf_v2 样本外回测 ({OOS_START} ~ {OOS_END})")
    print(f"{'='*60}")

    t0 = time.time()
    PluginRegistry.discover_builtin()

    strategy = StrategyRegistry.create("mlf", "v2")
    strategy.config.backtest.start_date = OOS_START
    strategy.config.backtest.end_date = OOS_END
    strategy.config.rebalance.frequency = "monthly"

    print(f"  池: {list(strategy.config.pools.keys())}")
    print(f"  选股: {strategy.config.selection.method}, top_n={strategy.config.selection.top_n}")
    print(f"  风控: target_vol={strategy.config.risk.target_vol}")
    print(f"  MLF: top_k={strategy.config.selection.mlf.get('top_k_factors')}")

    runner = StrategyRunner(strategy.config)
    result = runner.run()

    bt = result.backtest_result
    returns = bt.daily_returns
    metrics = compute_metrics(returns)

    elapsed = time.time() - t0
    print(f"  完成 ({elapsed:.1f}s): 净值={bt.final_nav:.4f}, 天数={bt.n_days}")

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

    nav_series = (
        [round(float(x), 4) for x in bt.nav] if hasattr(bt, "nav") else []
    )

    return {
        "strategy": "mlf_v2",
        "strategy_type": "mlf",
        "version": "v2",
        "oos_start": OOS_START,
        "oos_end": OOS_END,
        "n_days": int(bt.n_days),
        "final_nav": round(float(bt.final_nav), 4),
        "total_return": round(float(metrics.total_return), 4),
        "annualized_return": round(float(metrics.annualized_return), 4),
        "annualized_volatility": round(
            float(metrics.annualized_volatility), 4
        ),
        "sharpe_ratio": round(float(metrics.sharpe_ratio), 4),
        "max_drawdown": round(float(metrics.max_drawdown), 4),
        "win_rate": round(float(metrics.win_rate), 4),
        "daily_returns": [round(float(x), 6) for x in returns],
        "dates": (
            [str(d) for d in bt.dates]
            if hasattr(bt, "dates") and bt.dates
            else []
        ),
        "nav_series": nav_series,
        "rebalance_log": rebalance_log,
        "elapsed_seconds": round(elapsed, 1),
    }


def get_csi300_baseline() -> dict | None:
    """获取沪深300指数同期收益作为基线"""
    print(f"\n{'='*60}")
    print(f"获取沪深300基线 ({OOS_START} ~ {OOS_END})")
    print(f"{'='*60}")

    try:
        source = PluginRegistry.create(
            PluginType.DATA_SOURCE,
            "duckdb",
            config={"data_root": "D:/Work/Project/download_a_share/data"},
        )
        catalog = DataCatalog(source)

        idx_df = catalog.get_index_data("000300.XSHG", OOS_START, OOS_END)
        if idx_df is None or len(idx_df) == 0:
            print("  沪深300指数数据为空")
            return None

        if "date" in idx_df.columns:
            idx_df = idx_df.sort("date")

        close_col = (
            "close" if "close" in idx_df.columns else idx_df.columns[-1]
        )
        closes = idx_df[close_col].to_list()
        nav = [1.0]
        daily_returns = []
        for i in range(1, len(closes)):
            ret = (closes[i] - closes[i - 1]) / closes[i - 1]
            daily_returns.append(round(ret, 6))
            nav.append(round(nav[-1] * (1 + ret), 4))

        dates = [str(d) for d in idx_df["date"].to_list()]
        metrics = compute_metrics(daily_returns)

        print(f"  沪深300基线: 净值={nav[-1]:.4f}, 天数={len(daily_returns)}")

        return {
            "strategy": "CSI300_baseline",
            "strategy_type": "baseline",
            "version": "",
            "oos_start": OOS_START,
            "oos_end": OOS_END,
            "n_days": len(daily_returns),
            "final_nav": nav[-1],
            "total_return": round(float(metrics.total_return), 4),
            "annualized_return": round(
                float(metrics.annualized_return), 4
            ),
            "annualized_volatility": round(
                float(metrics.annualized_volatility), 4
            ),
            "sharpe_ratio": round(float(metrics.sharpe_ratio), 4),
            "max_drawdown": round(float(metrics.max_drawdown), 4),
            "win_rate": round(float(metrics.win_rate), 4),
            "daily_returns": daily_returns,
            "dates": dates,
            "nav_series": nav,
            "rebalance_log": [],
            "elapsed_seconds": 0.0,
        }
    except Exception as e:
        print(f"  获取沪深300基线失败: {e}")
        import traceback

        traceback.print_exc()
        return None


def load_existing_results() -> list[dict]:
    """加载已有策略对比结果"""
    if not EXISTING_COMPARISON.exists():
        print(f"  未找到现有对比文件: {EXISTING_COMPARISON}")
        return []

    try:
        with open(EXISTING_COMPARISON, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  加载现有结果失败: {e}")
        return []


def load_mlf_v1_baseline() -> dict | None:
    """加载 mlf_v1 修复前基线结果"""
    if not MLF_V1_BASELINE.exists():
        print(f"  未找到 mlf_v1 基线: {MLF_V1_BASELINE}")
        return None

    try:
        with open(MLF_V1_BASELINE, "r", encoding="utf-8") as f:
            data = json.load(f)
            data["strategy"] = "mlf_v1(修复前)"
            return data
    except Exception as e:
        print(f"  加载 mlf_v1 基线失败: {e}")
        return None


def print_comparison(
    mlf_v2_result: dict,
    mlf_v1_baseline: dict | None,
    baseline: dict | None,
    existing: list[dict],
) -> None:
    """打印完整对比表"""
    print(f"\n\n{'='*90}")
    print(f"完整对比 (2026-06-01 ~ 2026-07-10)")
    print(f"{'='*90}")

    print(
        f"\n{'策略':<20} {'总收益':>8} {'年化收益':>10} {'Sharpe':>8} "
        f"{'最大回撤':>8} {'胜率':>8} {'天数':>6}"
    )
    print("-" * 80)

    strategies = sorted(
        existing, key=lambda x: x["total_return"], reverse=True
    )
    for r in strategies:
        print(
            f"{r['strategy']:<20} "
            f"{r['total_return']*100:>7.2f}% "
            f"{r['annualized_return']*100:>9.2f}% "
            f"{r['sharpe_ratio']:>8.4f} "
            f"{r['max_drawdown']*100:>7.2f}% "
            f"{r['win_rate']*100:>7.2f}% "
            f"{r['n_days']:>6d}"
        )

    print("-" * 80)

    # mlf_v1 修复前基线
    if mlf_v1_baseline:
        r = mlf_v1_baseline
        print(
            f"{r['strategy']:<20} "
            f"{r['total_return']*100:>7.2f}% "
            f"{r['annualized_return']*100:>9.2f}% "
            f"{r['sharpe_ratio']:>8.4f} "
            f"{r['max_drawdown']*100:>7.2f}% "
            f"{r['win_rate']*100:>7.2f}% "
            f"{r['n_days']:>6d}"
        )

    # mlf_v2 修复后
    r = mlf_v2_result
    print(
        f"{'>>> ' + r['strategy']:<20} "
        f"{r['total_return']*100:>7.2f}% "
        f"{r['annualized_return']*100:>9.2f}% "
        f"{r['sharpe_ratio']:>8.4f} "
        f"{r['max_drawdown']*100:>7.2f}% "
        f"{r['win_rate']*100:>7.2f}% "
        f"{r['n_days']:>6d}"
    )

    if baseline:
        r = baseline
        print(
            f"{r['strategy']:<20} "
            f"{r['total_return']*100:>7.2f}% "
            f"{r['annualized_return']*100:>9.2f}% "
            f"{r['sharpe_ratio']:>8.4f} "
            f"{r['max_drawdown']*100:>7.2f}% "
            f"{r['win_rate']*100:>7.2f}% "
            f"{r['n_days']:>6d}"
        )

    # mlf_v2 建仓/调仓明细
    print(f"\n{'='*90}")
    print("mlf_v2 建仓/调仓明细")
    print(f"{'='*90}")
    for entry in mlf_v2_result.get("rebalance_log", []):
        date = entry["date"]
        pool_weights = entry.get("pool_weights", {})
        holdings = entry.get("holdings", {})
        top_holdings = sorted(
            holdings.items(), key=lambda x: x[1], reverse=True
        )[:10]
        holdings_str = ", ".join(f"{k}:{v:.1%}" for k, v in top_holdings)
        pool_str = ", ".join(f"{k}:{v:.0%}" for k, v in pool_weights.items())
        print(
            f"  {date} 池权重[{pool_str}] "
            f"持仓{len(holdings)}只, 前10: {holdings_str}"
        )

    # 每日净值对比 (mlf_v2 vs mlf_v1 修复前 vs CSI300)
    if mlf_v1_baseline and mlf_v2_result.get("dates"):
        print(f"\n{'='*90}")
        print("每日净值 (mlf_v2 vs mlf_v1修复前 vs CSI300)")
        print(f"{'='*90}")
        dates = mlf_v2_result["dates"]
        print(
            f"{'日期':<12}{'mlf_v2':>12}{'mlf_v1旧':>12}"
            f"{'CSI300':>12}{'差值(v2-v1)':>16}"
        )
        print("-" * 64)
        for i, date in enumerate(dates):
            v2 = (
                mlf_v2_result["nav_series"][i]
                if i < len(mlf_v2_result["nav_series"])
                else 0
            )
            v1 = (
                mlf_v1_baseline["nav_series"][i]
                if i < len(mlf_v1_baseline["nav_series"])
                else 0
            )
            bv = (
                baseline["nav_series"][i]
                if baseline and i < len(baseline["nav_series"])
                else 0
            )
            diff = v2 - v1
            print(
                f"{date:<12}{v2:>12.4f}{v1:>12.4f}{bv:>12.4f}{diff:>16.4f}"
            )


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    mlf_v2_result = run_mlf_oos()
    mlf_v1_baseline = load_mlf_v1_baseline()
    baseline = get_csi300_baseline()
    existing = load_existing_results()

    print_comparison(mlf_v2_result, mlf_v1_baseline, baseline, existing)

    results_file = OUTPUT_DIR / "results.json"
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(mlf_v2_result, f, indent=2, ensure_ascii=False)
    print(f"\nmlf_v2 结果已保存: {results_file}")

    if baseline:
        baseline_file = OUTPUT_DIR / "csi300_baseline.json"
        with open(baseline_file, "w", encoding="utf-8") as f:
            json.dump(baseline, f, indent=2, ensure_ascii=False)
        print(f"沪深300基线已保存: {baseline_file}")


if __name__ == "__main__":
    main()
