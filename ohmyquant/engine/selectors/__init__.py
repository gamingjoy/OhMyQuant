"""选股器实现

自动发现本目录下所有选股器模块。新增选股器：新建 .py + @register_selector，无需修改本文件。
"""

from ...core.discovery import discover_modules

discover_modules(__name__)


def create_selector(config: dict | None = None):
    """工厂方法：根据配置创建选股器"""
    from ...core.plugin_system import PluginRegistry, PluginType

    cfg = config or {}
    method = cfg.get("method", "industry_rotation")
    return PluginRegistry.create(PluginType.SELECTOR, method, config=cfg)


__all__ = [
    "create_selector",
]
