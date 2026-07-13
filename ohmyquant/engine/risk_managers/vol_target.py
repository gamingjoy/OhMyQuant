"""波动率目标风控管理器

简单的波动率目标策略：根据实现波动率调整暴露度。
当实现波动率高于目标时降低仓位，低于目标时提高仓位。
"""
from __future__ import annotations

import numpy as np
import polars as pl

from ...core.plugin_system import register_risk_manager
from ..risk import (
    BaseRiskManager,
    REGIME_HIGH_VOL,
    REGIME_SIDEWAY,
    REGIME_STRONG_TREND,
    REGIME_WEAK_TREND,
    TRADING_DAYS,
)


@register_risk_manager("vol_target")
class VolTargetRiskManager(BaseRiskManager):
    """波动率目标风控

    scale = clip(target_vol / current_vol, min_exposure_scale, 1.5)
    """

    def compute_exposure(
        self,
        nav: pl.Series,
        daily_returns: pl.Series,
        current_idx: int,
        current_exposure: float,
        **kwargs,
    ) -> tuple[float, str]:
        if current_idx < 20:
            return 1.0, REGIME_WEAK_TREND

        hist = self._slice(daily_returns, current_idx, self.lookback)
        if len(hist) < 10:
            return 1.0, REGIME_WEAK_TREND

        current_vol = self._annualized_vol(hist)
        if current_vol <= 0:
            return 1.0, REGIME_WEAK_TREND

        scale = self._clip(self.target_vol / current_vol, self.min_exposure_scale, 1.5)

        regime, _ = self.detect_regime(daily_returns, current_idx)
        return scale, regime

    def detect_regime(
        self,
        daily_returns: pl.Series,
        current_idx: int,
        lookback: int | None = None,
    ) -> tuple[str, float]:
        lookback = lookback or self.lookback
        if current_idx < lookback + 20:
            return REGIME_WEAK_TREND, 0.5

        hist = self._slice(daily_returns, current_idx, lookback)
        if len(hist) < 20:
            return REGIME_WEAK_TREND, 0.5

        current_vol = self._annualized_vol(hist)
        high_vol_threshold = self.target_vol * 1.3

        if current_vol > high_vol_threshold:
            confidence = min(
                abs(current_vol - high_vol_threshold) / high_vol_threshold + 0.5, 1.0
            )
            return REGIME_HIGH_VOL, float(confidence)

        # 简单趋势判断：正收益比例
        pos_ratio = float(np.mean(hist > 0))
        mean_ret = float(np.mean(hist)) * TRADING_DAYS
        if abs(mean_ret) > 0.15 and pos_ratio > 0.55:
            return REGIME_STRONG_TREND, min(abs(mean_ret) / 0.3, 1.0)
        elif pos_ratio > 0.45:
            return REGIME_WEAK_TREND, 0.6
        else:
            return REGIME_SIDEWAY, 0.5


__all__ = ["VolTargetRiskManager"]
