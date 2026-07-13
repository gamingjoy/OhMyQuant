"""optimization 模块功能烟雾测试

验证 StrategyEnsemble + StrategyWalkForward + ParamSearcher（网格降级）可用。
为控制耗时，使用短区间（2024 年）与小窗口。
"""
from __future__ import annotations

import sys
import time

from ohmyquant.data.base import DataCatalog
from ohmyquant.data.sources.duckdb_source import DuckDBSource
from ohmyquant.optimization import (
    ParamSearcher,
    StrategyEnsemble,
    StrategyWalkForward,
)


def main():
    print("=" * 70)
    print("optimization 模块功能烟雾测试")
    print("=" * 70)

    source = DuckDBSource({"data_root": "D:/Work/Project/download_a_share/data"})
    catalog = DataCatalog(source)
    hs300 = catalog.get_index_constituents("000300.SH")

    base_overrides = {
        "pools": {"main": hs300},
        "backtest": {
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "data_start_date": "2022-01-01",
        },
    }

    # ---- 1. StrategyEnsemble ----
    print("\n[1] StrategyEnsemble (ycj v1 + etf v1, perf_weight)")
    t0 = time.time()
    try:
        ens = StrategyEnsemble(weighting="perf_weight")
        ens.add_strategy("ycj", "v1")
        ens.add_strategy("etf", "v1")
        result = ens.run(config_overrides=base_overrides)
        elapsed = time.time() - t0
        print(f"    耗时 {elapsed:.1f}s")
        print(f"    集成天数:   {len(result.dates)}")
        print(f"    集成净值末值: {result.nav[-1]:.4f}")
        print(f"    集成 Sharpe:  {result.metrics.sharpe_ratio:.4f}")
        print(f"    成分权重:")
        for c in result.constituents:
            print(f"      {c['strategy_type']} {c['version']}: w={c['weight']:.3f} sharpe={c['sharpe']:.4f}")
        print("    [PASS] StrategyEnsemble 跑通")
    except Exception as e:
        print(f"    [FAIL] StrategyEnsemble 失败: {e}")
        import traceback
        traceback.print_exc()

    # ---- 2. StrategyWalkForward ----
    print("\n[2] StrategyWalkForward (ycj v1, test_window=6M, step=6M)")
    t0 = time.time()
    try:
        wf = StrategyWalkForward(test_window="6M", step="6M")
        # 用 2023-2024 全程拿日期，再切 6M 窗口
        wf_overrides = {
            "pools": {"main": hs300},
            "backtest": {
                "start_date": "2023-01-01",
                "end_date": "2024-12-31",
                "data_start_date": "2020-01-01",
            },
        }
        report = wf.run("ycj", "v1", base_overrides=wf_overrides)
        elapsed = time.time() - t0
        print(f"    耗时 {elapsed:.1f}s")
        print(f"    窗口数:       {len(report.windows)}")
        print(f"    平均 Sharpe:  {report.mean_sharpe:.4f}")
        print(f"    一致性:       {report.consistency:.1%} ({report.positive_windows}/{len(report.windows)})")
        print("    [PASS] StrategyWalkForward 跑通")
    except Exception as e:
        print(f"    [FAIL] StrategyWalkForward 失败: {e}")
        import traceback
        traceback.print_exc()

    # ---- 3. ParamSearcher（网格降级）----
    print("\n[3] ParamSearcher (网格降级, n_trials=2)")
    t0 = time.time()
    try:
        ps = ParamSearcher(n_trials=2, metric="sharpe", direction="maximize")
        report = ps.search(
            "ycj", "v1",
            {
                "selection.top_n": {"type": "int", "low": 30, "high": 50, "step": 20},
            },
        )
        elapsed = time.time() - t0
        print(f"    耗时 {elapsed:.1f}s")
        print(f"    后端:         {report.backend}")
        print(f"    试验数:       {report.n_trials}")
        print(f"    最优值:       {report.best_value:.4f}")
        print(f"    最优参数:     {report.best_params}")
        print("    [PASS] ParamSearcher 跑通")
    except Exception as e:
        print(f"    [FAIL] ParamSearcher 失败: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 70)
    print("optimization 烟雾测试完成")
    print("=" * 70)


if __name__ == "__main__":
    main()
