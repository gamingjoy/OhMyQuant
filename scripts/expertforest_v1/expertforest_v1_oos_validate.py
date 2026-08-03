"""expertForest_v1 OOS验证脚本

在IS对比选出最优池子+N值后, 用OOS数据(20260601+)验证策略表现。

用法:
    python scripts/expertforest_v1_oos_validate.py --pool 000300.XSHG --top_n 10
    python scripts/expertforest_v1_oos_validate.py --pool 000905.XSHG --top_n 15
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ohmyquant.strategy import StrategyRegistry


def main():
    parser = argparse.ArgumentParser(description="expertForest_v1 OOS验证")
    parser.add_argument("--pool", default="000905.XSHG", help="股票池指数代码")
    parser.add_argument("--top_n", type=int, default=30, help="选股数量N")
    parser.add_argument("--n_jobs", type=int, default=32, help="CPU核数(-1=全部)")
    parser.add_argument("--ensemble", default="rank_average",
                        choices=["equal_weight", "ic_weighted", "rank_average", "ic_rank_weighted"],
                        help="集成方法")
    parser.add_argument("--hyper_sets", default=None,
                        help="超参组合(逗号分隔, 如 conservative,moderate). 默认全部")
    parser.add_argument("--feature_sets", default=None,
                        help="特征集(逗号分隔, 如 momentum,fundamental,sentiment). 默认全部")
    parser.add_argument("--model_types", default=None,
                        help="模型类型(逗号分隔, 如 rf,et,lgb,xgb). 默认全部")
    parser.add_argument("--train_windows", default=None,
                        help="训练窗口(逗号分隔, 如 252,504). 默认全部")
    args = parser.parse_args()

    # OOS: 20260601及以后
    oos_start = "2026-06-01"
    oos_end = "2026-12-31"
    # 训练数据需覆盖504日窗口(~2年), OOS首调仓日2026-06-01回溯504日≈2024-06-01
    # 取2024-01-01确保双窗口(252/504)专家在OOS期均有充足训练数据
    data_start = "2024-01-01"

    config_override = {
        "pools": {"stocks": {"index": args.pool}},
        "selection": {"top_n": args.top_n},
        "backtest": {
            "start_date": oos_start,
            "end_date": oos_end,
            "data_start_date": data_start,
        },
        "expert": {"n_jobs": args.n_jobs},
        "ensemble": {"method": args.ensemble},
    }

    if args.hyper_sets:
        config_override["expert"]["hyper_sets"] = args.hyper_sets.split(",")

    if args.feature_sets:
        config_override["expert"]["feature_sets"] = args.feature_sets.split(",")

    if args.model_types:
        config_override["expert"]["model_types"] = args.model_types.split(",")

    if args.train_windows:
        config_override["expert"]["train_windows"] = [int(w) for w in args.train_windows.split(",")]

    print(f"expertForest_v1 OOS验证", flush=True)
    print(f"  池子: {args.pool}", flush=True)
    print(f"  Top-N: {args.top_n}", flush=True)
    print(f"  集成: {args.ensemble}", flush=True)
    print(f"  超参: {args.hyper_sets or 'all'}", flush=True)
    print(f"  特征集: {args.feature_sets or 'all'}", flush=True)
    print(f"  模型: {args.model_types or 'all'}", flush=True)
    print(f"  训练窗口: {args.train_windows or 'all'}", flush=True)
    print(f"  n_jobs: {args.n_jobs}", flush=True)
    print(f"  OOS区间: {oos_start} → {oos_end}", flush=True)

    t0 = time.time()
    strategy = StrategyRegistry.create("expertForest", "v1", config_override)
    result = strategy.run()
    elapsed = time.time() - t0

    print(f"\n总耗时: {elapsed:.0f}s ({elapsed/60:.1f}min)")

    # 保存结果
    output_dir = Path("output/oos_validate/expertforest_v1")
    output_dir.mkdir(parents=True, exist_ok=True)
    pool_name = args.pool.replace(".", "_").replace("+", "plus")
    hs_tag = "+".join(args.hyper_sets.split(",")) if args.hyper_sets else "all"
    fs_tag = "+".join(args.feature_sets.split(",")) if args.feature_sets else "all"
    mt_tag = "+".join(args.model_types.split(",")) if args.model_types else "all"
    tw_tag = "+".join(args.train_windows.split(",")) if args.train_windows else "all"
    output_file = output_dir / f"expertforest_v1_{pool_name}_n{args.top_n}_{args.ensemble}_hs{hs_tag}_fs{fs_tag}_mt{mt_tag}_tw{tw_tag}_oos.json"

    save_data = {
        "config": {
            "pool": args.pool,
            "top_n": args.top_n,
            "start": oos_start,
            "end": oos_end,
            "ensemble": args.ensemble,
            "hyper_sets": args.hyper_sets,
            "feature_sets": args.feature_sets,
            "model_types": args.model_types,
            "train_windows": args.train_windows,
        },
        "metrics": result.get("metrics", {}),
        "n_rebalance": len(result.get("holdings_log", [])),
        "elapsed_sec": elapsed,
    }
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(save_data, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n结果已保存: {output_file}")


if __name__ == "__main__":
    main()
