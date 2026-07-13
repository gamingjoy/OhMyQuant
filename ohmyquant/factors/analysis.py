"""因子分析

计算因子的 IC（信息系数）、ICIR（信息比率）、分位数收益、IC衰减等。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import polars as pl

from ..core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class FactorStats:
    """因子统计指标"""

    factor_name: str
    ic_mean: float = 0.0
    ic_std: float = 0.0
    icir: float = 0.0
    ic_positive_ratio: float = 0.0
    ic_abs_mean: float = 0.0
    n_obs: int = 0


@dataclass
class QuantileAnalysis:
    """分位数分析结果"""

    factor_name: str
    n_groups: int
    group_returns: dict[int, float] = field(default_factory=dict)  # {group: avg_return}
    long_short_return: float = 0.0  # 多空收益


class FactorAnalyzer:
    """因子分析器

    用法:
        analyzer = FactorAnalyzer()
        ic_series = analyzer.compute_ic(factor_values, forward_returns)
        stats = analyzer.compute_icir(ic_series)
        quantile = analyzer.compute_quantile_returns(factor_values, forward_returns)
    """

    @staticmethod
    def compute_ic(
        factor_values: pl.DataFrame,
        forward_returns: pl.DataFrame,
        method: str = "spearman",
    ) -> pl.DataFrame:
        """计算 IC 序列

        Args:
            factor_values: date × code 因子值宽表
            forward_returns: date × code 前向收益宽表
            method: "spearman" (Rank IC) 或 "pearson"

        Returns:
            DataFrame: date, ic 两列
        """
        from scipy.stats import pearsonr, spearmanr

        dates = factor_values["date"].to_list()
        ic_list: list[float | None] = []

        factor_cols = [c for c in factor_values.columns if c != "date"]
        return_cols = [c for c in forward_returns.columns if c != "date"]

        for i, d in enumerate(dates):
            fv_row = factor_values.row(i, named=True)
            fr_row = forward_returns.row(i, named=True)

            # 取共同 code
            common = [c for c in factor_cols if c in return_cols]
            fv = [fv_row[c] for c in common]
            fr = [fr_row[c] for c in common]

            # 过滤 None
            pairs = [(a, b) for a, b in zip(fv, fr) if a is not None and b is not None and not np.isnan(a) and not np.isnan(b)]
            if len(pairs) < 10:
                ic_list.append(None)
                continue

            fv_valid = [p[0] for p in pairs]
            fr_valid = [p[1] for p in pairs]

            try:
                if method == "spearman":
                    corr, _ = spearmanr(fv_valid, fr_valid)
                else:
                    corr, _ = pearsonr(fv_valid, fr_valid)
                ic_list.append(float(corr) if not np.isnan(corr) else None)
            except Exception:
                ic_list.append(None)

        return pl.DataFrame({"date": dates, "ic": ic_list})

    @staticmethod
    def compute_icir(
        ic_series: pl.DataFrame,
        window: int = 60,
        decay: float = 0.65,
    ) -> FactorStats:
        """计算 ICIR

        Args:
            ic_series: compute_ic 的输出
            window: 滚动窗口
            decay: 指数衰减权重（1.0 = 等权）

        Returns:
            FactorStats
        """
        ic = ic_series["ic"].drop_nulls()
        n = len(ic)
        if n < 10:
            return FactorStats(factor_name="", n_obs=n)

        ic_arr = ic.to_numpy()

        # 指数衰减加权
        if decay < 1.0 and n > 1:
            weights = np.array([decay ** k for k in range(n)])[::-1]
            weights = weights / weights.sum()
            ic_mean = float(np.average(ic_arr, weights=weights))
            ic_std = float(np.sqrt(np.average((ic_arr - ic_mean) ** 2, weights=weights)))
        else:
            ic_mean = float(ic_arr.mean())
            ic_std = float(ic_arr.std())

        icir = ic_mean / ic_std if ic_std > 1e-8 else 0.0
        ic_positive = float((ic_arr > 0).sum() / n)
        ic_abs_mean = float(np.abs(ic_arr).mean())

        return FactorStats(
            factor_name="",
            ic_mean=ic_mean,
            ic_std=ic_std,
            icir=icir,
            ic_positive_ratio=ic_positive,
            ic_abs_mean=ic_abs_mean,
            n_obs=n,
        )

    @staticmethod
    def compute_quantile_returns(
        factor_values: pl.DataFrame,
        forward_returns: pl.DataFrame,
        n_groups: int = 5,
    ) -> QuantileAnalysis:
        """计算分位数组合收益

        按因子值将股票分为 n_groups 组，计算各组平均收益。
        """
        dates = factor_values["date"].to_list()
        factor_cols = [c for c in factor_values.columns if c != "date"]
        return_cols = [c for c in forward_returns.columns if c != "date"]
        common_cols = [c for c in factor_cols if c in return_cols]

        group_returns_sum = {g: [] for g in range(1, n_groups + 1)}

        for i in range(len(dates)):
            fv_row = factor_values.row(i, named=True)
            fr_row = forward_returns.row(i, named=True)

            pairs = []
            for c in common_cols:
                fv = fv_row[c]
                fr = fr_row[c]
                if fv is not None and fr is not None:
                    pairs.append((c, float(fv), float(fr)))

            if len(pairs) < n_groups * 5:
                continue

            # 按 factor 值排序分组
            pairs.sort(key=lambda x: x[1])
            group_size = len(pairs) // n_groups

            for g in range(n_groups):
                start = g * group_size
                end = start + group_size if g < n_groups - 1 else len(pairs)
                group_returns = [p[2] for p in pairs[start:end]]
                if group_returns:
                    group_returns_sum[g + 1].append(np.mean(group_returns))

        result = QuantileAnalysis(factor_name="", n_groups=n_groups)
        for g, rets in group_returns_sum.items():
            if rets:
                result.group_returns[g] = float(np.mean(rets))

        # 多空收益 = 第1组 - 最后一组（假设 direction=1）
        if 1 in result.group_returns and n_groups in result.group_returns:
            result.long_short_return = result.group_returns[1] - result.group_returns[n_groups]

        return result

    @staticmethod
    def compute_ic_decay(
        factor_values: pl.DataFrame,
        returns: pl.DataFrame,
        horizons: list[int] | None = None,
    ) -> dict[int, float]:
        """计算 IC 衰减

        不同持有期的 IC 值，衡量因子预测能力的衰减速度。
        """
        horizons = horizons or [5, 10, 20, 40, 60]
        decay: dict[int, float] = {}

        for h in horizons:
            # 计算h日前向收益
            fwd_ret = _compute_forward_returns(returns, h)
            # 对齐日期
            common_dates = factor_values["date"].filter(
                factor_values["date"].is_in(fwd_ret["date"])
            )
            fv_aligned = factor_values.filter(pl.col("date").is_in(common_dates))
            fr_aligned = fwd_ret.filter(pl.col("date").is_in(common_dates))

            ic_df = FactorAnalyzer.compute_ic(fv_aligned, fr_aligned)
            stats = FactorAnalyzer.compute_icir(ic_df)
            decay[h] = stats.ic_mean

        return decay


def _compute_forward_returns(close: pl.DataFrame, horizon: int) -> pl.DataFrame:
    """计算 horizon 期前向收益

    Args:
        close: date × code 收盘价宽表
        horizon: 持有期

    Returns:
        date × code 前向收益宽表（每行是 t 时刻持有 horizon 天的收益）
    """
    date_col = close["date"]
    numeric = close.drop("date")
    # shift(-horizon) 取未来值
    future = numeric.shift(-horizon)
    fwd_ret = future / numeric - 1
    return fwd_ret.insert_column(0, date_col)


def compute_all_returns(close: pl.DataFrame, horizon: int = 20) -> pl.DataFrame:
    """便捷函数：计算前向收益"""
    return _compute_forward_returns(close, horizon)


__all__ = [
    "FactorAnalyzer",
    "FactorStats",
    "QuantileAnalysis",
    "compute_all_returns",
]
