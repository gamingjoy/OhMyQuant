"""行业轮动策略 v66（v53 + regime-aware 北向资金因子）—— [FINAL]

状态: final
IS Sharpe 0.6677 (+6.5% vs v53), OOS与v53相同(熊市自动禁用北向因子)

v66 = v53 + hk_hold_ratio_change_5d + hk_hold_regime_aware
迭代: v64(w=1.0, IS+0.02但2022-0.24) → v65(w=0.3, IS-0.01) → v66(regime-aware, IS+0.04)
"""
from __future__ import annotations

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("industry_rotation", "v66")
class IndustryRotationStrategyV66(BaseStrategy):
    """行业轮动策略 industry_rotation_v66 (hk_hold_ra, iter)"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "IndustryRotationStrategyV66":
        if strategy_type != "industry_rotation" or version != "v66":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        base_config = cls._load_config_yaml(config)
        return cls(base_config)
