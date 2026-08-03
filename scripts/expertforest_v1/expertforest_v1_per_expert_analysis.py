"""expertForest_v1 每专家深度分析脚本

运行32专家IS, 保存每专家预测+IC, 计算前向IC, 生成每专家分析报告。

输出:
  - output/per_expert_analysis/wf_results.pkl   (每调仓日每专家预测)
  - output/per_expert_analysis/expert_ic_table.csv  (每专家×每调仓日 IC)
  - output/per_expert_analysis/expert_summary.csv    (每专家汇总统计)
  - output/per_expert_analysis/group_analysis.csv    (按维度分组统计)

用法:
    python scripts/expertforest_v1_per_expert_analysis.py
    python scripts/expertforest_v1_per_expert_analysis.py --pool 000905.XSHG --top_n 30
    python scripts/expertforest_v1_per_expert_analysis.py --start 2024-01-01 --end 2025-12-31
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import polars as pl
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ohmyquant.strategy import StrategyRegistry
import os


def main():
    parser = argparse.ArgumentParser(description="expertForest_v1 每专家深度分析")
    parser.add_argument("--pool", default="000905.XSHG", help="股票池指数代码")
    parser.add_argument("--top_n", type=int, default=30, help="选股数量N")
    parser.add_argument("--start", default="2023-01-01", help="IS开始日期")
    parser.add_argument("--end", default="2025-12-31", help="IS结束日期")
    parser.add_argument("--n_jobs", type=int, default=-1, help="每进程CPU核数")
    parser.add_argument("--ensemble", default="rank_average",
                        choices=["equal_weight", "ic_weighted", "rank_average", "ic_rank_weighted"])
    parser.add_argument("--feature_sets", default=None,
                        help="特征集(逗号分隔, 如 momentum,fundamental)")
    parser.add_argument("--train_windows", default=None,
                        help="训练窗口(逗号分隔, 如 252,504)")
    parser.add_argument("--model_types", default=None,
                        help="模型类型(逗号分隔, 如 rf,et,lgb,xgb)")
    parser.add_argument("--output_dir", default="output/per_expert_analysis",
                        help="输出目录")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

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
    if args.train_windows:
        config_override["expert"]["train_windows"] = [int(w) for w in args.train_windows.split(",")]
    if args.model_types:
        config_override["expert"]["model_types"] = args.model_types.split(",")

    print(f"expertForest_v1 每专家深度分析", flush=True)
    print(f"  池子: {args.pool}", flush=True)
    print(f"  Top-N: {args.top_n}", flush=True)
    print(f"  集成: {args.ensemble}", flush=True)
    print(f"  区间: {args.start} → {args.end}", flush=True)
    if args.feature_sets:
        print(f"  特征集: {args.feature_sets}", flush=True)
    if args.train_windows:
        print(f"  训练窗口: {args.train_windows}", flush=True)
    if args.model_types:
        print(f"  模型类型: {args.model_types}", flush=True)
    print(f"  输出: {output_dir}", flush=True)

    # ========== 1. 运行策略 ==========
    t0 = time.time()
    strategy = StrategyRegistry.create("expertForest", "v1", config_override)
    result = strategy.run()
    elapsed = time.time() - t0
    print(f"\n策略运行耗时: {elapsed:.0f}s ({elapsed/60:.1f}min)", flush=True)

    wf_results = result.get("wf_results", [])
    metrics = result.get("metrics", {})
    print(f"调仓日数: {len(wf_results)}", flush=True)
    print(f"IS Sharpe: {metrics.get('sharpe', 'N/A')}", flush=True)

    # ========== 2. 保存wf_results ==========
    wf_path = output_dir / "wf_results.pkl"
    with open(wf_path, "wb") as f:
        pickle.dump(wf_results, f)
    print(f"wf_results已保存: {wf_path}", flush=True)

    # 保存metrics
    metrics_path = output_dir / "metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump({"metrics": metrics, "config": {
            "pool": args.pool, "top_n": args.top_n,
            "start": args.start, "end": args.end,
            "ensemble": args.ensemble,
        }, "elapsed_sec": elapsed}, f, indent=2, ensure_ascii=False, default=str)

    # ========== 3. 重新加载标签(前向5日超额收益) ==========
    print(f"\n加载前向收益标签用于计算forward IC...", flush=True)
    from ohmyquant.data.sources.duckdb_source import DuckDBSource
    from ohmyquant.strategy.strategies.expertForest.v1.factor_engine import FactorEngine

    cfg = strategy.config.model_dump() if hasattr(strategy.config, "model_dump") else strategy.config
    data_root = cfg.get("data", {}).get("data_root", os.getenv("DATA_ROOT", "data"))
    source = DuckDBSource({"data_root": data_root})
    fe = FactorEngine(source, cfg)

    # 获取股票池
    pool_index = cfg.get("pools", {}).get("stocks", {}).get("index", "000300.XSHG")
    if "+" in pool_index:
        pool_codes = set()
        for idx in pool_index.split("+"):
            pool_codes.update(source.load_index_constituents(idx.strip()))
        pool_codes = sorted(pool_codes)
    else:
        pool_codes = sorted(source.load_index_constituents(pool_index))

    data_start = cfg.get("backtest", {}).get("data_start_date", "2021-01-01")
    fetch_end = cfg.get("backtest", {}).get("end_date", "2025-12-31")
    benchmark = cfg.get("walk_forward", {}).get("benchmark", "000300.XSHG")

    price_df = fe._load_price_data(data_start, fetch_end, pool_codes)
    bench_df = source.load_index_data(benchmark, data_start, fetch_end)
    horizon = cfg.get("walk_forward", {}).get("prediction_horizon", 5)
    label_df = fe.compute_labels(price_df, bench_df, horizon)

    # label_df: [date, code, label]  label = fwd_return(t, t+5) - bench_fwd_return(t, t+5)
    label_df = label_df.with_columns(pl.col("date").cast(pl.Date))
    print(f"标签数据: {len(label_df)} 行", flush=True)

    # ========== 4. 计算每专家forward IC ==========
    print(f"\n计算每专家forward IC...", flush=True)

    # 收集所有专家ID
    expert_ids = set()
    for wf in wf_results:
        for ep in wf.get("expert_predictions", []):
            expert_ids.add(ep["expert_id"])
    expert_ids = sorted(expert_ids)
    print(f"专家数: {len(expert_ids)}", flush=True)

    # 按调仓日计算每专家forward IC
    ic_records = []  # [{date, expert_id, holdout_ic, forward_ic, n_codes}]
    for wf in wf_results:
        date_str = wf["date"]
        # 获取该日的真实标签
        try:
            dt = pl.lit(__import__("datetime").datetime.strptime(date_str, "%Y-%m-%d").date())
        except Exception:
            continue

        date_labels = label_df.filter(pl.col("date") == dt)
        if len(date_labels) == 0:
            continue

        label_map = dict(zip(
            date_labels["code"].to_list(),
            date_labels["label"].to_list()
        ))

        for ep in wf.get("expert_predictions", []):
            eid = ep["expert_id"]
            holdout_ic = ep.get("ic", 0.0)
            preds = ep.get("predictions", {})

            # 配对预测和真实标签
            pred_vals = []
            label_vals = []
            for code, pred in preds.items():
                if code in label_map and not np.isnan(pred):
                    lbl = label_map[code]
                    if lbl is not None and not np.isnan(lbl):
                        pred_vals.append(pred)
                        label_vals.append(lbl)

            if len(pred_vals) < 10:
                forward_ic = 0.0
            else:
                ic, _ = spearmanr(pred_vals, label_vals)
                forward_ic = 0.0 if np.isnan(ic) else float(ic)

            ic_records.append({
                "date": date_str,
                "expert_id": eid,
                "holdout_ic": holdout_ic,
                "forward_ic": forward_ic,
                "n_codes": len(pred_vals),
            })

    ic_df = pl.DataFrame(ic_records)
    print(f"IC记录数: {len(ic_df)}", flush=True)
    ic_df.write_csv(output_dir / "expert_ic_table.csv")
    print(f"IC表已保存: {output_dir / 'expert_ic_table.csv'}", flush=True)

    # ========== 5. 每专家汇总统计 ==========
    print(f"\n生成每专家汇总统计...", flush=True)

    summary_records = []
    for eid in expert_ids:
        sub = ic_df.filter(pl.col("expert_id") == eid)
        if len(sub) == 0:
            continue

        fwd_ics = sub["forward_ic"].to_numpy()
        holdout_ics = sub["holdout_ic"].to_numpy()

        # 解析专家ID: {model}_{hyper}_{feature}_w{window}
        parts = eid.split("_")
        model_type = parts[0]
        hyper_set = parts[1]
        feature_set = parts[2]
        train_window = int(parts[3].replace("w", ""))

        summary_records.append({
            "expert_id": eid,
            "model_type": model_type,
            "hyper_set": hyper_set,
            "feature_set": feature_set,
            "train_window": train_window,
            "n_dates": len(sub),
            "forward_ic_mean": float(np.mean(fwd_ics)),
            "forward_ic_std": float(np.std(fwd_ics, ddof=1)),
            "forward_ic_ir": float(np.mean(fwd_ics) / max(np.std(fwd_ics, ddof=1), 1e-8)),
            "forward_ic_positive_rate": float(np.mean(fwd_ics > 0)),
            "forward_ic_max": float(np.max(fwd_ics)),
            "forward_ic_min": float(np.min(fwd_ics)),
            "holdout_ic_mean": float(np.mean(holdout_ics)),
            "holdout_ic_std": float(np.std(holdout_ics, ddof=1)),
            "holdout_ic_ir": float(np.mean(holdout_ics) / max(np.std(holdout_ics, ddof=1), 1e-8)),
        })

    summary_df = pl.DataFrame(summary_records)
    summary_df = summary_df.sort("forward_ic_mean", descending=True)
    summary_df.write_csv(output_dir / "expert_summary.csv")
    print(f"专家汇总已保存: {output_dir / 'expert_summary.csv'}", flush=True)

    # 打印Top/Bottom 5
    print(f"\n{'='*80}", flush=True)
    print(f"Forward IC Top 5 专家:", flush=True)
    print(f"{'='*80}", flush=True)
    top5 = summary_df.head(5)
    for row in top5.iter_rows(named=True):
        print(f"  {row['expert_id']}: fwd_ic={row['forward_ic_mean']:.4f}, "
              f"ir={row['forward_ic_ir']:.3f}, pos_rate={row['forward_ic_positive_rate']:.2f}, "
              f"holdout_ic={row['holdout_ic_mean']:.4f}", flush=True)

    print(f"\nForward IC Bottom 5 专家:", flush=True)
    bot5 = summary_df.tail(5)
    for row in bot5.iter_rows(named=True):
        print(f"  {row['expert_id']}: fwd_ic={row['forward_ic_mean']:.4f}, "
              f"ir={row['forward_ic_ir']:.3f}, pos_rate={row['forward_ic_positive_rate']:.2f}, "
              f"holdout_ic={row['holdout_ic_mean']:.4f}", flush=True)

    # ========== 6. 按维度分组分析 ==========
    print(f"\n生成按维度分组分析...", flush=True)

    group_records = []
    for dim_name in ["model_type", "hyper_set", "feature_set", "train_window"]:
        for group_val in summary_df[dim_name].unique().to_list():
            sub = summary_df.filter(pl.col(dim_name) == group_val)
            group_records.append({
                "dimension": dim_name,
                "group": group_val,
                "n_experts": len(sub),
                "fwd_ic_mean": float(sub["forward_ic_mean"].mean()),
                "fwd_ic_std": float(sub["forward_ic_mean"].std(ddof=1)) if len(sub) > 1 else 0.0,
                "fwd_ic_ir_mean": float(sub["forward_ic_ir"].mean()),
                "fwd_ic_pos_rate_mean": float(sub["forward_ic_positive_rate"].mean()),
                "holdout_ic_mean": float(sub["holdout_ic_mean"].mean()),
            })

    group_df = pl.DataFrame(group_records)
    group_df = group_df.sort(["dimension", "fwd_ic_mean"], descending=[False, True])
    group_df.write_csv(output_dir / "group_analysis.csv")
    print(f"分组分析已保存: {output_dir / 'group_analysis.csv'}", flush=True)

    print(f"\n{'='*80}", flush=True)
    print(f"按维度分组统计:", flush=True)
    print(f"{'='*80}", flush=True)
    for row in group_df.iter_rows(named=True):
        print(f"  [{row['dimension']}] {row['group']:15s}: "
              f"fwd_ic={row['fwd_ic_mean']:.4f}, ir={row['fwd_ic_ir_mean']:.3f}, "
              f"pos_rate={row['fwd_ic_pos_rate_mean']:.2f}, "
              f"holdout_ic={row['holdout_ic_mean']:.4f} "
              f"(n={row['n_experts']})", flush=True)

    # ========== 7. IC时序分析(按月聚合) ==========
    print(f"\n生成IC时序分析...", flush=True)
    ic_df = ic_df.with_columns(
        pl.col("date").str.slice(0, 7).alias("year_month")
    )
    monthly_ic = ic_df.group_by(["year_month", "expert_id"]).agg(
        pl.col("forward_ic").mean().alias("monthly_fwd_ic"),
        pl.col("holdout_ic").mean().alias("monthly_holdout_ic"),
    ).sort(["year_month", "expert_id"])
    monthly_ic.write_csv(output_dir / "monthly_ic.csv")
    print(f"月度IC已保存: {output_dir / 'monthly_ic.csv'}", flush=True)

    # ========== 8. 集成IC vs 策略表现 ==========
    # 按调仓日计算集成forward IC (用selected_codes的composite score vs label)
    print(f"\n计算集成forward IC...", flush=True)
    ensemble_ic_records = []
    for wf in wf_results:
        date_str = wf["date"]
        try:
            dt = pl.lit(__import__("datetime").datetime.strptime(date_str, "%Y-%m-%d").date())
        except Exception:
            continue

        date_labels = label_df.filter(pl.col("date") == dt)
        if len(date_labels) == 0:
            continue
        label_map = dict(zip(
            date_labels["code"].to_list(),
            date_labels["label"].to_list()
        ))

        composite = wf.get("predictions", {})
        pred_vals = []
        label_vals = []
        for code, score in composite.items():
            if code in label_map and not np.isnan(score):
                lbl = label_map[code]
                if lbl is not None and not np.isnan(lbl):
                    pred_vals.append(score)
                    label_vals.append(lbl)

        if len(pred_vals) >= 10:
            ic, _ = spearmanr(pred_vals, label_vals)
            ensemble_ic = 0.0 if np.isnan(ic) else float(ic)
        else:
            ensemble_ic = 0.0

        ensemble_ic_records.append({
            "date": date_str,
            "ensemble_forward_ic": ensemble_ic,
            "n_codes": len(pred_vals),
        })

    ens_ic_df = pl.DataFrame(ensemble_ic_records)
    ens_ic_df.write_csv(output_dir / "ensemble_ic.csv")
    print(f"集成IC已保存: {output_dir / 'ensemble_ic.csv'}", flush=True)

    ens_ics = ens_ic_df["ensemble_forward_ic"].to_numpy()
    print(f"\n集成forward IC统计:", flush=True)
    print(f"  均值: {np.mean(ens_ics):.4f}", flush=True)
    print(f"  标准差: {np.std(ens_ics, ddof=1):.4f}", flush=True)
    print(f"  IR: {np.mean(ens_ics)/max(np.std(ens_ics, ddof=1), 1e-8):.3f}", flush=True)
    print(f"  正率: {np.mean(ens_ics > 0):.2f}", flush=True)

    print(f"\n{'='*80}", flush=True)
    print(f"分析完成! 所有结果保存至: {output_dir}", flush=True)
    print(f"{'='*80}", flush=True)


if __name__ == "__main__":
    main()
