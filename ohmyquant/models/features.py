"""特征变换器

截面级特征变换，用于 FeaturePipeline。
每个变换器实现 fit_transform 和 transform 方法。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np
import polars as pl


class BaseTransform(ABC):
    """变换器抽象基类"""

    def __init__(self, **kwargs: Any):
        self.params = kwargs

    @abstractmethod
    def fit_transform(self, df: pl.DataFrame, feature_names: list[str]) -> pl.DataFrame:
        """拟合并变换"""
        ...

    @abstractmethod
    def transform(self, df: pl.DataFrame, feature_names: list[str]) -> pl.DataFrame:
        """用已拟合参数变换"""
        ...

    @staticmethod
    def _transform_column(df: pl.DataFrame, name: str, new_name: str, vals: list) -> pl.DataFrame:
        """替换列值"""
        return df.with_columns(pl.Series(new_name, vals)).drop(name).rename({new_name: name})


class RankTransform(BaseTransform):
    """截面排名归一化到 [0, 1]"""

    def fit_transform(self, df: pl.DataFrame, feature_names: list[str]) -> pl.DataFrame:
        return self.transform(df, feature_names)

    def transform(self, df: pl.DataFrame, feature_names: list[str]) -> pl.DataFrame:
        result = df
        for name in feature_names:
            if name not in df.columns:
                continue
            vals = df[name].to_list()
            valid = [v for v in vals if v is not None and not (isinstance(v, float) and np.isnan(v))]
            n = len(valid)
            if n < 2:
                continue
            ranks = []
            for v in vals:
                if v is None or (isinstance(v, float) and np.isnan(v)):
                    ranks.append(0.5)
                else:
                    rank = sum(1 for x in valid if x <= v) / n
                    ranks.append(rank)
            result = result.with_columns(pl.Series(name, ranks))
        return result


class ZScoreTransform(BaseTransform):
    """截面 z-score 标准化"""

    def fit_transform(self, df: pl.DataFrame, feature_names: list[str]) -> pl.DataFrame:
        return self.transform(df, feature_names)

    def transform(self, df: pl.DataFrame, feature_names: list[str]) -> pl.DataFrame:
        result = df
        for name in feature_names:
            if name not in df.columns:
                continue
            vals = df[name].to_list()
            valid = [v for v in vals if v is not None and not (isinstance(v, float) and np.isnan(v))]
            if len(valid) < 2:
                continue
            mean_v = float(np.mean(valid))
            std_v = float(np.std(valid))
            if std_v < 1e-8:
                continue
            zscores = []
            for v in vals:
                if v is None or (isinstance(v, float) and np.isnan(v)):
                    zscores.append(0.0)
                else:
                    zscores.append((v - mean_v) / std_v)
            result = result.with_columns(pl.Series(name, zscores))
        return result


class WinsorizeTransform(BaseTransform):
    """缩尾处理（截断极端值）"""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.lower = kwargs.get("lower", 0.01)
        self.upper = kwargs.get("upper", 0.99)

    def fit_transform(self, df: pl.DataFrame, feature_names: list[str]) -> pl.DataFrame:
        return self.transform(df, feature_names)

    def transform(self, df: pl.DataFrame, feature_names: list[str]) -> pl.DataFrame:
        result = df
        for name in feature_names:
            if name not in df.columns:
                continue
            vals = df[name].to_list()
            valid = sorted([v for v in vals if v is not None and not (isinstance(v, float) and np.isnan(v))])
            if len(valid) < 10:
                continue
            lo = valid[int(len(valid) * self.lower)]
            hi = valid[int(len(valid) * self.upper)]
            clipped = []
            for v in vals:
                if v is None or (isinstance(v, float) and np.isnan(v)):
                    clipped.append(v)
                else:
                    clipped.append(max(lo, min(hi, v)))
            result = result.with_columns(pl.Series(name, clipped))
        return result


class IndustryNeutralTransform(BaseTransform):
    """行业中性化（减去行业均值）"""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self._industry_means: dict[str, dict[str, float]] = {}

    def fit_transform(self, df: pl.DataFrame, feature_names: list[str]) -> pl.DataFrame:
        if "industry" not in df.columns:
            return df
        result = df
        for name in feature_names:
            if name not in df.columns:
                continue
            industry_means: dict[str, float] = {}
            for name_val in df["industry"].unique().to_list():
                subset = df.filter(pl.col("industry") == name_val)[name].drop_nulls()
                if len(subset) > 0:
                    industry_means[name_val] = float(subset.mean())
            self._industry_means[name] = industry_means

            vals = df[name].to_list()
            industries = df["industry"].to_list()
            neutralized = []
            for v, ind in zip(vals, industries):
                if v is None or ind not in industry_means:
                    neutralized.append(v)
                else:
                    neutralized.append(v - industry_means[ind])
            result = result.with_columns(pl.Series(name, neutralized))
        return result.drop("industry") if "industry" in result.columns else result

    def transform(self, df: pl.DataFrame, feature_names: list[str]) -> pl.DataFrame:
        if "industry" not in df.columns or not self._industry_means:
            return df
        result = df
        for name in feature_names:
            if name not in df.columns or name not in self._industry_means:
                continue
            vals = df[name].to_list()
            industries = df["industry"].to_list()
            means = self._industry_means[name]
            neutralized = []
            for v, ind in zip(vals, industries):
                if v is None or ind not in means:
                    neutralized.append(v)
                else:
                    neutralized.append(v - means[ind])
            result = result.with_columns(pl.Series(name, neutralized))
        return result.drop("industry") if "industry" in result.columns else result


class LagTransform(BaseTransform):
    """时滞处理（将因子值滞后 N 期）"""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.lag = kwargs.get("lag", 1)

    def fit_transform(self, df: pl.DataFrame, feature_names: list[str]) -> pl.DataFrame:
        return self.transform(df, feature_names)

    def transform(self, df: pl.DataFrame, feature_names: list[str]) -> pl.DataFrame:
        return df


_TRANSFORM_REGISTRY = {
    "rank": RankTransform,
    "zscore": ZScoreTransform,
    "winsorize": WinsorizeTransform,
    "industry_neutral": IndustryNeutralTransform,
    "lag": LagTransform,
}


def create_transform(name: str, **kwargs: Any) -> BaseTransform:
    """创建变换器实例"""
    cls = _TRANSFORM_REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"未知变换器: {name}，可选: {list(_TRANSFORM_REGISTRY.keys())}")
    return cls(**kwargs)


__all__ = [
    "BaseTransform",
    "RankTransform",
    "ZScoreTransform",
    "WinsorizeTransform",
    "IndustryNeutralTransform",
    "LagTransform",
    "create_transform",
]
