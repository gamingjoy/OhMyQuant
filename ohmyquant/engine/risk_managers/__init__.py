"""风控管理器实现"""
from .cvar_manager import CVaRRiskManager
from .drawdown_defense import DrawdownDefenseRiskManager
from .regime_adaptive import RegimeAdaptiveRiskManager
from .vol_target import VolTargetRiskManager


def create_risk_manager(config: dict | None = None):
    """工厂方法：根据配置创建风控管理器

    Args:
        config: 风控配置 dict，需包含 method 字段指定风控器类型。
                method 可选: vol_target / cvar / drawdown / regime_adaptive
                未指定 method 时默认 regime_adaptive（最全面）

    Returns:
        BaseRiskManager 实例
    """
    from ...core.plugin_system import PluginRegistry, PluginType

    cfg = config or {}
    method = cfg.get("method", "regime_adaptive")
    return PluginRegistry.create(PluginType.RISK_MANAGER, method, config=cfg)


__all__ = [
    "VolTargetRiskManager",
    "CVaRRiskManager",
    "DrawdownDefenseRiskManager",
    "RegimeAdaptiveRiskManager",
    "create_risk_manager",
]
