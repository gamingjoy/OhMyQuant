"""分配器实现"""
from .equal_allocator import EqualAllocator
from .hrp_allocator import HRPAllocator
from .icir_allocator import ICIRWeightedAllocator


def create_allocator(config: dict | None = None):
    """工厂方法：根据配置创建分配器

    Args:
        config: 分配配置 dict，需包含 method 字段指定分配器类型。
                method 可选: equal / hrp / icir_weighted
                未指定 method 时默认 equal（最简单）

    Returns:
        BaseAllocator 实例
    """
    from ...core.plugin_system import PluginRegistry, PluginType

    cfg = config or {}
    method = cfg.get("method", "equal")
    return PluginRegistry.create(PluginType.ALLOCATOR, method, config=cfg)


__all__ = [
    "EqualAllocator",
    "HRPAllocator",
    "ICIRWeightedAllocator",
    "create_allocator",
]
