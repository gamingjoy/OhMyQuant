"""行业轮动策略每日调仓检查

T日早晨运行：下载T-1数据后，运行本脚本检查是否需要调仓。
- 自动检测最新数据日期
- 运行OOS回测到最新日期
- 判断最新数据日是否为调仓日
- 如需调仓，自动生成同花顺交易流水文件
- 如无需调仓，显示当前持仓和下次调仓日

用法:
    python scripts/industry_rotation_daily.py                       # 默认 v53 检查最新数据日
    python scripts/industry_rotation_daily.py --version v53         # 指定版本
    python scripts/industry_rotation_daily.py --date 2026-07-20     # 指定日期检查
    python scripts/industry_rotation_daily.py --version v40         # 使用旧版本 v40
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np

from ohmyquant.data.sources.duckdb_source import DuckDBSource
from ohmyquant.execution.ths_utils import (
    CAPITAL,
    LOT_SIZE,
    TEMPLATE_PATH,
    TRANSACTION_COST_RATE,
    compute_lot_shares,
    generate_trades,
    get_open_prices,
    replay_history,
    write_xlsx,
)
from ohmyquant.strategy import StrategyRegistry, StrategyRunner

logger = logging.getLogger(__name__)

DEFAULT_VERSION = "v53"  # 当前 final 版本（v43 为旧 final，已 superseded）
DATA_ROOT = "D:/Work/Project/download_a_share/data"
OOS_START = "2026-06-01"
OUTPUT_DIR = Path(f"output/ths/industry_rotation_{DEFAULT_VERSION}")


def get_latest_data_date(source: DuckDBSource) -> str:
    """获取最新数据日期"""
    latest = source.get_latest_date()
    print(f"最新数据日期: {latest}")
    return latest


def run_oos_backtest(end_date: str, version: str = DEFAULT_VERSION) -> dict:
    """运行OOS回测到指定日期，返回结果和调仓历史"""
    print(f"运行OOS回测: {OOS_START} → {end_date} (version={version})")

    config_override = {
        "backtest": {
            "start_date": OOS_START,
            "end_date": end_date,
        }
    }
    strategy = StrategyRegistry.create("industry_rotation", version, config_override)
    runner = StrategyRunner(strategy.config)
    result = runner.run()

    bt = result.backtest_result
    nav = bt.nav
    daily_returns = bt.daily_returns

    n_days = len(nav)
    final_nav = float(nav[-1]) if n_days > 0 else 1.0
    total_return = final_nav - 1.0

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

    print(f"  净值: {final_nav:.4f}  收益: {total_return:+.2%}  "
          f"Sharpe: {sharpe:.4f}  最大回撤: {max_drawdown:.2%}")

    # 获取调仓历史
    stock_weights = bt.stock_weights_by_date
    rebalance_log = []
    for entry in bt.pool_weight_log:
        date_str = str(entry.get("date", ""))
        holdings = stock_weights.get(date_str, {})
        rebalance_log.append({
            "date": date_str,
            "holdings": {k: round(v, 4) for k, v in holdings.items()},
        })

    return {
        "final_nav": final_nav,
        "total_return": total_return,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "rebalance_log": rebalance_log,
    }


def main():
    parser = argparse.ArgumentParser(description="行业轮动策略每日调仓检查")
    parser.add_argument("--version", default=DEFAULT_VERSION,
                        help=f"策略版本(默认 {DEFAULT_VERSION})")
    parser.add_argument("--date", default=None,
                        help="指定日期(YYYY-MM-DD)，默认用最新数据日")
    args = parser.parse_args()

    version = args.version
    strategy_name = f"industry_rotation_{version}"
    output_dir = Path(f"output/ths/{strategy_name}")

    source = DuckDBSource({"data_root": DATA_ROOT})

    # 1. 确定检查日期
    if args.date:
        check_date = args.date
    else:
        check_date = get_latest_data_date(source)

    check_dt = datetime.strptime(check_date, "%Y-%m-%d")
    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    print(f"策略版本: {strategy_name}")
    print(f"检查日期: {check_date} ({weekday_names[check_dt.weekday()]})")
    print("=" * 60)

    # 2. 运行OOS回测到检查日期
    result = run_oos_backtest(check_date, version=version)
    rebalance_log = result["rebalance_log"]

    if not rebalance_log:
        print("无调仓记录")
        return

    # 3. 判断是否需要调仓
    last_rebalance = rebalance_log[-1]
    last_rebalance_date = last_rebalance["date"]
    last_holdings = last_rebalance["holdings"]

    print(f"\n最近调仓日: {last_rebalance_date}")
    print(f"当前持仓: {len(last_holdings)} 只, 总权重 {sum(last_holdings.values()):.2%}")

    # 显示持仓
    try:
        industry_map = source.load_industry_map()
        from collections import Counter
        sw_counter = Counter()
        for code, w in last_holdings.items():
            ind = industry_map.get(code, "未知")
            sw_counter[ind] += w
        print("行业分布:")
        for ind, w in sw_counter.most_common():
            print(f"  {ind}: {w:.2%}")
        print("持仓明细:")
        for code, w in sorted(last_holdings.items(), key=lambda x: x[1], reverse=True):
            ind = industry_map.get(code, "未知")
            print(f"  {code:<12} {w:.2%}  {ind}")
    except Exception as e:
        print(f"行业分析失败: {e}")

    # 4. 判断是否需要生成调仓文件
    need_rebalance = (last_rebalance_date == check_date)

    if not need_rebalance:
        # 计算下次调仓日（下个周一）
        days_to_monday = (7 - check_dt.weekday()) % 7
        if days_to_monday == 0:
            days_to_monday = 7
        next_monday = check_dt + timedelta(days=days_to_monday)
        print(f"\n>>> 今日({check_date})非调仓日，无需操作")
        print(f">>> 下次调仓日: {next_monday.strftime('%Y-%m-%d')} (周一)")
        return

    # 5. 需要调仓，生成同花顺文件
    print(f"\n>>> 今日({check_date})为调仓日，生成同花顺交易流水...")

    # 回放历史调仓重建持仓状态（无需state.json，每次完整重建）
    prev_shares, prev_cash = replay_history(
        source, rebalance_log, check_date, strategy_name=strategy_name
    )
    is_build = (len(prev_shares) == 0)

    if is_build:
        print(f"  首次建仓（无历史持仓）")
    else:
        print(f"  当前持仓: {len(prev_shares)} 只, 现金 {prev_cash:,.0f}")

    # 获取所有股票的开盘价（当前持仓 + 目标持仓），避免漏卖漏买
    all_codes = list(set(list(prev_shares.keys()) + list(last_holdings.keys())))
    if not all_codes:
        print(f"  目标持仓和当前持仓都为空（继续空仓），无需生成交易文件")
        return
    open_prices = get_open_prices(source, all_codes, check_date)
    if not open_prices:
        print(f"无法获取{check_date}开盘价，无法生成交易文件")
        return

    trades, new_shares, new_cash = generate_trades(
        check_date, prev_shares, last_holdings, open_prices, prev_cash, is_build,
        strategy_name=strategy_name,
    )

    if not trades:
        print("无交易需要执行（持仓未变化）")
        return

    # 写入文件
    if is_build:
        filename = f"{check_date.replace('-', '')}_build.xlsx"
        label = "建仓"
    else:
        filename = f"{check_date.replace('-', '')}_rebalance.xlsx"
        label = "调仓"

    output_path = output_dir / filename
    write_xlsx(trades, output_path)

    # 打印摘要
    buy_count = sum(1 for t in trades if t["业务类型"] == "买入")
    sell_count = sum(1 for t in trades if t["业务类型"] == "卖出")
    total_amount = sum(t["成交金额"] for t in trades)
    total_cost = sum(t["费用"] for t in trades)
    print(f"\n{label}完成: {len(trades)}笔 (买{buy_count}/卖{sell_count})")
    print(f"交易金额: {total_amount:,.0f}  费用: {total_cost:,.0f}")
    for t in trades:
        action = "买" if t["业务类型"] == "买入" else "卖"
        print(f"  {action} {t['证券代码']:<12} {t['数量']:>6d}股 @{t['价格']:.2f}")
    print(f"\n文件已生成: {output_path}")
    print(f"剩余现金: {new_cash:,.0f}")
    print(f"持仓: {len(new_shares)} 只")


if __name__ == "__main__":
    main()
