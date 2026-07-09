"""公共类型定义

为整个框架提供统一的类型别名，确保各模块间类型一致。
"""
from __future__ import annotations

from typing import TypeAlias, Union

import polars as pl

# 证券代码（如 "000001.SZ"）
Code: TypeAlias = str

# 日期字符串（"YYYY-MM-DD"）或日期对象
DateLike: TypeAlias = Union[str, pl.Date]

# 净值序列
NavSeries: TypeAlias = pl.Series

# 因子值矩阵（date × code）
FactorMatrix: TypeAlias = pl.DataFrame

# 持仓权重（code → weight）
WeightMap: TypeAlias = dict[str, float]

# 持仓列表项
Position: TypeAlias = dict[str, object]

# 数据字典（字段名 → DataFrame）
DataDict: TypeAlias = dict[str, pl.DataFrame]

# 调仓频率
RebalanceFreq: TypeAlias = str  # "daily" / "weekly" / "monthly" / "quarterly" / "adaptive"

# 市场状态
Regime: TypeAlias = str  # "strong_trend" / "weak_trend" / "sideway" / "high_vol"
