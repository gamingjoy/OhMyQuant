"""分配器实现

自动发现本目录下所有分配器模块。新增分配器：新建 .py + @register_allocator，无需修改本文件。
"""

from .equal_allocator import EqualAllocator

from ...core.discovery import discover_modules

discover_modules(__name__)


def create_allocator(config: dict | None = None):
    """工厂方法：根据配置创建分配器

    Args:
        config: 分配配置 dict，需包含 method 字段指定分配器类型。
                method 可选: equal
                未指定 method 时默认 equal

    Returns:
        BaseAllocator 实例
    """
    from ...core.plugin_system import PluginRegistry, PluginType

    cfg = config or {}
    method = cfg.get("method", "equal")
    return PluginRegistry.create(PluginType.ALLOCATOR, method, config=cfg)


__all__ = [
    "EqualAllocator",
    "create_allocator",
]
