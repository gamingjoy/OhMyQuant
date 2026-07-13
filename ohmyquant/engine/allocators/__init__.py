"""分配器实现

自动发现本目录下所有分配器模块。新增分配器：新建 .py + @register_allocator，无需修改本文件。
下方显式导入仅用于向后兼容 re-export。
"""
from .equal_allocator import EqualAllocator
from .hrp_allocator import HRPAllocator
from .icir_allocator import ICIRWeightedAllocator

from ...core.discovery import discover_modules

discover_modules(__name__)


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
