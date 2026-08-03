"""批量重新生成全部 OOS 同花顺交易文件

运行一次 OOS 回测，遍历所有调仓日，逐个生成同花顺交易流水文件。
比逐日运行 industry_rotation_daily.py 快 7 倍（1 次回测 vs 7 次回测）。

用法:
    python scripts/regenerate_ths_files.py                    # 默认 v53
    python scripts/regenerate_ths_files.py --version v63      # 指定 v63
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# 复用 daily 脚本的全部函数
from industry_rotation_daily import (
    generate_trades,
    get_open_prices,
    replay_history,
    run_oos_backtest,
    write_xlsx,
)
from ohmyquant.data.sources.duckdb_source import DuckDBSource

DATA_ROOT = "D:/Work/Project/download_a_share/data"

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="v53", help="策略版本(默认 v53)")
    args = parser.parse_args()
    version = args.version

    output_dir = Path(f"output/ths/industry_rotation_{version}")

    source = DuckDBSource({"data_root": DATA_ROOT})

    # 动态获取最新数据日期作为回测终止日
    oos_end = source.get_latest_date()
    print(f"运行 OOS 回测: {version} → {oos_end}")
    result = run_oos_backtest(oos_end, version=version)
    rebalance_log = result["rebalance_log"]

    print(f"\n调仓日数量: {len(rebalance_log)}")
    print(f"{'日期':<12} {'类型':<6} {'买':<4} {'卖':<4} {'持仓':<4} {'现金':>12}")
    print("-" * 50)

    # 清空输出目录
    if output_dir.exists():
        for f in output_dir.glob("*.xlsx"):
            f.unlink()
    output_dir.mkdir(parents=True, exist_ok=True)

    for i, entry in enumerate(rebalance_log):
        date_str = entry["date"]
        holdings = entry["holdings"]

        # 回放历史重建持仓状态
        prev_shares, prev_cash = replay_history(source, rebalance_log, date_str)
        is_build = (len(prev_shares) == 0)

        # 获取所有股票开盘价（当前持仓 + 目标持仓）
        all_codes = list(set(list(prev_shares.keys()) + list(holdings.keys())))
        open_prices = get_open_prices(source, all_codes, date_str)

        trades, new_shares, new_cash = generate_trades(
            date_str, prev_shares, holdings, open_prices, prev_cash, is_build
        )

        if i == 0:
            filename = f"{date_str.replace('-', '')}_build.xlsx"
        else:
            filename = f"{date_str.replace('-', '')}_rebalance.xlsx"
        output_path = output_dir / filename
        write_xlsx(trades, output_path)

        buy_count = sum(1 for t in trades if t["业务类型"] == "买入")
        sell_count = sum(1 for t in trades if t["业务类型"] == "卖出")
        label = "建仓" if i == 0 else "调仓"
        if not trades:
            print(f"{date_str:<12} {label:<6} {buy_count:<4} {sell_count:<4} {len(new_shares):<4} {new_cash:>12,.0f}  (维持空仓)")
        else:
            print(f"{date_str:<12} {label:<6} {buy_count:<4} {sell_count:<4} {len(new_shares):<4} {new_cash:>12,.0f}")

    print(f"\n文件已生成到: {output_dir}")
    files = sorted(output_dir.glob("*.xlsx"))
    print(f"共 {len(files)} 个文件:")
    for f in files:
        print(f"  {f.name}")


if __name__ == "__main__":
    main()
