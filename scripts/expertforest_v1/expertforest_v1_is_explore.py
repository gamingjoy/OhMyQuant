"""expertForest_v1 IS 验证脚本

运行Walk Forward回测，验证多专家树集成策略效果。

用法:
    python scripts/expertforest_v1_is_explore.py                    # 默认沪深300, N=10
    python scripts/expertforest_v1_is_explore.py --pool 000905.XSHG  # 中证500
    python scripts/expertforest_v1_is_explore.py --top_n 15           # N=15
    python scripts/expertforest_v1_is_explore.py --smoke              # 快速冒烟测试(2个月)
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
    parser = argparse.ArgumentParser(description="expertForest_v1 IS验证")
    parser.add_argument("--pool", default="000300.XSHG", help="股票池指数代码")
    parser.add_argument("--top_n", type=int, default=10, help="选股数量N")
    parser.add_argument("--smoke", action="store_true", help="冒烟测试(短区间)")
    parser.add_argument("--fast", action="store_true", help="快速模式(仅conservative, 2模型, 8专家)")
    parser.add_argument("--start", default="2023-01-01", help="IS开始日期")
    parser.add_argument("--end", default="2025-12-31", help="IS结束日期")
    parser.add_argument("--n_jobs", type=int, default=-1, help="每进程CPU核数(-1=全部, 并行时设8)")
    parser.add_argument("--ensemble", default="equal_weight",
                        choices=["equal_weight", "ic_weighted", "rank_average", "ic_rank_weighted"],
                        help="集成方法")
    parser.add_argument("--feature_sets", default=None,
                        help="特征集(逗号分隔, 如 momentum,fundamental,combined)")
    parser.add_argument("--hyper_sets", default=None,
                        help="超参组合(逗号分隔, 如 conservative,moderate). 默认全部")
    args = parser.parse_args()

    if args.smoke:
        args.start = "2024-01-01"
        args.end = "2024-02-28"

    # 构建配置覆盖
    config_override = {
        "pools": {"stocks": {"index": args.pool}},
        "selection": {"top_n": args.top_n},
        "backtest": {
            "start_date": args.start,
            "end_date": args.end,
            "data_start_date": "2021-01-01",
        },
        "expert": {"n_jobs": args.n_jobs},
        "ensemble": {"method": args.ensemble},
    }

    if args.feature_sets:
        config_override["expert"]["feature_sets"] = args.feature_sets.split(",")

    if args.hyper_sets:
        config_override["expert"]["hyper_sets"] = args.hyper_sets.split(",")

    if args.fast:
        config_override["expert"] = {
            "model_types": ["rf", "lgb"],
            "hyper_sets": ["conservative"],
            "feature_sets": args.feature_sets.split(",") if args.feature_sets else ["momentum", "fundamental"],
            "train_windows": [252],
            "n_jobs": args.n_jobs,
        }

    print(f"expertForest_v1 IS验证", flush=True)
    print(f"  池子: {args.pool}", flush=True)
    print(f"  Top-N: {args.top_n}", flush=True)
    print(f"  n_jobs: {args.n_jobs}", flush=True)
    print(f"  集成: {args.ensemble}", flush=True)
    print(f"  区间: {args.start} → {args.end}", flush=True)
    if args.smoke:
        print(f"  冒烟测试模式", flush=True)
    if args.fast:
        print(f"  快速模式: 2模型×1超参×2特征×1窗口 = 4专家", flush=True)

    # 创建并运行策略
    t0 = time.time()
    strategy = StrategyRegistry.create("expertForest", "v1", config_override)
    result = strategy.run()
    elapsed = time.time() - t0

    print(f"\n总耗时: {elapsed:.0f}s ({elapsed/60:.1f}min)")

    # 保存结果
    output_dir = Path("output/is_compare/expertforest_v1")
    output_dir.mkdir(parents=True, exist_ok=True)
    pool_name = args.pool.replace(".", "_").replace("+", "plus")
    # 文件名包含集成方法/特征集/超参组合, 避免覆盖
    ens_tag = args.ensemble
    fs_tag = "+".join(args.feature_sets.split(",")) if args.feature_sets else "default"
    hs_tag = "+".join(args.hyper_sets.split(",")) if args.hyper_sets else "all"
    output_file = output_dir / f"expertforest_v1_{pool_name}_n{args.top_n}_{ens_tag}_{fs_tag}_{hs_tag}.json"

    save_data = {
        "config": {
            "pool": args.pool,
            "top_n": args.top_n,
            "start": args.start,
            "end": args.end,
            "smoke": args.smoke,
            "ensemble": args.ensemble,
            "feature_sets": args.feature_sets,
            "hyper_sets": args.hyper_sets,
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
