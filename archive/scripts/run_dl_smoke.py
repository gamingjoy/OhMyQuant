"""DL/LSTM 烟雾测试

验证 ModelSelector + LSTM 全流程：
蓝筹股池 → 因子计算 → 强因子筛选 → LSTM 训练/推理 → 选股 → 回测

依赖: torch（PyTorch）
若 torch 未装，脚本优雅退出并提示。

注意: LSTM 训练较慢，本测试使用小 epochs + 短回测区间。
"""
from __future__ import annotations

import sys
import time

import numpy as np

from ohmyquant.strategy.runner import StrategyRunner


def main():
    print("=" * 70)
    print("DL/ModelSelector (lstm) 烟雾测试")
    print("=" * 70)

    # 检查 torch
    try:
        import torch  # noqa: F401
        print(f"    torch 可用")
    except ImportError:
        print("[SKIP] torch 未安装，跳过 DL 烟雾测试")
        print("       安装: pip install torch")
        sys.exit(0)

    # 配置：使用 dl/v1 策略，缩短回测区间 + 减小 epochs
    config_overrides = {
        "backtest": {
            "start_date": "2023-06-01",
            "end_date": "2024-06-30",
            "data_start_date": "2020-01-01",
        },
        "selection": {
            "method": "model",
            "model_name": "lstm",
            "model": {
                "hidden_dim": 32,
                "num_layers": 1,
                "dropout": 0.0,
                "epochs": 5,
                "batch_size": 128,
                "learning_rate": 0.005,
                "patience": 5,
                "device": "cpu",
            },
            "ml": {
                "train_window": 126,
                "target_horizon": 10,
                "sample_step": 5,
                "retrain_freq": 21,
            },
            "top_n": 5,
            "max_stock_weight": 0.2,
        },
        "portfolio": {
            "max_stock_weight": 0.2,
        },
    }

    print("\n[1] 启动 dl v1 + LSTM 选股器回测...")
    print(f"    选股方法: model (lstm)")
    print(f"    回测区间: {config_overrides['backtest']['start_date']} → {config_overrides['backtest']['end_date']}")
    print(f"    LSTM 参数: epochs=5, hidden_dim=32, device=cpu")
    t0 = time.time()

    try:
        result = StrategyRunner.run_strategy("dl", "v1", config_overrides)
        elapsed = time.time() - t0
        print(f"\n[2] 策略执行完成（耗时 {elapsed:.1f}s）")

        bt = result.backtest_result
        print("\n" + "=" * 70)
        print("回测结果摘要")
        print("=" * 70)
        print(f"  回测天数:     {bt.n_days}")
        print(f"  最终净值:     {bt.final_nav:.4f}")

        if len(bt.daily_returns) > 0:
            returns = bt.daily_returns.to_numpy()
            returns = returns[~np.isnan(returns)]
            if len(returns) > 0:
                ann_ret = float(np.mean(returns) * 242)
                ann_vol = float(np.std(returns) * np.sqrt(242))
                sharpe = ann_ret / ann_vol if ann_vol > 0 else 0
                print(f"  年化收益:     {ann_ret:.2%}")
                print(f"  年化波动:     {ann_vol:.2%}")
                print(f"  夏普比率:     {sharpe:.4f}")

        rebalance_dates = list(bt.stock_weights_by_date.keys())
        print(f"  调仓日数量:   {len(rebalance_dates)}")

        nav0_ok = abs(bt.nav[0] - 1.0) < 1e-6
        print(f"\n  NAV[0] == 1.0:    {'PASS' if nav0_ok else 'FAIL'}")
        print(f"  调仓日 > 0:       {'PASS' if len(rebalance_dates) > 0 else 'FAIL'}")

        if len(rebalance_dates) > 0:
            last_date = rebalance_dates[-1]
            last_weights = bt.stock_weights_by_date[last_date]
            print(f"  最后调仓日:       {last_date}")
            print(f"  最后持仓数:       {len(last_weights)}")
            if last_weights:
                top3 = sorted(last_weights.items(), key=lambda x: -x[1])[:3]
                print(f"  Top-3 持仓:       {top3}")

        print("\n" + "=" * 70)
        print("DL 烟雾测试完成 - ModelSelector + LSTM 全流程跑通")
        print("=" * 70)

    except Exception as e:
        elapsed = time.time() - t0
        print(f"\n[ERROR] 策略执行失败（耗时 {elapsed:.1f}s）")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
