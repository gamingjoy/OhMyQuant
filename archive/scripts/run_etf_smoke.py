"""ETF v1 轮动策略烟雾测试

验证 ETF 策略全流程：ETF 池加载 → 动量因子 → ICIR 选 Top-3 → 月度调仓 → etf_cn 成本模型
"""
from __future__ import annotations

import sys
import time

import numpy as np

from ohmyquant.strategy.runner import StrategyRunner


def main():
    print("=" * 70)
    print("ETF v1 动量轮动策略 烟雾测试")
    print("=" * 70)

    config_overrides = {
        "backtest": {
            "start_date": "2023-01-01",
            "end_date": "2024-12-31",
            "data_start_date": "2020-01-01",
        },
    }

    print("\n[1] 启动 etf v1 策略回测...")
    print(f"    回测区间: 2023-01-01 ~ 2024-12-31")
    t0 = time.time()

    try:
        result = StrategyRunner.run_strategy("etf", "v1", config_overrides)
        elapsed = time.time() - t0
        print(f"\n[2] 策略执行完成（耗时 {elapsed:.1f}s）")

        bt = result.backtest_result
        print("\n" + "=" * 70)
        print("回测结果摘要")
        print("=" * 70)
        print(f"  回测天数:     {bt.n_days}")
        print(f"  最终净值:     {bt.final_nav:.4f}")
        print(f"  NAV[0]:       {bt.nav[0]:.6f}")

        if len(bt.daily_returns) > 0:
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
        rebalance_dates = list(bt.stock_weights_by_date.keys())
        print(f"  调仓日数量:   {len(rebalance_dates)}")

        # 验证成本模型与 NAV 一致性
        nav0_ok = abs(bt.nav[0] - 1.0) < 1e-6
        print(f"\n  NAV[0] == 1.0:    {'PASS' if nav0_ok else 'FAIL'} ({bt.nav[0]:.6f})")
        print(f"  调仓日志非空:     {'PASS' if len(bt.pool_weight_log) > 0 else 'FAIL'}")

        print("\n" + "=" * 70)
        print("ETF 烟雾测试完成 - 全流程跑通")
        print("=" * 70)

    except Exception as e:
        elapsed = time.time() - t0
        print(f"\n[ERROR] 策略执行失败（耗时 {elapsed:.1f}s）")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
