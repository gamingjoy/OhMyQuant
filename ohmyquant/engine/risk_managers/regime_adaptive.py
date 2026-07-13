"""Regime-Adaptive 综合风控管理器（默认主力风控）

集成 regime 检测 + 波动率目标 + CVaR + 趋势暴露 + 回撤控制 + 尾部风险。
移植 halo_index 的 RiskManager 完整逻辑到 polars。

综合暴露度公式:
  effective_scale = vol_scale * base_exposure * proactive_scale

其中:
  vol_scale = compute_cvar_scale（波动率目标 + CVaR 惩罚 + 长短期平滑）
  base_exposure = compute_regime_adaptive_trend_exposure（regime 基础暴露 + MA120 过滤）
  proactive_scale = managed_vol_scale * tail_risk_scale（管理波动率 × 尾部风险）
"""
from __future__ import annotations

import numpy as np
import polars as pl

from ...core.logging import get_logger
from ...core.plugin_system import register_risk_manager
from ..risk import (
    BaseRiskManager,
    REGIME_HIGH_VOL,
    REGIME_SIDEWAY,
    REGIME_STRONG_TREND,
    REGIME_WEAK_TREND,
    TRADING_DAYS,
)

logger = get_logger(__name__)


@register_risk_manager("regime_adaptive")
class RegimeAdaptiveRiskManager(BaseRiskManager):
    """Regime-Adaptive 综合风控

    最全面的风控器，整合多种风险信号。
    对应 halo_index 的 RiskManager 完整实现。
    """

    def compute_exposure(
        self,
        nav: pl.Series,
        daily_returns: pl.Series,
        current_idx: int,
        current_exposure: float,
        **kwargs,
    ) -> tuple[float, str]:
        return self._compute_composite_exposure(
            nav, daily_returns, current_idx, current_exposure
        )

    # ------------------------------------------------------------------
    # 市场状态检测
    # ------------------------------------------------------------------

    def detect_regime(
        self,
        daily_returns: pl.Series,
        current_idx: int,
        lookback: int | None = None,
    ) -> tuple[str, float]:
        """检测市场状态

        基于 vol + 趋势斜率 + MA20/MA40 + 阳线比例判断
        """
        lookback = lookback or self.lookback
        if current_idx < lookback + 20:
            return REGIME_WEAK_TREND, 0.5

        hist = self._slice(daily_returns, current_idx, lookback)
        if len(hist) < 40:
            return REGIME_WEAK_TREND, 0.5

        current_vol = self._annualized_vol(hist)

        # 净值近似与趋势斜率
        nav_approx = np.cumprod(1 + hist)
        x = np.arange(len(nav_approx))
        if len(x) < 10:
            return REGIME_WEAK_TREND, 0.5

        slope = np.polyfit(x, nav_approx, 1)[0]
        trend_strength = (
            slope / nav_approx[0] * TRADING_DAYS if nav_approx[0] > 0 else 0
        )

        # 移动均线
        ma20 = self._rolling_mean(nav_approx, 20)
        ma40 = self._rolling_mean(nav_approx, min(40, len(nav_approx)))
        above_ma20 = (
            nav_approx[-1] > ma20[-1] if not np.isnan(ma20[-1]) else True
        )
        above_ma40 = (
            nav_approx[-1] > ma40[-1] if not np.isnan(ma40[-1]) else True
        )
        pos_days = float(np.mean(hist > 0))

        high_vol_threshold = self.target_vol * 1.3
        if current_vol > high_vol_threshold:
            regime = REGIME_HIGH_VOL
            confidence = min(
                abs(current_vol - high_vol_threshold) / high_vol_threshold + 0.5, 1.0
            )
        elif abs(trend_strength) > 0.15 and above_ma20 and above_ma40:
            regime = REGIME_STRONG_TREND
            confidence = min(abs(trend_strength) / 0.3, 1.0)
        elif above_ma20 or above_ma40:
            regime = REGIME_WEAK_TREND
            confidence = 0.6
        else:
            regime = REGIME_SIDEWAY
            confidence = min(1.0 - pos_days + 0.3, 0.9) if pos_days < 0.5 else 0.5

        return regime, float(confidence)

    # ------------------------------------------------------------------
    # CVaR 缩放
    # ------------------------------------------------------------------

    def _compute_cvar_scale(
        self,
        daily_returns: pl.Series,
        current_idx: int,
        lookback: int | None = None,
    ) -> float:
        """波动率目标 + CVaR 惩罚 + 长短期平滑"""
        lookback = lookback or self.lookback
        hist = self._slice(daily_returns, current_idx, lookback)

        if len(hist) < 40:
            if len(hist) >= 20:
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

    # ------------------------------------------------------------------
    # 动态波动率目标
    # ------------------------------------------------------------------

    def _compute_dynamic_vol_target(
        self,
        daily_returns: pl.Series,
        current_idx: int,
        base_target: float | None = None,
        regime: str | None = None,
    ) -> float:
        """根据 regime 动态调整目标波动率"""
        base_target = base_target or self.target_vol
        hist = self._slice(daily_returns, current_idx, self.lookback)
        if len(hist) < 20:
            return base_target

        current_vol = self._annualized_vol(hist)
        if regime == REGIME_HIGH_VOL:
            return base_target * 0.85
        elif regime == REGIME_SIDEWAY:
            return base_target * 0.95
        elif regime == REGIME_STRONG_TREND:
            if current_vol < base_target * 0.8:
                return base_target * 1.15
            return base_target
        else:  # weak_trend
            if current_vol < base_target * 0.7:
                return base_target * 1.1
            elif current_vol > base_target * 1.5:
                return base_target * 0.8
            return base_target

    # ------------------------------------------------------------------
    # Regime 自适应趋势暴露
    # ------------------------------------------------------------------

    def _compute_regime_adaptive_trend_exposure(
        self,
        daily_returns: pl.Series,
        current_idx: int,
    ) -> float:
        """根据 regime 设定基础暴露度 + MA120 趋势过滤"""
        regime, _ = self.detect_regime(daily_returns, current_idx)

        if regime == REGIME_STRONG_TREND:
            base_exposure = 1.0
        elif regime == REGIME_WEAK_TREND:
            base_exposure = 0.95
        elif regime == REGIME_SIDEWAY:
            base_exposure = 0.85
        elif regime == REGIME_HIGH_VOL:
            base_exposure = 0.75
        else:
            base_exposure = 0.9

        # MA120 趋势过滤
        if current_idx >= 120:
            hist = self._slice(daily_returns, current_idx, current_idx)
            if len(hist) >= 120:
                nav_approx = np.cumprod(1 + hist)
                ma120 = self._rolling_mean(nav_approx, 120)
                if not np.isnan(ma120[-1]) and ma120[-1] > 0:
                    price_vs_ma = (nav_approx[-1] - ma120[-1]) / ma120[-1]
                    if price_vs_ma < -0.05:
                        base_exposure *= 0.85
                    elif price_vs_ma < -0.03:
                        base_exposure *= 0.92

        return self._clip(base_exposure, 0.4, 1.0)

    # ------------------------------------------------------------------
    # 回撤控制
    # ------------------------------------------------------------------

    def _compute_enhanced_drawdown_control(
        self,
        nav: pl.Series,
        current_idx: int,
        daily_returns: pl.Series,
    ) -> float:
        """回撤分级降仓 + 崩盘信号"""
        if current_idx < 1:
            return 1.0

        dd = self._compute_drawdown(nav, current_idx)
        abs_dd = abs(dd)

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

        # 崩盘信号
        if current_idx >= 5:
            recent_5d = self._slice(daily_returns, current_idx, 5)
            crash_signal = float(np.sum(recent_5d))
            if crash_signal < -0.05:
                crash_penalty = min(abs(crash_signal) / 0.10, 1.0)
                target_exposure *= 1.0 - 0.3 * crash_penalty

        if target_exposure < 1.0:
            return max(0.15, target_exposure)

        # 小回撤 + 负动量
        if current_idx >= 20:
            recent_20d = self._slice(daily_returns, current_idx, 20)
            momentum_20d = float(np.sum(recent_20d))
            if abs_dd > 0.02 and momentum_20d <= 0:
                return max(0.70, 1.0 - abs_dd * 2)

        return 1.0

    # ------------------------------------------------------------------
    # 管理波动率
    # ------------------------------------------------------------------

    def _compute_managed_vol_scale(
        self,
        daily_returns: pl.Series,
        current_idx: int,
    ) -> float:
        """管理波动率模式缩放"""
        if current_idx < 60:
            return 1.0
        recent_ret = self._slice(daily_returns, current_idx, 60)
        if len(recent_ret) < 60:
            return 1.0

        # 20 日滚动波动率
        rolling_vol = self._rolling_std(recent_ret, 20) * np.sqrt(TRADING_DAYS)
        rolling_vol_clean = rolling_vol[~np.isnan(rolling_vol)]
        if len(rolling_vol_clean) < 10:
            return 1.0
        short_vol_ma = float(np.mean(rolling_vol_clean))
        if short_vol_ma <= 0:
            return 1.0

        if self.vol_trend_mode == "managed_vol":
            mvs = self.target_vol / short_vol_ma
            mvs = np.clip(mvs, 0.5, 1.2)
            return 1.0 + (mvs - 1.0) * self.vol_trend_strength
        elif self.vol_trend_mode == "trend":
            long_vol = self._annualized_vol(recent_ret)
            if long_vol <= 0:
                return 1.0
            vol_ratio = short_vol_ma / long_vol
            if vol_ratio > 1.5:
                base = 0.55
            elif vol_ratio > 1.3:
                base = 0.70
            elif vol_ratio > 1.15:
                base = 0.85
            elif vol_ratio > 1.0:
                base = 0.95
            elif vol_ratio < 0.7:
                base = 1.10
            elif vol_ratio < 0.85:
                base = 1.05
            else:
                base = 1.0
            return 1.0 + (base - 1.0) * self.vol_trend_strength
        return 1.0

    # ------------------------------------------------------------------
    # 尾部风险
    # ------------------------------------------------------------------

    def _compute_tail_risk_scale(
        self,
        daily_returns: pl.Series,
        current_idx: int,
    ) -> float:
        """VaR/CVaR 尾部风险缩放"""
        if self.tail_risk_strength <= 0:
            return 1.0
        if current_idx < self.lookback:
            return 1.0

        hist = self._slice(daily_returns, current_idx, self.lookback)
        if len(hist) < 20:
            return 1.0

        var_95 = self._compute_var(hist, alpha=0.05)
        tail_mask = hist <= var_95
        if tail_mask.sum() > 0:
            cvar_95 = float(np.mean(hist[tail_mask]))
        else:
            cvar_95 = var_95

        if cvar_95 < self.var_threshold:
            excess = abs(cvar_95 - self.var_threshold) / abs(self.var_threshold)
            return max(0.5, 1.0 - self.tail_risk_strength * excess)
        return 1.0

    # ------------------------------------------------------------------
    # 综合暴露度
    # ------------------------------------------------------------------

    def _compute_composite_exposure(
        self,
        nav: pl.Series,
        daily_returns: pl.Series,
        current_idx: int,
        current_exposure: float,
    ) -> tuple[float, str]:
        """综合所有信号计算有效暴露度

        effective_scale = vol_scale * base_exposure * proactive_scale
        """
        regime, _ = self.detect_regime(daily_returns, current_idx)

        # 1. 动态目标波动率
        effective_target = self._compute_dynamic_vol_target(
            daily_returns, current_idx, base_target=self.target_vol, regime=regime
        )

        # 2. CVaR 缩放（使用动态目标）
        original_target = self.target_vol
        self.target_vol = effective_target
        vol_scale = self._compute_cvar_scale(daily_returns, current_idx)
        self.target_vol = original_target

        # 3. Regime 自适应趋势暴露
        base_exposure = self._compute_regime_adaptive_trend_exposure(
            daily_returns, current_idx
        )

        # 4. 回撤控制（取与当前暴露度的较小值）
        dd_exposure = self._compute_enhanced_drawdown_control(
            nav, current_idx, daily_returns
        )
        if dd_exposure < current_exposure:
            current_exposure = dd_exposure
        else:
            # 缓慢恢复
            if current_idx > 0:
                nav_arr = nav.to_numpy()
                cummax = np.maximum.accumulate(nav_arr[:current_idx])
                if len(cummax) > 0 and cummax[-1] > 0:
                    dd_from_hwm = abs((nav_arr[current_idx - 1] - cummax[-1]) / cummax[-1])
                else:
                    dd_from_hwm = 0.0
                proximity = max(0.0, 1.0 - dd_from_hwm / 0.10)
                has_momentum = self._has_positive_momentum(daily_returns, current_idx)
                if has_momentum:
                    recovery_speed = 0.01 + 0.04 * proximity
                else:
                    recovery_speed = 0.005 + 0.015 * proximity
                current_exposure = min(current_exposure + recovery_speed, dd_exposure)

        base_exposure = max(0.7, base_exposure * current_exposure)

        # 5. 主动缩放：管理波动率 × 尾部风险
        managed_vol_scale = self._compute_managed_vol_scale(daily_returns, current_idx)
        tail_scale = self._compute_tail_risk_scale(daily_returns, current_idx)
        proactive_scale = managed_vol_scale * tail_scale
        proactive_scale = float(np.clip(proactive_scale, 0.3, 1.3))

        # 6. 综合
        effective_scale = vol_scale * base_exposure * proactive_scale
        effective_scale = float(np.clip(effective_scale, 0.15, 1.5))

        return effective_scale, regime

    def _has_positive_momentum(
        self, daily_returns: pl.Series, current_idx: int, window: int = 20
    ) -> bool:
        if current_idx < window:
            return True
        recent = self._slice(daily_returns, current_idx, window)
        return float(np.sum(recent)) > 0

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _rolling_mean(arr: np.ndarray, window: int) -> np.ndarray:
        """一维滚动均值（不填充前 window-1 个为 NaN）"""
        if len(arr) < window:
            return np.full(len(arr), np.nan)
        cumsum = np.cumsum(np.insert(arr, 0, 0))
        result = np.full(len(arr), np.nan)
        result[window - 1:] = (cumsum[window:] - cumsum[:-window]) / window
        return result

    @staticmethod
    def _rolling_std(arr: np.ndarray, window: int) -> np.ndarray:
        """一维滚动标准差"""
        if len(arr) < window:
            return np.full(len(arr), np.nan)
        result = np.full(len(arr), np.nan)
        for i in range(window - 1, len(arr)):
            result[i] = float(np.std(arr[i - window + 1 : i + 1], ddof=1))
        return result


__all__ = ["RegimeAdaptiveRiskManager"]
