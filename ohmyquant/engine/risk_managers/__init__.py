"""风控管理器实现

自动发现本目录下所有风控模块。新增风控器：新建 .py + @register_risk_manager，无需修改本文件。
下方显式导入仅用于向后兼容 re-export。
"""
from .cvar_manager import CVaRRiskManager
from .drawdown_defense import DrawdownDefenseRiskManager
from .regime_adaptive import RegimeAdaptiveRiskManager
from .vol_target import VolTargetRiskManager

from ...core.discovery import discover_modules

discover_modules(__name__)


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
