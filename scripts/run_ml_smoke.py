"""ML/ModelSelector 烟雾测试

验证 ModelSelector + LightGBM 全流程：
HS300 池 → 因子计算 → 强因子筛选 → LightGBM LTR 训练/推理 → 选股 → 回测

依赖: lightgbm（已确认 4.6.0 安装）
若 lightgbm 未装，脚本优雅退出并提示。
"""
from __future__ import annotations

import sys
import time

import numpy as np

from ohmyquant.data.base import DataCatalog
from ohmyquant.data.sources.duckdb_source import DuckDBSource
from ohmyquant.strategy.runner import StrategyRunner


def main():
    print("=" * 70)
    print("ML/ModelSelector (lightgbm_ltr) 烟雾测试")
    print("=" * 70)

    # 检查 lightgbm
    try:
        import lightgbm  # noqa: F401
        print(f"    lightgbm 可用")
    except ImportError:
        print("[SKIP] lightgbm 未安装，跳过 ML 烟雾测试")
        sys.exit(0)

    # 1. 加载 HS300 池
    print("\n[1] 加载沪深300成分股...")
    source = DuckDBSource({"data_root": "D:/Work/Project/download_a_share/data"})
    catalog = DataCatalog(source)
    hs300 = catalog.get_index_constituents("000300.SH")
    print(f"    沪深300成分股: {len(hs300)} 只")

    # 2. 配置：selection.method=model, model_name=lightgbm_ltr
    config_overrides = {
        "pools": {"main": hs300},
        "backtest": {
            "start_date": "2023-01-01",
            "end_date": "2024-12-31",
            "data_start_date": "2020-01-01",
        },
        "selection": {
            "method": "model",
            "model_name": "lightgbm_ltr",
            "model": {"n_estimators": 100, "max_depth": 3},
            "top_n": 50,
            "max_stock_weight": 0.02,
            "ml": {"train_window": 252, "target_horizon": 20, "sample_step": 5, "retrain_freq": 21},
        },
    }

    print("\n[2] 启动 ycj v1 + model 选股器回测...")
    print(f"    选股方法: model (lightgbm_ltr)")
    t0 = time.time()

    try:
        result = StrategyRunner.run_strategy("ycj", "v1", config_overrides)
        elapsed = time.time() - t0
        print(f"\n[3] 策略执行完成（耗时 {elapsed:.1f}s）")

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
                print(f"  年化收益:     {ann_ret:.2%}")
                print(f"  年化波动:     {ann_vol:.2%}")
                print(f"  夏普比率:     {sharpe:.4f}")

        rebalance_dates = list(bt.stock_weights_by_date.keys())
        print(f"  调仓日数量:   {len(rebalance_dates)}")

        nav0_ok = abs(bt.nav[0] - 1.0) < 1e-6
        print(f"\n  NAV[0] == 1.0:    {'PASS' if nav0_ok else 'FAIL'}")
        print(f"  调仓日 > 0:       {'PASS' if len(rebalance_dates) > 0 else 'FAIL'}")

        print("\n" + "=" * 70)
        print("ML 烟雾测试完成 - ModelSelector + LightGBM 全流程跑通")
        print("=" * 70)

    except Exception as e:
        elapsed = time.time() - t0
        print(f"\n[ERROR] 策略执行失败（耗时 {elapsed:.1f}s）")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
