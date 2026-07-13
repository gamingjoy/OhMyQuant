"""CVaR 风控管理器

基于条件风险价值（CVaR）的风控，当尾部风险超过阈值时降低暴露度。
移植 halo_index 的 compute_cvar_scale 逻辑。
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


@register_risk_manager("cvar")
class CVaRRiskManager(BaseRiskManager):
    """CVaR 风控管理器

    scale = vol_scale * (1 - cvar_penalty_strength * cvar_penalty)
    其中 vol_scale = target_vol / current_vol
    cvar_penalty = clip(|cvar| / |var_threshold|, 0, 1) ** 1.5  当 cvar < var_threshold
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

        scale = self._compute_cvar_scale(daily_returns, current_idx)
        regime, _ = self.detect_regime(daily_returns, current_idx)
        return scale, regime

    def _compute_cvar_scale(
        self,
        daily_returns: pl.Series,
        current_idx: int,
        lookback: int | None = None,
    ) -> float:
        """计算 CVaR 缩放因子"""
        lookback = lookback or self.lookback
        hist = self._slice(daily_returns, current_idx, lookback)

        if len(hist) < 20:
            if len(hist) >= 5:
                current_vol = self._annualized_vol(hist)
                if current_vol <= 0:
                    return 1.0
                return self._clip(self.target_vol / current_vol, 0.5, 1.5)
            return 1.0

        current_vol = self._annualized_vol(hist)
        if current_vol <= 0:
            return 1.0

        cvar = self._compute_cvar(hist, alpha=0.05)
        var_threshold = -self.target_vol / np.sqrt(TRADING_DAYS) * self.cvar_limit_factor
        vol_scale = self.target_vol / current_vol

        if cvar < var_threshold:
            cvar_ratio = abs(cvar) / abs(var_threshold)
            cvar_penalty = min(1.0, cvar_ratio ** 1.5)
            scale = vol_scale * (1.0 - self.cvar_penalty_strength * cvar_penalty)
        else:
            scale = vol_scale

        # 长短期平滑
        if current_idx >= 120:
            long_hist = self._slice(daily_returns, current_idx, 120)
            if len(long_hist) >= 60:
                long_vol = self._annualized_vol(long_hist)
                if long_vol > 0:
                    long_scale = self.target_vol / long_vol
                else:
                    long_scale = scale
                if scale < 1.0:
                    scale = 0.7 * scale + 0.3 * long_scale
                else:
                    scale = 0.3 * scale + 0.7 * long_scale

        return self._clip(scale, 0.5, 1.5)

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

        cvar = self._compute_cvar(hist, alpha=0.05)
        if cvar < self.var_threshold:
            return REGIME_HIGH_VOL, 0.7

        mean_ret = float(np.mean(hist)) * TRADING_DAYS
        pos_ratio = float(np.mean(hist > 0))
        if abs(mean_ret) > 0.15 and pos_ratio > 0.55:
            return REGIME_STRONG_TREND, min(abs(mean_ret) / 0.3, 1.0)
        elif pos_ratio > 0.45:
            return REGIME_WEAK_TREND, 0.6
        else:
            return REGIME_SIDEWAY, 0.5


__all__ = ["CVaRRiskManager"]
