"""回测引擎：T+1开盘价成交，计算净值与绩效指标

交易规则:
  1. 每周调仓日t选股，t+1开盘价成交
  2. 佣金双向万1 + 单边滑点0.10%
  3. 等权配置Top-N只个股
  4. 非调仓日持有不动

绩效指标:
  - 年化收益、最大回撤、超额夏普IR、Calmar比率
  - 年化波动率、月度胜率、换手率
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
import polars as pl

from ohmyquant.core.logging import get_logger

logger = get_logger(__name__)

TRADING_DAYS = 242
RISK_FREE_RATE = 0.02


def run_backtest(
    wf_results: list[dict],
    price_df: pl.DataFrame,
    bench_df: pl.DataFrame,
    trade_calendar: list[str],
    config: dict,
) -> dict[str, Any]:
    """执行回测，返回净值序列与绩效指标

    Args:
        wf_results: Walk Forward输出 [{date, selected_codes, ...}]
        price_df: 行情数据 [date, code, open, close, ...]
        bench_df: 基准数据 [date, close, ...]
        trade_calendar: 交易日历列表
        config: 策略配置

    Returns:
        dict: nav, daily_returns, dates, metrics, holdings_log
    """
    cost_rate = config.get("backtest", {}).get("transaction_cost", 0.0001)
    slippage = config.get("backtest", {}).get("slippage", 0.001)
    total_cost = cost_rate * 2 + slippage * 2  # 买卖双向佣金+滑点

    # 构建价格查找表
    price_df = price_df.with_columns(pl.col("date").cast(pl.Date))
    price_df = price_df.sort(["code", "date"])

    # 开盘价查找表 (date, code) -> open
    open_pivot = price_df.select([
        pl.col("date").dt.strftime("%Y-%m-%d"),
        "code",
        "open",
    ]).pivot(values="open", index="date", on="code", aggregate_function="first")

    # 收盘价查找表 (date, code) -> close
    close_pivot = price_df.select([
        pl.col("date").dt.strftime("%Y-%m-%d"),
        "code",
        "close",
    ]).pivot(values="close", index="date", on="code", aggregate_function="first")

    # 基准净值
    bench_df = bench_df.with_columns(pl.col("date").dt.strftime("%Y-%m-%d")).sort("date")
    bench_close = dict(zip(bench_df["date"].to_list(), bench_df["close"].to_list()))
    bench_first = bench_df["close"][0]

    # 构建调仓日 → 选股列表的映射
    # 调仓日t选股，t+1成交
    rebalance_map: dict[str, list[str]] = {}
    for r in wf_results:
        if r["selected_codes"]:
            rebalance_map[r["date"]] = r["selected_codes"]

    # 按交易日遍历
    nav = 1.0
    bench_nav = 1.0
    current_holdings: dict[str, float] = {}  # code → weight
    pending_trades: dict[str, float] | None = None  # 下一日要执行的调仓

    nav_list = []
    bench_nav_list = []
    daily_ret_list = []
    dates_list = []
    holdings_log = []
    turnover_log = []

    for date_str in trade_calendar:
        # 检查是否有待执行调仓（昨日选股，今日成交）
        if pending_trades is not None:
            # 执行调仓：T+1开盘价成交
            new_holdings = pending_trades
            # 计算换手率
            old_codes = set(current_holdings.keys())
            new_codes = set(new_holdings.keys())
            bought = new_codes - old_codes
            sold = old_codes - new_codes
            turnover = (len(bought) + len(sold)) / max(len(new_codes | old_codes), 1)
            turnover_log.append({"date": date_str, "turnover": turnover})

            current_holdings = new_holdings
            pending_trades = None

            # 交易成本从NAV中扣除
            nav *= (1 - total_cost * turnover)

        # 检查是否为调仓日（选股，下一日成交）
        if date_str in rebalance_map:
            selected = rebalance_map[date_str]
            if selected:
                weight = 1.0 / len(selected)
                pending_trades = {code: weight for code in selected}
            else:
                pending_trades = {}

        # 计算当日持仓收益（用收盘价）
        daily_return = 0.0
        if current_holdings and date_str in close_pivot["date"].to_list():
            row = close_pivot.filter(pl.col("date") == date_str)
            if len(row) > 0:
                row_dict = row.to_dicts()[0]
                # 计算持仓的日收益率
                prev_date_idx = trade_calendar.index(date_str) - 1
                if prev_date_idx >= 0:
                    prev_date_str = trade_calendar[prev_date_idx]
                    prev_row = close_pivot.filter(pl.col("date") == prev_date_str)
                    if len(prev_row) > 0:
                        prev_dict = prev_row.to_dicts()[0]
                        for code, weight in current_holdings.items():
                            curr_close = row_dict.get(code)
                            prev_close = prev_dict.get(code)
                            if curr_close and prev_close and not np.isnan(curr_close) and not np.isnan(prev_close) and prev_close > 0:
                                stock_ret = curr_close / prev_close - 1
                                daily_return += weight * stock_ret

        nav *= (1 + daily_return)
        nav_list.append(nav)

        # 基准收益
        bench_price = bench_close.get(date_str)
        if bench_price and bench_first > 0:
            bench_nav = bench_price / bench_first
        bench_nav_list.append(bench_nav)

        bench_ret = 0.0
        if len(bench_nav_list) >= 2:
            bench_ret = bench_nav_list[-1] / bench_nav_list[-2] - 1

        daily_ret_list.append(daily_return)
        dates_list.append(date_str)

        if current_holdings:
            holdings_log.append({
                "date": date_str,
                "holdings": dict(current_holdings),
                "n_stocks": len(current_holdings),
            })

    # 计算绩效指标
    nav_arr = np.array(nav_list)
    bench_arr = np.array(bench_nav_list)
    daily_rets = np.array(daily_ret_list)
    bench_rets = np.diff(np.concatenate([[1.0], bench_arr]))

    # 超额收益
    excess_rets = daily_rets - bench_rets[:len(daily_rets)]

    metrics = _compute_metrics(nav_arr, bench_arr, daily_rets, bench_rets, excess_rets, dates_list)

    return {
        "nav": pl.Series(nav_list),
        "dates": dates_list,
        "daily_returns": pl.Series(daily_ret_list),
        "benchmark_nav": pl.Series(bench_nav_list),
        "metrics": metrics,
        "holdings_log": holdings_log,
        "turnover_log": turnover_log,
    }


def _compute_metrics(
    nav: np.ndarray,
    bench_nav: np.ndarray,
    daily_rets: np.ndarray,
    bench_rets: np.ndarray,
    excess_rets: np.ndarray,
    dates: list[str] | None = None,
) -> dict[str, float]:
    """计算绩效指标"""
    n_days = len(nav)
    if n_days < 2:
        return {}

    # 总收益
    total_return = float(nav[-1] / nav[0] - 1) if nav[0] > 0 else float(nav[-1] - 1)
    bench_total = float(bench_nav[-1] / bench_nav[0] - 1) if bench_nav[0] > 0 else float(bench_nav[-1] - 1)

    # 年化收益
    years = n_days / TRADING_DAYS
    ann_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
    bench_ann = (1 + bench_total) ** (1 / years) - 1 if years > 0 else 0

    # 年化波动率
    ann_vol = float(np.std(daily_rets, ddof=1) * np.sqrt(TRADING_DAYS)) if len(daily_rets) > 1 else 0
    bench_vol = float(np.std(bench_rets, ddof=1) * np.sqrt(TRADING_DAYS)) if len(bench_rets) > 1 else 0

    # Sharpe
    rf_daily = (1 + RISK_FREE_RATE) ** (1 / TRADING_DAYS) - 1
    sharpe = float((np.mean(daily_rets) - rf_daily) / np.std(daily_rets, ddof=1) * np.sqrt(TRADING_DAYS)) if len(daily_rets) > 1 and np.std(daily_rets, ddof=1) > 0 else 0
    bench_sharpe = float((np.mean(bench_rets) - rf_daily) / np.std(bench_rets, ddof=1) * np.sqrt(TRADING_DAYS)) if len(bench_rets) > 1 and np.std(bench_rets, ddof=1) > 0 else 0

    # 最大回撤
    peak = np.maximum.accumulate(nav)
    drawdown = (nav - peak) / peak
    max_drawdown = float(np.min(drawdown))
    bench_peak = np.maximum.accumulate(bench_nav)
    bench_dd = (bench_nav - bench_peak) / bench_peak
    bench_max_dd = float(np.min(bench_dd))

    # 超额夏普IR
    ir = float(np.mean(excess_rets) / np.std(excess_rets, ddof=1) * np.sqrt(TRADING_DAYS)) if len(excess_rets) > 1 and np.std(excess_rets, ddof=1) > 0 else 0

    # Calmar
    calmar = float(ann_return / abs(max_drawdown)) if max_drawdown != 0 else 0

    # 月度胜率 (使用实际日历月)
    monthly_rets = []
    if dates is not None and len(dates) == len(daily_rets):
        current_month = None
        month_ret = 1.0
        for i, d in enumerate(daily_rets):
            month_str = dates[i][:7]  # "YYYY-MM"
            if current_month is None:
                current_month = month_str
            if month_str != current_month:
                monthly_rets.append(month_ret - 1)
                month_ret = 1.0
                current_month = month_str
            month_ret *= (1 + d)
        if month_ret != 1.0 or not monthly_rets:
            monthly_rets.append(month_ret - 1)
    else:
        # 回退: 每22天算一个月
        month_ret = 1.0
        for i, d in enumerate(daily_rets):
            month_ret *= (1 + d)
            if (i + 1) % 22 == 0 or i == len(daily_rets) - 1:
                monthly_rets.append(month_ret - 1)
                month_ret = 1.0
    win_rate = float(sum(1 for r in monthly_rets if r > 0) / len(monthly_rets)) if monthly_rets else 0

    return {
        "total_return": total_return,
        "bench_total_return": bench_total,
        "excess_return": total_return - bench_total,
        "ann_return": ann_return,
        "bench_ann_return": bench_ann,
        "ann_volatility": ann_vol,
        "bench_volatility": bench_vol,
        "sharpe": sharpe,
        "bench_sharpe": bench_sharpe,
        "max_drawdown": max_drawdown,
        "bench_max_drawdown": bench_max_dd,
        "information_ratio": ir,
        "calmar": calmar,
        "monthly_win_rate": win_rate,
        "n_days": n_days,
        "final_nav": float(nav[-1]),
    }


def print_metrics(metrics: dict[str, float], strategy_name: str = "expertForest_v1"):
    """打印绩效指标"""
    print("\n" + "=" * 70)
    print(f"  {strategy_name} 回测绩效")
    print("=" * 70)
    print(f"  交易日数:       {metrics.get('n_days', 0)}")
    print(f"  最终净值:       {metrics.get('final_nav', 0):.4f}")
    print(f"  累计收益:       {metrics.get('total_return', 0):>+10.2%}  (基准 {metrics.get('bench_total_return', 0):>+10.2%})")
    print(f"  超额收益:       {metrics.get('excess_return', 0):>+10.2%}")
    print(f"  年化收益:       {metrics.get('ann_return', 0):>+10.2%}  (基准 {metrics.get('bench_ann_return', 0):>+10.2%})")
    print(f"  年化波动率:     {metrics.get('ann_volatility', 0):>10.2%}  (基准 {metrics.get('bench_volatility', 0):>10.2%})")
    print(f"  Sharpe:         {metrics.get('sharpe', 0):>10.4f}  (基准 {metrics.get('bench_sharpe', 0):>10.4f})")
    print(f"  最大回撤:       {metrics.get('max_drawdown', 0):>+10.2%}  (基准 {metrics.get('bench_max_drawdown', 0):>+10.2%})")
    print(f"  超额夏普IR:     {metrics.get('information_ratio', 0):>10.4f}")
    print(f"  Calmar:         {metrics.get('calmar', 0):>10.4f}")
    print(f"  月度胜率:       {metrics.get('monthly_win_rate', 0):>10.2%}")
    print("=" * 70)
