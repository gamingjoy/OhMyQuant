"""YCJ 策略全流程试运行脚本

使用沪深300成分股作为股票池，缩短回测区间验证全流程：
数据加载 → 因子计算 → IC分析 → 选股 → 回测 → 绩效指标
"""
from __future__ import annotations

import sys
import time

from ohmyquant.data.base import DataCatalog
from ohmyquant.data.sources.duckdb_source import DuckDBSource
from ohmyquant.strategy.runner import StrategyRunner


def main():
    print("=" * 70)
    print("YCJ 策略全流程试运行")
    print("=" * 70)

    # 1. 加载沪深300成分股作为股票池
    print("\n[1] 加载沪深300成分股...")
    source = DuckDBSource({"data_root": "D:/Work/Project/download_a_share/data"})
    catalog = DataCatalog(source)
    hs300 = catalog.get_index_constituents("000300.SH")
    print(f"    沪深300成分股: {len(hs300)} 只")

    if len(hs300) < 50:
        print("    WARNING: 成分股数量不足，可能影响强因子筛选")

    # 2. 配置覆盖：指定股票池 + 缩短回测区间
    config_overrides = {
        "pools": {"main": hs300},
        "backtest": {
            "start_date": "2023-01-01",
            "end_date": "2024-12-31",
            "data_start_date": "2020-01-01",
        },
    }

    # 3. 运行 ycj v1 策略
    print("\n[2] 启动 ycj v1 策略回测...")
    print(f"    回测区间: 2023-01-01 ~ 2024-12-31")
    print(f"    数据起始: 2020-01-01（预热3年）")
    t0 = time.time()

    try:
        result = StrategyRunner.run_strategy("ycj", "v1", config_overrides)
        elapsed = time.time() - t0
        print(f"\n[3] 策略执行完成（耗时 {elapsed:.1f}s）")

        # 4. 打印关键指标
        bt = result.backtest_result
        print("\n" + "=" * 70)
        print("回测结果摘要")
        print("=" * 70)
        print(f"  回测天数:     {bt.n_days}")
        print(f"  最终净值:     {bt.final_nav:.4f}")
        print(f"  NAV[0]:       {bt.nav[0]:.6f}")

        if len(bt.daily_returns) > 0:
            import numpy as np
            returns = bt.daily_returns.to_numpy()
            returns = returns[~np.isnan(returns)]
            if len(returns) > 0:
                ann_ret = float(np.mean(returns) * 242)
                ann_vol = float(np.std(returns) * np.sqrt(242))
                sharpe = ann_ret / ann_vol if ann_vol > 0 else 0
                nav_arr = bt.nav.to_numpy()
                peak = np.maximum.accumulate(nav_arr)
                drawdown = (nav_arr - peak) / peak
                max_dd = float(np.min(drawdown))
                print(f"  年化收益:     {ann_ret:.2%}")
                print(f"  年化波动:     {ann_vol:.2%}")
                print(f"  夏普比率:     {sharpe:.4f}")
                print(f"  最大回撤:     {max_dd:.2%}")

        print(f"  调仓日志数:   {len(bt.pool_weight_log)}")
        print(f"  暴露度日志:   {len(bt.exposure_log)}")

        # 5. 打印调仓日数量
        rebalance_dates = list(bt.stock_weights_by_date.keys())
        print(f"  调仓日数量:   {len(rebalance_dates)}")
        if rebalance_dates:
            print(f"  首次调仓:     {rebalance_dates[0]}")
            print(f"  末次调仓:     {rebalance_dates[-1]}")

        # 6. 验证 NAV 一致性
        print("\n" + "=" * 70)
        print("NAV 一致性检查")
        print("=" * 70)
        nav0_ok = abs(bt.nav[0] - 1.0) < 1e-6
        len_ok = len(bt.daily_returns) == len(bt.dates) - 1
        cum_ret = float(bt.nav[-1] / bt.nav[0]) - 1
        print(f"  NAV[0] == 1.0:        {'PASS' if nav0_ok else 'FAIL'} ({bt.nav[0]:.6f})")
        print(f"  len(returns)==len-1:  {'PASS' if len_ok else 'FAIL'} ({len(bt.daily_returns)} vs {len(bt.dates)-1})")
        print(f"  累计收益:             {cum_ret:.2%}")
        print(f"  final_nav-1:          {bt.final_nav - 1:.2%}")

        print("\n" + "=" * 70)
        print("试运行完成 - 全流程跑通")
        print("=" * 70)

    except Exception as e:
        elapsed = time.time() - t0
        print(f"\n[ERROR] 策略执行失败（耗时 {elapsed:.1f}s）")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
