"""批量计算260+因子的IC，筛选有效因子

计算逻辑：
  - rank IC（Spearman相关）：因子排名 vs N日前向收益率排名
  - IC均值：>0.03 为有效
  - ICIR（IC均值/IC标准差）：>0.5 为稳定

用法:
    python scripts/factor_ic_screening.py              # 默认5日
    python scripts/factor_ic_screening.py --horizon 20 # 20日horizon
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import polars as pl
import duckdb

DATA_ROOT = "D:/Work/Project/download_a_share/data"
POOL_INDEX = "000300.XSHG"
IS_START = "2022-01-01"
IS_END = "2025-12-31"


def load_factors_and_returns(forward_days: int):
    """加载因子数据和前向收益率"""
    t0 = time.time()
    con = duckdb.connect()

    # 1. 获取沪深300成分股
    print(">> 加载沪深300成分股...", flush=True)
    constituents = con.execute(f"""
        SELECT DISTINCT code FROM read_parquet('{DATA_ROOT}/parquet/index_constituents/**/*.parquet')
        WHERE index_code = '{POOL_INDEX}'
    """).fetchall()
    stock_codes = [r[0] for r in constituents]
    print(f"   成分股: {len(stock_codes)} 只", flush=True)

    # 创建临时表
    codes_df = pl.DataFrame({"code": stock_codes})
    con.register("stock_codes", codes_df)

    # 2. 加载因子数据
    print(">> 加载因子数据...", flush=True)
    factors_df = con.execute(f"""
        SELECT f.* FROM read_parquet('{DATA_ROOT}/parquet/factors_wide/**/*.parquet') f
        JOIN stock_codes s ON f.code = s.code
        WHERE f.date >= '{IS_START}' AND f.date <= '{IS_END}'
    """).pl()
    print(f"   因子数据: {factors_df.shape}", flush=True)

    # 3. 加载收盘价计算前向收益
    print(">> 加载收盘价...", flush=True)
    close_df = con.execute(f"""
        SELECT d.date, d.code, d.close FROM read_parquet('{DATA_ROOT}/stock_daily_wide_partitioned/**/*.parquet') d
        JOIN stock_codes s ON d.code = s.code
        WHERE d.date >= '{IS_START}' AND d.date <= '{IS_END}'
    """).pl()
    print(f"   价格数据: {close_df.shape}", flush=True)

    # 4. 计算前向收益
    print(f">> 计算{forward_days}日前向收益...", flush=True)
    close_df = close_df.sort(["code", "date"])
    close_df = close_df.with_columns(
        pl.col("close").shift(-forward_days).over("code").alias("future_close")
    )
    close_df = close_df.with_columns(
        (pl.col("future_close") / pl.col("close") - 1.0).alias("forward_return")
    )
    close_df = close_df.drop_nulls(subset=["forward_return"])

    # 5. 合并因子和收益
    print(">> 合并因子和收益...", flush=True)
    factor_cols = [c for c in factors_df.columns if c not in ("date", "code")]
    print(f"   因子数: {len(factor_cols)}", flush=True)

    # 统一date类型
    factors_df = factors_df.with_columns(pl.col("date").cast(pl.Date))
    close_df = close_df.with_columns(pl.col("date").cast(pl.Date))

    merged = factors_df.join(close_df.select(["date", "code", "forward_return"]), on=["date", "code"], how="inner")
    print(f"   合并后: {merged.shape}", flush=True)

    elapsed = time.time() - t0
    print(f"   数据加载完成 ({elapsed:.0f}s)\n", flush=True)

    return merged, factor_cols


def compute_rank_ic(df: pl.DataFrame, factor_name: str) -> dict:
    """计算单个因子的rank IC"""
    sub = df.select([factor_name, "forward_return", "date"]).drop_nulls()
    if len(sub) < 100:
        return {"factor": factor_name, "mean_ic": 0.0, "ic_std": 0.0, "icir": 0.0, "n_days": 0}

    # 按日期分组计算rank IC
    ic_list = []
    for (date,), group in sub.group_by(["date"]):
        if len(group) < 10:
            continue
        vals = group.select([factor_name, "forward_return"]).to_numpy()
        if np.std(vals[:, 0]) == 0 or np.std(vals[:, 1]) == 0:
            continue
        # Spearman rank correlation
        from scipy.stats import spearmanr
        ic, _ = spearmanr(vals[:, 0], vals[:, 1])
        if not np.isnan(ic):
            ic_list.append(ic)

    if len(ic_list) < 10:
        return {"factor": factor_name, "mean_ic": 0.0, "ic_std": 0.0, "icir": 0.0, "n_days": len(ic_list)}

    ic_arr = np.array(ic_list)
    mean_ic = float(np.mean(ic_arr))
    ic_std = float(np.std(ic_arr, ddof=1))
    icir = mean_ic / ic_std if ic_std > 0 else 0.0

    return {
        "factor": factor_name,
        "mean_ic": mean_ic,
        "ic_std": ic_std,
        "icir": icir,
        "n_days": len(ic_list),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=5, help="前向收益天数")
    args = parser.parse_args()
    forward_days = args.horizon

    print("=" * 80, flush=True)
    print(f"因子IC筛选：{IS_START} ~ {IS_END}，沪深300，{forward_days}日horizon", flush=True)
    print("=" * 80, flush=True)

    df, factor_cols = load_factors_and_returns(forward_days)

    # 批量计算IC
    print(f">> 批量计算{len(factor_cols)}个因子的rank IC...", flush=True)
    results = []
    t0 = time.time()
    for i, fname in enumerate(factor_cols):
        r = compute_rank_ic(df, fname)
        results.append(r)
        if (i + 1) % 50 == 0:
            elapsed = time.time() - t0
            print(f"   {i+1}/{len(factor_cols)} 完成 ({elapsed:.0f}s)", flush=True)

    elapsed = time.time() - t0
    print(f"   全部完成: {len(results)} 个因子 ({elapsed:.0f}s)\n", flush=True)

    # 排序：按 |ICIR| 降序
    results.sort(key=lambda x: abs(x["icir"]), reverse=True)

    # 输出 top 50
    print("=" * 80, flush=True)
    print("Top 50 因子（按|ICIR|降序）", flush=True)
    print("=" * 80, flush=True)
    print(f"{'因子':<45} {'IC':>8} {'IC_std':>8} {'ICIR':>8} {'天数':>6}", flush=True)
    print("-" * 80, flush=True)
    for r in results[:50]:
        print(f"{r['factor']:<45} {r['mean_ic']:>+8.4f} {r['ic_std']:>8.4f} "
              f"{r['icir']:>+8.4f} {r['n_days']:>6}", flush=True)

    # 筛选有效因子：|IC| > 0.03 且 |ICIR| > 0.5
    effective = [r for r in results if abs(r["mean_ic"]) > 0.03 and abs(r["icir"]) > 0.5]
    print(f"\n有效因子（|IC|>0.03 且 |ICIR|>0.5）: {len(effective)} 个", flush=True)
    for r in effective:
        print(f"  {r['factor']:<45} IC={r['mean_ic']:>+.4f} ICIR={r['icir']:>+.4f}", flush=True)

    # 当前v53使用的12个因子的IC
    v53_factors = [
        "Price1M", "Price3M", "ROC20", "DAVOL10", "money_flow_20",
        "gross_income_ratio", "roe_ttm", "net_profit_ratio",
        "earnings_to_price_ratio", "book_to_price_ratio",
        "raw_beta", "residual_volatility",
    ]
    print(f"\nv53使用的12个因子IC:", flush=True)
    for fname in v53_factors:
        r = next((x for x in results if x["factor"] == fname), None)
        if r:
            print(f"  {r['factor']:<45} IC={r['mean_ic']:>+.4f} ICIR={r['icir']:>+.4f}", flush=True)

    # 保存结果
    output_dir = Path("output/factor_analysis")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"factor_ic_screening_h{forward_days}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "params": {
                "pool": POOL_INDEX,
                "start": IS_START,
                "end": IS_END,
                "forward_days": FORWARD_DAYS,
            },
            "all_factors": results,
            "effective_factors": effective,
        }, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n结果已保存: {output_file}", flush=True)


if __name__ == "__main__":
    main()
