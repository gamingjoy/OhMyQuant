"""新数据源因子IC分析：北向资金 + 主力资金 + 估值因子

候选因子：
  北向资金（3个）：hk_hold_ratio, hk_hold_ratio_change_5d, hk_hold_ratio_change_20d
  主力资金（4个）：main_net_inflow_ratio, main_net_inflow_5d, main_net_inflow_20d, xl_net_inflow_ratio
  估值因子（3个）：ps_ratio_inv, pcf_ratio_inv, dividend_yield

用法:
    python scripts/new_factor_ic_analysis.py --horizon 5
    python scripts/new_factor_ic_analysis.py --horizon 20
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
from scipy.stats import spearmanr

DATA_ROOT = "D:/Work/Project/download_a_share/data"
POOL_INDEX = "000300.XSHG"
IS_START = "2022-01-01"
IS_END = "2025-12-31"


def load_pool_and_returns(forward_days: int) -> pl.DataFrame:
    """加载沪深300成分股和前向收益"""
    con = duckdb.connect()

    # 成分股
    constituents = con.execute(f"""
        SELECT DISTINCT code FROM read_parquet('{DATA_ROOT}/parquet/index_constituents/**/*.parquet')
        WHERE index_code = '{POOL_INDEX}'
    """).fetchall()
    stock_codes = [r[0] for r in constituents]
    codes_df = pl.DataFrame({"code": stock_codes})
    con.register("stock_codes", codes_df)
    print(f"成分股: {len(stock_codes)} 只", flush=True)

    # 收盘价
    close_df = con.execute(f"""
        SELECT d.date, d.code, d.close
        FROM read_parquet('{DATA_ROOT}/stock_daily_wide_partitioned/**/*.parquet') d
        JOIN stock_codes s ON d.code = s.code
        WHERE d.date >= '{IS_START}' AND d.date <= '{IS_END}'
    """).pl()
    close_df = close_df.with_columns(pl.col("date").cast(pl.Date))
    close_df = close_df.sort(["code", "date"])
    close_df = close_df.with_columns(
        pl.col("close").shift(-forward_days).over("code").alias("future_close")
    )
    close_df = close_df.with_columns(
        (pl.col("future_close") / pl.col("close") - 1.0).alias("forward_return")
    )
    close_df = close_df.drop_nulls(subset=["forward_return"])
    print(f"价格数据: {close_df.shape}", flush=True)
    con.close()
    return close_df, stock_codes


def build_hk_hold_factors(stock_codes: list[str]) -> pl.DataFrame:
    """构建北向资金因子"""
    print(">> 构建北向资金因子...", flush=True)
    con = duckdb.connect()
    codes_df = pl.DataFrame({"code": stock_codes})
    con.register("stock_codes", codes_df)

    df = con.execute(f"""
        SELECT date, code, share_ratio
        FROM read_parquet('{DATA_ROOT}/parquet/stock_hk_hold/**/*.parquet')
        WHERE date >= '{IS_START}' AND date <= '{IS_END}'
          AND code IN (SELECT code FROM stock_codes)
        ORDER BY code, date
    """).pl()
    df = df.with_columns(pl.col("date").cast(pl.Date))
    print(f"   北向数据: {df.shape}", flush=True)

    if len(df) == 0:
        con.close()
        return pl.DataFrame()

    # 每只股票取每日最新的share_ratio（可能有多条link_id记录）
    df = df.group_by(["date", "code"]).agg(pl.col("share_ratio").sum().alias("hk_hold_ratio"))

    # 计算变化值
    df = df.sort(["code", "date"])
    df = df.with_columns(
        pl.col("hk_hold_ratio").shift(5).over("code").alias("hk_hold_ratio_5d_ago")
    )
    df = df.with_columns(
        pl.col("hk_hold_ratio").shift(20).over("code").alias("hk_hold_ratio_20d_ago")
    )
    df = df.with_columns(
        (pl.col("hk_hold_ratio") - pl.col("hk_hold_ratio_5d_ago")).alias("hk_hold_ratio_change_5d"),
        (pl.col("hk_hold_ratio") - pl.col("hk_hold_ratio_20d_ago")).alias("hk_hold_ratio_change_20d"),
    )
    df = df.select([
        "date", "code", "hk_hold_ratio", "hk_hold_ratio_change_5d", "hk_hold_ratio_change_20d"
    ])
    con.close()
    print(f"   北向因子: {df.shape}", flush=True)
    return df


def build_money_flow_factors(stock_codes: list[str]) -> pl.DataFrame:
    """构建主力资金因子"""
    print(">> 构建主力资金因子...", flush=True)
    con = duckdb.connect()
    codes_df = pl.DataFrame({"code": stock_codes})
    con.register("stock_codes", codes_df)

    df = con.execute(f"""
        SELECT f.date, f.code,
               f.inflow_l, f.inflow_m, f.inflow_s, f.inflow_xl,
               f.outflow_l, f.outflow_m, f.outflow_s, f.outflow_xl
        FROM read_parquet('{DATA_ROOT}/parquet/stock_money_flow/**/*.parquet') f
        JOIN stock_codes s ON f.code = s.code
        WHERE f.date >= '{IS_START}' AND f.date <= '{IS_END}'
        ORDER BY f.code, f.date
    """).pl()
    df = df.with_columns(pl.col("date").cast(pl.Date))
    print(f"   资金流数据: {df.shape}", flush=True)

    if len(df) == 0:
        con.close()
        return pl.DataFrame()

    # 主力净流入 = (超大单流入+大单流入) - (超大单流出+大单流出)
    df = df.with_columns(
        ((pl.col("inflow_xl") + pl.col("inflow_l")) -
         (pl.col("outflow_xl") + pl.col("outflow_l"))).alias("main_net_inflow")
    )
    # 总成交额 = 所有流入+所有流出
    df = df.with_columns(
        (pl.col("inflow_xl") + pl.col("inflow_l") + pl.col("inflow_m") + pl.col("inflow_s") +
         pl.col("outflow_xl") + pl.col("outflow_l") + pl.col("outflow_m") + pl.col("outflow_s")).alias("total_flow")
    )
    # 主力净流入比率
    df = df.with_columns(
        (pl.col("main_net_inflow") / pl.col("total_flow")).alias("main_net_inflow_ratio")
    )
    # 超大单净流入比率
    df = df.with_columns(
        ((pl.col("inflow_xl") - pl.col("outflow_xl")) / pl.col("total_flow")).alias("xl_net_inflow_ratio")
    )

    # 5日累计和20日累计
    df = df.sort(["code", "date"])
    df = df.with_columns(
        pl.col("main_net_inflow_ratio").rolling_sum(window_size=5).over("code").alias("main_net_inflow_5d"),
        pl.col("main_net_inflow_ratio").rolling_sum(window_size=20).over("code").alias("main_net_inflow_20d"),
    )

    df = df.select([
        "date", "code", "main_net_inflow_ratio", "main_net_inflow_5d",
        "main_net_inflow_20d", "xl_net_inflow_ratio"
    ])
    con.close()
    print(f"   资金流因子: {df.shape}", flush=True)
    return df


def build_valuation_factors(stock_codes: list[str]) -> pl.DataFrame:
    """构建估值因子"""
    print(">> 构建估值因子...", flush=True)
    con = duckdb.connect()
    codes_df = pl.DataFrame({"code": stock_codes})
    con.register("stock_codes", codes_df)

    df = con.execute(f"""
        SELECT v.date, v.code, v.ps_ratio, v.pcf_ratio, v.pcf_ratio2, v.dividend_ratio
        FROM read_parquet('{DATA_ROOT}/parquet/stock_valuation/**/*.parquet') v
        JOIN stock_codes s ON v.code = s.code
        WHERE v.date >= '{IS_START}' AND v.date <= '{IS_END}'
        ORDER BY v.date, v.code
    """).pl()
    df = df.with_columns(pl.col("date").cast(pl.Date))
    print(f"   估值数据: {df.shape}", flush=True)

    if len(df) == 0:
        con.close()
        return pl.DataFrame()

    # 估值因子取倒数（低估值→高分）
    df = df.with_columns(
        (1.0 / pl.col("ps_ratio")).alias("ps_ratio_inv"),
        (1.0 / pl.col("pcf_ratio2")).alias("pcf_ratio_inv"),
    )
    # 股息率直接使用（高股息→高分）
    # dividend_ratio 已是百分比形式

    df = df.select(["date", "code", "ps_ratio_inv", "pcf_ratio_inv", "dividend_ratio"])
    con.close()
    print(f"   估值因子: {df.shape}", flush=True)
    return df


def compute_rank_ic(df: pl.DataFrame, factor_name: str) -> dict:
    """计算单个因子的rank IC"""
    sub = df.select([factor_name, "forward_return", "date"]).drop_nulls()
    if len(sub) < 100:
        return {"factor": factor_name, "mean_ic": 0.0, "ic_std": 0.0, "icir": 0.0, "n_days": 0}

    ic_list = []
    for (date,), group in sub.group_by(["date"]):
        if len(group) < 10:
            continue
        vals = group.select([factor_name, "forward_return"]).to_numpy()
        if np.std(vals[:, 0]) == 0 or np.std(vals[:, 1]) == 0:
            continue
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
    parser.add_argument("--horizon", type=int, default=5)
    args = parser.parse_args()
    h = args.horizon

    print("=" * 100, flush=True)
    print(f"新数据源因子IC分析：{IS_START}~{IS_END}，沪深300，{h}日horizon", flush=True)
    print("=" * 100, flush=True)

    # 1. 加载收益数据
    t0 = time.time()
    close_df, stock_codes = load_pool_and_returns(h)
    returns_df = close_df.select(["date", "code", "forward_return"])

    # 2. 构建所有因子
    hk_df = build_hk_hold_factors(stock_codes)
    mf_df = build_money_flow_factors(stock_codes)
    val_df = build_valuation_factors(stock_codes)

    # 3. 合并
    print("\n>> 合并所有因子...", flush=True)
    merged = returns_df
    if len(hk_df) > 0:
        merged = merged.join(hk_df, on=["date", "code"], how="left")
    if len(mf_df) > 0:
        merged = merged.join(mf_df, on=["date", "code"], how="left")
    if len(val_df) > 0:
        merged = merged.join(val_df, on=["date", "code"], how="left")
    print(f"   合并后: {merged.shape}", flush=True)

    # 4. 计算IC
    factor_cols = [c for c in merged.columns if c not in ("date", "code", "forward_return")]
    print(f"\n>> 计算{len(factor_cols)}个因子的rank IC...", flush=True)

    results = []
    for i, fname in enumerate(factor_cols):
        r = compute_rank_ic(merged, fname)
        results.append(r)
        print(f"   {i+1}/{len(factor_cols)} {fname:<40} IC={r['mean_ic']:>+.4f} "
              f"ICIR={r['icir']:>+.4f} 天数={r['n_days']}", flush=True)

    elapsed = time.time() - t0
    print(f"\n完成: {elapsed:.0f}s\n", flush=True)

    # 排序输出
    results.sort(key=lambda x: abs(x["icir"]), reverse=True)
    print("=" * 100, flush=True)
    print(f"因子排名（按|ICIR|降序，{h}日horizon）", flush=True)
    print("=" * 100, flush=True)
    print(f"{'因子':<40} {'IC':>8} {'IC_std':>8} {'ICIR':>8} {'天数':>6}", flush=True)
    print("-" * 80, flush=True)
    for r in results:
        print(f"{r['factor']:<40} {r['mean_ic']:>+8.4f} {r['ic_std']:>8.4f} "
              f"{r['icir']:>+8.4f} {r['n_days']:>6}", flush=True)

    # 有效因子
    effective = [r for r in results if abs(r["mean_ic"]) > 0.02 and abs(r["icir"]) > 0.3]
    print(f"\n有效因子（|IC|>0.02 且 |ICIR|>0.3）: {len(effective)} 个", flush=True)
    for r in effective:
        print(f"  ★ {r['factor']:<40} IC={r['mean_ic']:>+.4f} ICIR={r['icir']:>+.4f}", flush=True)

    # 保存
    output_dir = Path("output/factor_analysis")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"new_factor_ic_h{h}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({"horizon": h, "results": results, "effective": effective}, f, indent=2, ensure_ascii=False)
    print(f"\n结果已保存: {output_file}", flush=True)


if __name__ == "__main__":
    main()
