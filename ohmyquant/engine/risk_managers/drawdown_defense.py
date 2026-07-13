"""回撤防御风控管理器

根据当前回撤深度动态降低仓位，并检测崩盘信号。
移植 halo_index 的 compute_enhanced_drawdown_control 逻辑。

回撤分级:
  >18% → 30% 仓位
  >12% → 45% 仓位
  >8%  → 60% 仓位
  >4%  → 80% 仓位
  否则  → 100% 仓位
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


@register_risk_manager("drawdown")
class DrawdownDefenseRiskManager(BaseRiskManager):
    """回撤防御风控

    专注于最大回撤控制，适合保守型策略。
    """

    def compute_exposure(
        self,
        nav: pl.Series,
        daily_returns: pl.Series,
        current_idx: int,
        current_exposure: float,
        **kwargs,
    ) -> tuple[float, str]:
        if current_idx < 1:
            return 1.0, REGIME_WEAK_TREND

        target_exposure = self._compute_drawdown_exposure(nav, daily_returns, current_idx)
        regime, _ = self.detect_regime(daily_returns, current_idx)
        return target_exposure, regime

    def _compute_drawdown_exposure(
        self,
        nav: pl.Series,
        daily_returns: pl.Series,
        current_idx: int,
    ) -> float:
        """计算基于回撤的暴露度"""
        dd = self._compute_drawdown(nav, current_idx)
        abs_dd = abs(dd)

        # 回撤分级降仓
        if abs_dd > 0.18:
            target_exposure = 0.30
        elif abs_dd > 0.12:
            target_exposure = 0.45
        elif abs_dd > 0.08:
            target_exposure = 0.60
        elif abs_dd > 0.04:
            target_exposure = 0.80
        else:
            target_exposure = 1.0

        # 崩盘信号检测：近 5 日累计收益 < -5% 时额外惩罚
        if current_idx >= 5:
            recent_5d = self._slice(daily_returns, current_idx, 5)
            crash_signal = float(np.sum(recent_5d))
            if crash_signal < -0.05:
                crash_penalty = min(abs(crash_signal) / 0.10, 1.0)
                target_exposure *= 1.0 - 0.3 * crash_penalty

        # 20 日动量检查
        if current_idx >= 20:
            recent_20d = self._slice(daily_returns, current_idx, 20)
            momentum_20d = float(np.sum(recent_20d))
        else:
            momentum_20d = 0.0

        if target_exposure < 1.0:
            return max(0.15, target_exposure)

        # 小回撤 + 负动量 → 轻度降仓
        if abs_dd > 0.02 and momentum_20d <= 0:
            return max(0.70, 1.0 - abs_dd * 2)

        return 1.0

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

        # 崩盘检测：近 5 日累计收益
        if current_idx >= 5:
            recent_5d = self._slice(daily_returns, current_idx, 5)
            if float(np.sum(recent_5d)) < -0.05:
                return REGIME_HIGH_VOL, 0.8

        mean_ret = float(np.mean(hist)) * TRADING_DAYS
        pos_ratio = float(np.mean(hist > 0))
        if abs(mean_ret) > 0.15 and pos_ratio > 0.55:
            return REGIME_STRONG_TREND, min(abs(mean_ret) / 0.3, 1.0)
        elif pos_ratio > 0.45:
            return REGIME_WEAK_TREND, 0.6
        else:
            return REGIME_SIDEWAY, 0.5


__all__ = ["DrawdownDefenseRiskManager"]
