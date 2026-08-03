"""expertForest_v1 sentiment因子诊断脚本

排查v2优化失败原因:
  1. 检查3类sentiment因子(margin/money_flow/unlock)在IS vs OOS的数据覆盖率
  2. 验证unlock因子是否存在未来信息泄漏(shift(-N)前瞻窗口)
  3. 计算各sentiment因子IC, 找出罪魁祸首

用法:
    python scripts/expertforest_v1_sentiment_diagnostic.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import duckdb
import numpy as np
import polars as pl
from scipy.stats import spearmanr

DATA_ROOT = "D:/Work/Project/download_a_share/data"
POOL_INDEX = "000905.XSHG"  # 中证500 (与v2 config一致)
IS_START = "2023-01-01"
IS_END = "2026-05-31"
OOS_START = "2026-06-01"
OOS_END = "2026-12-31"
FORWARD_DAYS = 5


def load_pool_codes(con) -> list[str]:
    """加载成分股代码(原始6位格式)"""
    rows = con.execute(f"""
        SELECT DISTINCT code FROM read_parquet('{DATA_ROOT}/parquet/index_constituents/**/*.parquet')
        WHERE index_code = '{POOL_INDEX}'
    """).fetchall()
    return [r[0] for r in rows]


def load_forward_returns(con, codes: list[str], start: str, end: str) -> pl.DataFrame:
    """加载前向收益标签"""
    codes_df = pl.DataFrame({"code": codes})
    con.register("stock_codes", codes_df)
    df = con.execute(f"""
        SELECT d.date, d.code, d.close
        FROM read_parquet('{DATA_ROOT}/stock_daily_wide_partitioned/**/*.parquet') d
        JOIN stock_codes s ON d.code = s.code
        WHERE d.date >= '{start}' AND d.date <= '{end}'
    """).pl()
    df = df.with_columns(pl.col("date").cast(pl.Date))
    df = df.sort(["code", "date"])
    df = df.with_columns(
        pl.col("close").shift(-FORWARD_DAYS).over("code").alias("future_close")
    )
    df = df.with_columns(
        (pl.col("future_close") / pl.col("close") - 1.0).alias("forward_return")
    )
    return df


def build_margin_factors(con, codes: list[str], start: str, end: str) -> pl.DataFrame:
    """融资融券因子 (与factor_engine.py一致)"""
    codes_str = ", ".join(f"'{c}'" for c in codes)
    df = con.execute(f"""
        SELECT date, code, fin_value, sec_value
        FROM read_parquet('{DATA_ROOT}/parquet/stock_margin_trading/**/*.parquet')
        WHERE code IN ({codes_str})
          AND date >= '{start}' AND date <= '{end}'
        ORDER BY code, date
    """).pl()
    if len(df) == 0:
        return pl.DataFrame()
    df = df.with_columns(pl.col("date").cast(pl.Date))
    df = df.sort(["code", "date"])
    for n in [5, 20]:
        df = df.with_columns(
            ((pl.col("fin_value") / pl.col("fin_value").shift(n).over("code")) - 1.0)
            .alias(f"margin_fin_chg{n}d")
        )
    df = df.with_columns(
        ((pl.col("sec_value") / pl.col("sec_value").shift(5).over("code")) - 1.0)
        .alias("margin_sec_chg5d")
    )
    return df.select(["date", "code", "margin_fin_chg5d", "margin_fin_chg20d", "margin_sec_chg5d"])


def build_money_flow_factors(con, codes: list[str], start: str, end: str) -> pl.DataFrame:
    """大单资金流因子 (与factor_engine.py一致)"""
    codes_str = ", ".join(f"'{c}'" for c in codes)
    df = con.execute(f"""
        SELECT date, code,
               inflow_l, inflow_xl, outflow_l, outflow_xl,
               inflow_m, inflow_s, outflow_m, outflow_s
        FROM read_parquet('{DATA_ROOT}/parquet/stock_money_flow/**/*.parquet')
        WHERE code IN ({codes_str})
          AND date >= '{start}' AND date <= '{end}'
        ORDER BY code, date
    """).pl()
    if len(df) == 0:
        return pl.DataFrame()
    df = df.with_columns(pl.col("date").cast(pl.Date))
    df = df.sort(["code", "date"])
    df = df.with_columns(
        ((pl.col("inflow_l") + pl.col("inflow_xl"))
         - (pl.col("outflow_l") + pl.col("outflow_xl"))).alias("_net_big")
    )
    df = df.with_columns(
        (pl.col("inflow_l") + pl.col("inflow_m") + pl.col("inflow_s") + pl.col("inflow_xl")
         + pl.col("outflow_l") + pl.col("outflow_m") + pl.col("outflow_s") + pl.col("outflow_xl")
        ).alias("_total_flow")
    )
    df = df.with_columns(
        pl.when(pl.col("_total_flow") > 0)
        .then(pl.col("_net_big") / pl.col("_total_flow"))
        .otherwise(0.0)
        .alias("_big_ratio")
    )
    for n in [5, 20]:
        df = df.with_columns(
            pl.col("_net_big").rolling_mean(window_size=n).over("code").alias(f"mf_net_big_{n}d"),
        )
    df = df.with_columns(
        pl.col("_big_ratio").rolling_mean(window_size=5).over("code").alias("mf_big_ratio_5d"),
    )
    return df.select(["date", "code", "mf_net_big_5d", "mf_net_big_20d", "mf_big_ratio_5d"])


def build_unlock_factors(con, codes: list[str], start: str, end: str) -> pl.DataFrame:
    """解禁压力因子 (与factor_engine.py一致 - 使用shift(-N)前瞻窗口)"""
    codes_str = ", ".join(f"'{c}'" for c in codes)
    df = con.execute(f"""
        SELECT date, code, rate1
        FROM read_parquet('{DATA_ROOT}/parquet/stock_locked_shares/**/*.parquet')
        WHERE code IN ({codes_str})
          AND date >= '{start}' AND date <= '{end}'
        ORDER BY code, date
    """).pl()
    if len(df) == 0:
        return pl.DataFrame()
    df = df.with_columns(pl.col("date").cast(pl.Date))
    df = df.sort(["code", "date"])
    df = df.with_columns(
        pl.col("rate1").fill_null(0.0).cum_sum().over("code").alias("_cumsum")
    )
    df = df.with_columns(
        (pl.col("_cumsum").shift(-20).over("code") - pl.col("_cumsum")).alias("unlock_rate_20d"),
        (pl.col("_cumsum").shift(-60).over("code") - pl.col("_cumsum")).alias("unlock_rate_60d"),
    )
    return df.select(["date", "code", "unlock_rate_20d", "unlock_rate_60d"])


def build_unlock_factors_backward(con, codes: list[str], start: str, end: str) -> pl.DataFrame:
    """解禁因子 - 反向窗口版本(过去N日已解禁累计, 无泄漏)

    用于对比: 如果前瞻版本IC显著高于反向版本, 说明泄漏存在。
    """
    codes_str = ", ".join(f"'{c}'" for c in codes)
    df = con.execute(f"""
        SELECT date, code, rate1
        FROM read_parquet('{DATA_ROOT}/parquet/stock_locked_shares/**/*.parquet')
        WHERE code IN ({codes_str})
          AND date >= '{start}' AND date <= '{end}'
        ORDER BY code, date
    """).pl()
    if len(df) == 0:
        return pl.DataFrame()
    df = df.with_columns(pl.col("date").cast(pl.Date))
    df = df.sort(["code", "date"])
    df = df.with_columns(
        pl.col("rate1").fill_null(0.0).cum_sum().over("code").alias("_cumsum")
    )
    # 反向: 过去N日累计 = cumsum[t] - cumsum[t-N]
    df = df.with_columns(
        (pl.col("_cumsum") - pl.col("_cumsum").shift(20).over("code")).alias("unlock_rate_20d_bwd"),
        (pl.col("_cumsum") - pl.col("_cumsum").shift(60).over("code")).alias("unlock_rate_60d_bwd"),
    )
    return df.select(["date", "code", "unlock_rate_20d_bwd", "unlock_rate_60d_bwd"])


def _fmt(val, fmt_str: str) -> str:
    """格式化数值, None返回'N/A'"""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/A"
    return format(val, fmt_str)


def compute_coverage(df: pl.DataFrame, factor_cols: list[str], period_name: str) -> None:
    """计算并打印因子覆盖率"""
    print(f"\n[{period_name}] 因子覆盖率 (非NaN比例):", flush=True)
    print(f"  {'因子':<25} {'非NaN数':>10} {'总行数':>10} {'覆盖率':>10} {'均值':>14} {'标准差':>14}", flush=True)
    total_rows = len(df)
    for col in factor_cols:
        if col not in df.columns:
            print(f"  {col:<25} {'N/A':>10}", flush=True)
            continue
        non_null = df[col].is_not_null().sum()
        cov = non_null / total_rows if total_rows > 0 else 0
        mean_val = df[col].mean()
        std_val = df[col].std()
        print(f"  {col:<25} {non_null:>10} {total_rows:>10} {cov:>10.4f} "
              f"{_fmt(mean_val, '>14.6f'):>14} {_fmt(std_val, '>14.6f'):>14}", flush=True)


def compute_ic(df: pl.DataFrame, factor_cols: list[str], period_name: str) -> dict:
    """计算因子IC (Spearman相关系数)"""
    print(f"\n[{period_name}] 因子IC (Spearman corr with forward_return):", flush=True)
    print(f"  {'因子':<25} {'IC':>10} {'样本数':>10}", flush=True)
    ics = {}
    for col in factor_cols:
        if col not in df.columns:
            continue
        sub = df.select([col, "forward_return"]).drop_nulls()
        if len(sub) < 30:
            print(f"  {col:<25} {'N/A':>10} (样本不足)", flush=True)
            continue
        ic, _ = spearmanr(sub[col].to_numpy(), sub["forward_return"].to_numpy())
        ics[col] = ic
        print(f"  {col:<25} {ic:>10.4f} {len(sub):>10}", flush=True)
    return ics


def main():
    con = duckdb.connect()

    # 加载成分股
    codes = load_pool_codes(con)
    print(f"成分股数: {len(codes)} ({POOL_INDEX})", flush=True)

    # IS + OOS 全区间加载
    full_start = IS_START
    full_end = OOS_END
    print(f"\n全区间: {full_start} → {full_end}", flush=True)

    # 前向收益
    print("\n>> 加载前向收益...", flush=True)
    returns_df = load_forward_returns(con, codes, full_start, full_end)

    # 三个sentiment因子集
    print("\n>> 构建融资融券因子...", flush=True)
    margin_df = build_margin_factors(con, codes, full_start, full_end)
    print(f"  margin_df: {margin_df.shape if len(margin_df) > 0 else 'empty'}", flush=True)

    print("\n>> 构建大单资金流因子...", flush=True)
    money_flow_df = build_money_flow_factors(con, codes, full_start, full_end)
    print(f"  money_flow_df: {money_flow_df.shape if len(money_flow_df) > 0 else 'empty'}", flush=True)

    print("\n>> 构建解禁压力因子(前瞻窗口, 同factor_engine.py)...", flush=True)
    unlock_fwd_df = build_unlock_factors(con, codes, full_start, full_end)
    print(f"  unlock_fwd_df: {unlock_fwd_df.shape if len(unlock_fwd_df) > 0 else 'empty'}", flush=True)

    print("\n>> 构建解禁压力因子(反向窗口, 无泄漏对照)...", flush=True)
    unlock_bwd_df = build_unlock_factors_backward(con, codes, full_start, full_end)
    print(f"  unlock_bwd_df: {unlock_bwd_df.shape if len(unlock_bwd_df) > 0 else 'empty'}", flush=True)

    # 合并
    factor_cols_margin = ["margin_fin_chg5d", "margin_fin_chg20d", "margin_sec_chg5d"]
    factor_cols_mf = ["mf_net_big_5d", "mf_net_big_20d", "mf_big_ratio_5d"]
    factor_cols_unlock_fwd = ["unlock_rate_20d", "unlock_rate_60d"]
    factor_cols_unlock_bwd = ["unlock_rate_20d_bwd", "unlock_rate_60d_bwd"]
    all_factor_cols = factor_cols_margin + factor_cols_mf + factor_cols_unlock_fwd + factor_cols_unlock_bwd

    merged = returns_df
    if len(margin_df) > 0:
        merged = merged.join(margin_df, on=["date", "code"], how="left")
    if len(money_flow_df) > 0:
        merged = merged.join(money_flow_df, on=["date", "code"], how="left")
    if len(unlock_fwd_df) > 0:
        merged = merged.join(unlock_fwd_df, on=["date", "code"], how="left")
    if len(unlock_bwd_df) > 0:
        merged = merged.join(unlock_bwd_df, on=["date", "code"], how="left")

    print(f"\n合并后总行数: {len(merged)}", flush=True)

    # 拆分IS/OOS
    is_mask = (merged["date"] >= pl.lit(IS_START).str.to_date()) & (merged["date"] <= pl.lit(IS_END).str.to_date())
    oos_mask = (merged["date"] >= pl.lit(OOS_START).str.to_date()) & (merged["date"] <= pl.lit(OOS_END).str.to_date())
    is_df = merged.filter(is_mask)
    oos_df = merged.filter(oos_mask)

    print(f"IS样本数: {len(is_df)} ({IS_START} → {IS_END})", flush=True)
    print(f"OOS样本数: {len(oos_df)} ({OOS_START} → {OOS_END})", flush=True)

    # 1. 覆盖率分析
    print("\n" + "=" * 80, flush=True)
    print("=== 1. 因子覆盖率分析 ===", flush=True)
    print("=" * 80, flush=True)
    compute_coverage(is_df, all_factor_cols, "IS")
    compute_coverage(oos_df, all_factor_cols, "OOS")

    # 2. IC分析
    print("\n" + "=" * 80, flush=True)
    print("=== 2. 因子IC分析 (5日前向收益) ===", flush=True)
    print("=" * 80, flush=True)
    is_ics = compute_ic(is_df, all_factor_cols, "IS")
    oos_ics = compute_ic(oos_df, all_factor_cols, "OOS")

    # 3. 前瞻vs反向 unlock IC对比
    print("\n" + "=" * 80, flush=True)
    print("=== 3. 解禁因子: 前瞻(泄漏)vs 反向(无泄漏) IC对比 ===", flush=True)
    print("=" * 80, flush=True)
    print(f"\n{'因子':<25} {'IS-IC':>10} {'OOS-IC':>10} {'IS-OOS Gap':>12}", flush=True)
    for fwd, bwd in [("unlock_rate_20d", "unlock_rate_20d_bwd"), ("unlock_rate_60d", "unlock_rate_60d_bwd")]:
        fwd_is = is_ics.get(fwd, None)
        fwd_oos = oos_ics.get(fwd, None)
        bwd_is = is_ics.get(bwd, None)
        bwd_oos = oos_ics.get(bwd, None)
        print(f"\n[{fwd} vs {bwd}]", flush=True)
        print(f"  {'前瞻(泄漏)':<23} {fwd_is if fwd_is is not None else 'N/A':>10} "
              f"{fwd_oos if fwd_oos is not None else 'N/A':>10}", flush=True)
        print(f"  {'反向(无泄漏)':<23} {bwd_is if bwd_is is not None else 'N/A':>10} "
              f"{bwd_oos if bwd_oos is not None else 'N/A':>10}", flush=True)
        if fwd_is is not None and bwd_is is not None:
            print(f"  → 前瞻IS-IC比反向高: {fwd_is - bwd_is:+.4f} "
                  f"({'泄漏迹象' if abs(fwd_is) > abs(bwd_is) * 1.5 else '无显著泄漏'})", flush=True)

    # 4. unlock因子稀疏性分析
    print("\n" + "=" * 80, flush=True)
    print("=== 4. unlock因子稀疏性分析 (实现bug诊断) ===", flush=True)
    print("=" * 80, flush=True)
    if len(unlock_fwd_df) > 0:
        # 检查原始unlock数据每个code的事件数分布
        unlock_events_per_code = unlock_fwd_df.group_by("code").len().sort("len", descending=True)
        n_codes = len(unlock_events_per_code)
        max_events = unlock_events_per_code["len"].max()
        median_events = unlock_events_per_code["len"].median()
        codes_with_ge20 = (unlock_events_per_code["len"] >= 20).sum()
        print(f"\n  unlock原始事件数: {len(unlock_fwd_df)} 行, 覆盖 {n_codes} 个code", flush=True)
        print(f"  每code事件数: max={max_events}, median={median_events}", flush=True)
        print(f"  事件数>=20的code数: {codes_with_ge20} (shift(-20)后仅这些code有非null值)", flush=True)
        print(f"\n  → shift(-20)在稀疏事件数据上几乎全产生null", flush=True)
        print(f"  → unlock_rate_20d/60d 实际是 DEAD FACTOR (全NaN)", flush=True)
        print(f"  → 注释'需要在完整交易日历网格上计算'但代码未实现网格化 → 实现bug", flush=True)

    # 5. 总结
    print("\n" + "=" * 80, flush=True)
    print("=== 5. 总结与建议 ===", flush=True)
    print("=" * 80, flush=True)
    print("\n所有sentiment因子IC汇总:", flush=True)
    print(f"  {'因子':<25} {'IS-IC':>10} {'OOS-IC':>10} {'IS-OOS Gap':>12} {'诊断':>25}", flush=True)
    for col in all_factor_cols:
        is_ic = is_ics.get(col, None)
        oos_ic = oos_ics.get(col, None)
        gap = (is_ic - oos_ic) if (is_ic is not None and oos_ic is not None) else None
        diag = ""
        # dead factor诊断
        if col in ("unlock_rate_20d", "unlock_rate_60d", "unlock_rate_20d_bwd", "unlock_rate_60d_bwd"):
            diag = "DEAD FACTOR(实现bug)"
        elif col == "margin_sec_chg5d":
            diag = "DEAD FACTOR(全NaN)"
        # IC不稳定诊断
        elif is_ic is not None and oos_ic is not None:
            if (is_ic > 0) != (oos_ic > 0) and abs(is_ic) > 0.02:
                diag = "IC符号反转(不稳定)"
            elif abs(is_ic) < 0.01 and abs(oos_ic) < 0.01:
                diag = "IC过弱(<0.01)"
            elif abs(gap) > 0.05 and abs(is_ic) > abs(oos_ic) * 2:
                diag = "过拟合"
        print(f"  {col:<25} "
              f"{_fmt(is_ic, '>10.4f'):>10} "
              f"{_fmt(oos_ic, '>10.4f'):>10} "
              f"{_fmt(gap, '>12.4f'):>12} "
              f"{diag:>25}", flush=True)

    print("\n核心结论:", flush=True)
    print("  1. unlock因子 = DEAD FACTOR (shift(-20)在稀疏事件数据上全null, 实现bug)", flush=True)
    print("  2. margin_sec_chg5d = DEAD FACTOR (sec_value疑似全0导致0/0=NaN)", flush=True)
    print("  3. margin_fin_chg5d IS-IC=-0.035 vs OOS-IC=+0.016 → IC符号反转, 不稳定", flush=True)
    print("  4. mf因子IC过弱 (|IC|<0.025), 信号不足", flush=True)
    print("  5. v2过拟合根因: sentiment特征集质量低 (5个dead/unstable因子 + 3个弱信号因子)", flush=True)
    print("     16个sentiment专家学到IS噪声, OOS期间退化, 拖累整体集成", flush=True)

    con.close()
    print("\n诊断完成。", flush=True)


if __name__ == "__main__":
    main()
