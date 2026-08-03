"""expertForest_v1 每日调仓检查与同花顺交易文件生成

T日早晨运行:
  1. 检查最新数据日期
  2. 运行OOS回测获取最新调仓信号
  3. 判断是否为调仓日(每周一)
  4. 生成同花顺交易流水xlsx

用法:
  python scripts/expertforest_v1/expertforest_v1_daily.py
  python scripts/expertforest_v1/expertforest_v1_daily.py --date 2026-07-20
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ohmyquant.data.sources.duckdb_source import DuckDBSource
from ohmyquant.execution.ths_utils import (
    CAPITAL,
    generate_trades,
    get_open_prices,
    replay_history,
    write_xlsx,
)
from ohmyquant.strategy.runner import run_oos_backtest

logger = logging.getLogger(__name__)

DEFAULT_VERSION = "v1"
DATA_ROOT = "D:/Work/Project/download_a_share/data"
OOS_START = "2026-06-01"
OUTPUT_DIR = Path(f"output/ths/expertforest_v1")


def get_latest_data_date(source: DuckDBSource) -> str:
    """获取最新数据日期"""
    latest = source.get_latest_date()
    print(f"最新数据日期: {latest}")
    return latest


def main():
    parser = argparse.ArgumentParser(description="expertForest_v1 策略每日调仓检查")
    parser.add_argument("--version", default=DEFAULT_VERSION,
                        help=f"策略版本(默认 {DEFAULT_VERSION})")
    parser.add_argument("--date", default=None,
                        help="指定日期(YYYY-MM-DD)，默认用最新数据日")
    args = parser.parse_args()

    version = args.version
    strategy_name = f"expertforest_v1"
    output_dir = Path(f"output/ths/{strategy_name}")

    source = DuckDBSource({"data_root": DATA_ROOT})

    # 1. 确定检查日期
    if args.date:
        check_date = args.date
    else:
        check_date = get_latest_data_date(source)

    check_dt = datetime.strptime(check_date, "%Y-%m-%d")
    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    print(f"策略版本: {strategy_name} {version}")
    print(f"检查日期: {check_date} ({weekday_names[check_dt.weekday()]})")
    print("=" * 60)

    # 2. 运行OOS回测到检查日期
    result = run_oos_backtest("expertForest", version, OOS_START, check_date)
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
    print("持仓明细:")
    for code, w in sorted(last_holdings.items(), key=lambda x: x[1], reverse=True):
        print(f"  {code:<12} {w:.2%}")

    # 4. 判断是否需要生成调仓文件
    need_rebalance = (last_rebalance_date == check_date)

    if not need_rebalance:
        days_to_monday = (7 - check_dt.weekday()) % 7
        if days_to_monday == 0:
            days_to_monday = 7
        next_monday = check_dt + timedelta(days=days_to_monday)
        print(f"\n>>> 今日({check_date})非调仓日，无需操作")
        print(f">>> 下次调仓日: {next_monday.strftime('%Y-%m-%d')} (周一)")
        return

    # 5. 需要调仓，生成同花顺文件
    print(f"\n>>> 今日({check_date})为调仓日，生成同花顺交易流水...")

    prev_shares, prev_cash = replay_history(
        source, rebalance_log, check_date, strategy_name=strategy_name
    )
    is_build = (len(prev_shares) == 0)

    if is_build:
        print(f"  首次建仓（无历史持仓）")
    else:
        print(f"  当前持仓: {len(prev_shares)} 只, 现金 {prev_cash:,.0f}")

    all_codes = list(set(list(prev_shares.keys()) + list(last_holdings.keys())))
    if not all_codes:
        print(f"  目标持仓和当前持仓都为空，无需生成交易文件")
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

    if is_build:
        filename = f"{check_date.replace('-', '')}_build.xlsx"
        label = "建仓"
    else:
        filename = f"{check_date.replace('-', '')}_rebalance.xlsx"
        label = "调仓"

    output_path = output_dir / filename
    write_xlsx(trades, output_path)

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


if __name__ == "__main__":
    main()
