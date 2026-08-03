"""expertForest_v1 特征集划分与因子数量分析

检查momentum/fundamental特征集的因子数量、IC分布,识别优化机会。
"""
from __future__ import annotations

import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import polars as pl
from scipy.stats import spearmanr

DATA_ROOT = "D:/Work/Project/download_a_share/data"
POOL_INDEX = "000905.XSHG"

from ohmyquant.data.sources.duckdb_source import DuckDBSource
from ohmyquant.strategy.strategies.expertForest.v1.expert_pool import (
    MOMENTUM_PREFIXES, FUNDAMENTAL_PREFIXES, filter_features
)


def main():
    source = DuckDBSource({"data_root": DATA_ROOT})
    con = source.con

    # 加载成分股
    rows = con.execute(f"""
        SELECT DISTINCT code FROM index_constituents
        WHERE index_code = '{POOL_INDEX}'
    """).fetchall()
    codes = [r[0] for r in rows]
    print(f"成分股: {len(codes)} 只 ({POOL_INDEX})", flush=True)

    # 加载factors_wide schema
    schema_df = con.execute("SELECT * FROM factors_wide LIMIT 0").pl()
    all_factor_cols = [c for c in schema_df.columns if c not in ("date", "code")]
    print(f"\nfactors_wide总因子数: {len(all_factor_cols)}", flush=True)

    # 检查覆盖率(用2024-2025数据采样)
    codes_str = ", ".join(f"'{c}'" for c in codes[:300])  # 用前300只采样
    sample_df = con.execute(f"""
        SELECT * FROM factors_wide
        WHERE code IN ({codes_str})
          AND date >= '2024-01-01' AND date <= '2025-12-31'
    """).pl()
    total_rows = len(sample_df)
    print(f"采样数据: {total_rows} 行 (前300只股票, 2024-2025)", flush=True)

    # 筛选覆盖率>80%的因子
    valid_factors = []
    for col in all_factor_cols:
        if col in sample_df.columns:
            non_null = sample_df[col].is_not_null().sum()
            if non_null / total_rows >= 0.80:
                valid_factors.append(col)
    print(f"覆盖率>80%的因子: {len(valid_factors)}/{len(all_factor_cols)}", flush=True)

    # 衍生因子(模拟factor_engine的计算)
    derived_cols = [
        "drv_MA5", "drv_MA10", "drv_MA20", "drv_MA60",
        "drv_BIAS5", "drv_BIAS10", "drv_BIAS20", "drv_BIAS60",
        "drv_MOM_1d", "drv_MOM_5d", "drv_MOM_10d", "drv_MOM_20d", "drv_MOM_60d",
        "drv_VOL_5", "drv_VOL_10", "drv_VOL_20", "drv_VOL_60",
        "drv_VR_5", "drv_VR_20", "drv_R5", "drv_R20", "drv_VRatio_20_60",
    ]
    hk_col = "hk_hold_ratio_change_5d"

    all_factors = valid_factors + derived_cols + [hk_col]
    print(f"\n总因子数(原始+衍生+北向): {len(all_factors)}", flush=True)
    print(f"  原始: {len(valid_factors)}, 衍生: {len(derived_cols)}, 北向: 1", flush=True)

    # 按特征集分组
    momentum_factors = filter_features(all_factors, MOMENTUM_PREFIXES)
    fundamental_factors = filter_features(all_factors, FUNDAMENTAL_PREFIXES)
    uncategorized = [f for f in all_factors if f not in momentum_factors and f not in fundamental_factors]

    print(f"\n=== 特征集划分 ===", flush=True)
    print(f"  momentum: {len(momentum_factors)} 因子", flush=True)
    print(f"  fundamental: {len(fundamental_factors)} 因子", flush=True)
    print(f"  未分类: {len(uncategorized)} 因子", flush=True)

    if uncategorized:
        print(f"\n  未分类因子列表:", flush=True)
        for f in uncategorized:
            print(f"    {f}", flush=True)

    # 打印各特征集的因子样例
    print(f"\n  momentum因子样例(前20):", flush=True)
    for f in momentum_factors[:20]:
        print(f"    {f}", flush=True)
    if len(momentum_factors) > 20:
        print(f"    ... 共{len(momentum_factors)}个", flush=True)

    print(f"\n  fundamental因子样例(前20):", flush=True)
    for f in fundamental_factors[:20]:
        print(f"    {f}", flush=True)
    if len(fundamental_factors) > 20:
        print(f"    ... 共{len(fundamental_factors)}个", flush=True)

    # 检查是否有重叠
    overlap = set(momentum_factors) & set(fundamental_factors)
    if overlap:
        print(f"\n  ⚠️ 特征集重叠因子: {overlap}", flush=True)
    else:
        print(f"\n  ✅ 特征集无重叠", flush=True)

    print(f"\n分析完成。", flush=True)


if __name__ == "__main__":
    main()
