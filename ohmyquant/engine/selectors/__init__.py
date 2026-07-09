"""选股器实现"""
from .hybrid_selector import AdaptiveICIRSelector, HybridSelector
from .icir_selector import ICIRSelector
from .momentum_selector import MomentumSelector

try:
    from .ml_selector import MLSelector
except ImportError:
    MLSelector = None  # type: ignore

try:
    from .model_selector import ModelSelector
except ImportError:
    ModelSelector = None  # type: ignore

try:
    from .rl_selector import RLSelector
except ImportError:
    RLSelector = None  # type: ignore


def create_selector(config: dict | None = None):
    """工厂方法：根据配置创建选股器"""
    from ...core.plugin_system import PluginRegistry, PluginType

    cfg = config or {}
    method = cfg.get("method", "icir")
    return PluginRegistry.create(PluginType.SELECTOR, method, config=cfg)


__all__ = [
    "ICIRSelector",
    "MomentumSelector",
    "HybridSelector",
    "AdaptiveICIRSelector",
    "MLSelector",
    "ModelSelector",
    "RLSelector",
    "create_selector",
]
