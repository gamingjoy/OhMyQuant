"""插件注册系统

框架所有可插拔组件（策略/因子/选股器/风控/分配器/调仓器/数据源/成本模型）
通过统一注册系统管理。

注册方式：
  1. 装饰器：@register_factor("mom_1m")  /  @register_selector("icir")
  2. 运行时：PluginRegistry.register(...)(klass)
  3. 外部包：通过 pyproject.toml 的 [project.entry-points."ohmyquant.plugins"] 声明

使用方式：
  PluginRegistry.create(PluginType.SELECTOR, "icir", config={...})
  PluginRegistry.get(PluginType.FACTOR, "mom_1m")
  PluginRegistry.list_plugins(PluginType.FACTOR)
"""
from __future__ import annotations

import enum
import importlib
from dataclasses import dataclass, field
from typing import Any, Callable, ClassVar

from pydantic import BaseModel

from .exceptions import PluginNotFoundError
from .logging import get_logger

logger = get_logger(__name__)


class PluginType(enum.Enum):
    """插件类型枚举"""

    STRATEGY = "strategy"
    FACTOR = "factor"
    SELECTOR = "selector"
    RISK_MANAGER = "risk_manager"
    ALLOCATOR = "allocator"
    REBALANCER = "rebalancer"
    DATA_SOURCE = "data_source"
    COST_MODEL = "cost_model"
    SCHEDULER = "scheduler"
    MODEL = "model"


@dataclass
class PluginMeta:
    """插件元数据"""

    name: str
    version: str = "1.0"
    description: str = ""
    author: str = ""
    category: str = ""
    config_schema: type[BaseModel] | None = None
    tags: list[str] = field(default_factory=list)


class PluginRegistry:
    """中央插件注册表（类级单例）

    所有插件注册信息存储在类变量 _registries 中，
    进程内全局可见。
    """

    _registries: ClassVar[dict[PluginType, dict[str, tuple[type, PluginMeta]]]] = {}
    _discovered: ClassVar[bool] = False
    _builtin_discovered: ClassVar[bool] = False

    # 内置插件包清单：discover_builtin 会导入这些包，各包 __init__ 再自扫描子模块
    _BUILTIN_PLUGIN_PACKAGES: ClassVar[tuple[str, ...]] = (
        "ohmyquant.data.sources",
        "ohmyquant.factors.builtin",
        "ohmyquant.engine.selectors",
        "ohmyquant.engine.allocators",
        "ohmyquant.engine.risk_managers",
        "ohmyquant.execution.cost_model",
        "ohmyquant.execution.scheduler",
        "ohmyquant.execution.rebalancer",
        "ohmyquant.models.ml",
        "ohmyquant.models.dl",
        "ohmyquant.models.rl",
        "ohmyquant.strategy.strategies",
    )

    @classmethod
    def register(
        cls,
        plugin_type: PluginType,
        name: str | None = None,
        meta: PluginMeta | None = None,
    ) -> Callable[[type], type]:
        """装饰器：注册插件类

        Args:
            plugin_type: 插件类型
            name: 注册名，None 则用类名
            meta: 元数据，None 则自动构建
        """

        def decorator(klass: type) -> type:
            plugin_name = name or klass.__name__
            meta_obj = meta or PluginMeta(
                name=plugin_name,
                description=(klass.__doc__ or "").strip().split("\n")[0],
            )
            registry = cls._registries.setdefault(plugin_type, {})
            if plugin_name in registry:
                logger.debug(f"插件已存在，覆盖注册: {plugin_type.value}/{plugin_name}")
            registry[plugin_name] = (klass, meta_obj)
            logger.debug(f"注册插件: {plugin_type.value}/{plugin_name} -> {klass.__name__}")
            return klass

        return decorator

    @classmethod
    def get(cls, plugin_type: PluginType, name: str) -> type:
        """获取插件类（不实例化）"""
        cls.discover_builtin()
        registry = cls._registries.get(plugin_type, {})
        if name not in registry:
            available = list(registry.keys())
            raise PluginNotFoundError(plugin_type.value, name, available)
        return registry[name][0]

    @classmethod
    def get_meta(cls, plugin_type: PluginType, name: str) -> PluginMeta:
        """获取插件元数据"""
        registry = cls._registries.get(plugin_type, {})
        if name not in registry:
            available = list(registry.keys())
            raise PluginNotFoundError(plugin_type.value, name, available)
        return registry[name][1]

    @classmethod
    def create(
        cls,
        plugin_type: PluginType,
        name: str,
        config: dict | BaseModel | None = None,
        **kwargs: Any,
    ) -> Any:
        """创建插件实例

        Args:
            plugin_type: 插件类型
            name: 注册名
            config: 配置 dict 或 Pydantic 模型，会传给插件构造函数的 config 参数
            **kwargs: 额外构造参数
        """
        klass = cls.get(plugin_type, name)
        meta = cls.get_meta(plugin_type, name)

        # Pydantic 校验配置
        if meta.config_schema is not None and config is not None:
            if isinstance(config, BaseModel):
                config = config.model_dump()
            config = meta.config_schema(**config).model_dump()
        elif isinstance(config, BaseModel):
            config = config.model_dump()

        # 尝试带 config 参数构造
        try:
            return klass(config=config, **kwargs)
        except TypeError:
            # 插件构造函数不接受 config 参数
            return klass(**kwargs)

    @classmethod
    def list_plugins(cls, plugin_type: PluginType, category: str | None = None) -> list[str]:
        """列出已注册的插件名

        Args:
            plugin_type: 插件类型
            category: 可选类别过滤
        """
        cls.discover_builtin()
        registry = cls._registries.get(plugin_type, {})
        if category is None:
            return list(registry.keys())
        return [
            name
            for name, (_, meta) in registry.items()
            if meta.category == category
        ]

    @classmethod
    def list_all(cls) -> dict[str, list[str]]:
        """列出所有插件"""
        cls.discover_builtin()
        return {
            pt.value: list(reg.keys())
            for pt, reg in cls._registries.items()
            if reg
        }

    @classmethod
    def unregister(cls, plugin_type: PluginType, name: str) -> bool:
        """取消注册"""
        registry = cls._registries.get(plugin_type, {})
        return registry.pop(name, None) is not None

    @classmethod
    def clear(cls, plugin_type: PluginType | None = None) -> None:
        """清空注册表"""
        if plugin_type is None:
            cls._registries.clear()
        else:
            cls._registries.pop(plugin_type, None)

    @classmethod
    def discover(cls) -> None:
        """通过 importlib.metadata entry_points 发现外部插件

        外部包在 pyproject.toml 中声明:
            [project.entry-points."ohmyquant.plugins"]
            my_plugin = "my_package.plugins"
        """
        if cls._discovered:
            return
        cls._discovered = True

        try:
            from importlib.metadata import entry_points
        except ImportError:
            return

        try:
            eps = entry_points(group="ohmyquant.plugins")
        except TypeError:
            # Python 3.9 兼容
            eps = entry_points().get("ohmyquant.plugins", [])

        for ep in eps:
            try:
                ep.load()
                logger.info(f"加载外部插件: {ep.name} from {ep.value}")
            except Exception as e:
                logger.warning(f"加载外部插件失败 {ep.name}: {e}")

    @classmethod
    def discover_builtin(cls) -> None:
        """发现并注册所有内置插件包。幂等。

        逐个导入 _BUILTIN_PLUGIN_PACKAGES 中的包；各包的 __init__.py 会调用
        discover_modules(__name__) 自扫描子模块，触发 @register_* 装饰器。
        新增内置插件只需把 .py 放进对应包，无需修改任何 __init__.py。
        """
        if cls._builtin_discovered:
            return
        cls._builtin_discovered = True
        from .discovery import discover_modules

        for pkg in cls._BUILTIN_PLUGIN_PACKAGES:
            try:
                # 导入包本身（触发其 __init__ 的自扫描）；对单模块包用 discover_modules
                importlib.import_module(pkg)
            except ImportError:
                # 某些包可能是单模块而非包，回退到 discover_modules
                discover_modules(pkg.rsplit(".", 1)[0]) if "." in pkg else None


# ---------------------------------------------------------------------------
# 便捷装饰器
# ---------------------------------------------------------------------------

def register_factor(name: str | None = None, category: str = "", meta: PluginMeta | None = None):
    """注册因子

    @register_factor("mom_1m", category="momentum")
    class Momentum1M(Factor): ...
    """
    if meta is None and category:
        meta = PluginMeta(name=name or "", category=category)
    elif meta is not None and category:
        meta.category = category
    return PluginRegistry.register(PluginType.FACTOR, name, meta)


def register_selector(name: str | None = None, meta: PluginMeta | None = None):
    """注册选股器"""
    return PluginRegistry.register(PluginType.SELECTOR, name, meta)


def register_risk_manager(name: str | None = None, meta: PluginMeta | None = None):
    """注册风控管理器"""
    return PluginRegistry.register(PluginType.RISK_MANAGER, name, meta)


def register_allocator(name: str | None = None, meta: PluginMeta | None = None):
    """注册分配器"""
    return PluginRegistry.register(PluginType.ALLOCATOR, name, meta)


def register_rebalancer(name: str | None = None, meta: PluginMeta | None = None):
    """注册调仓器"""
    return PluginRegistry.register(PluginType.REBALANCER, name, meta)


def register_data_source(name: str | None = None, meta: PluginMeta | None = None):
    """注册数据源"""
    return PluginRegistry.register(PluginType.DATA_SOURCE, name, meta)


def register_cost_model(name: str | None = None, meta: PluginMeta | None = None):
    """注册成本模型"""
    return PluginRegistry.register(PluginType.COST_MODEL, name, meta)


def register_scheduler(name: str | None = None, meta: PluginMeta | None = None):
    """注册调度器"""
    return PluginRegistry.register(PluginType.SCHEDULER, name, meta)


def register_strategy(strategy_type: str, version: str):
    """注册策略

    Args:
        strategy_type: 策略类型（ycj/dh）
        version: 版本号（v1/v2）

    Usage:
        @register_strategy("ycj", "v1")
        class YCJStrategyV1(BaseStrategy):
            ...
    """
    name = f"{strategy_type}_{version}"
    return PluginRegistry.register(PluginType.STRATEGY, name)


def register_model(name: str | None = None, meta: PluginMeta | None = None):
    """注册 ML/DL/RL 模型

    Usage:
        @register_model("lightgbm_ltr")
        class LightGBMModel(Model): ...
    """
    return PluginRegistry.register(PluginType.MODEL, name, meta)


__all__ = [
    "PluginType",
    "PluginMeta",
    "PluginRegistry",
    "register_factor",
    "register_selector",
    "register_risk_manager",
    "register_allocator",
    "register_rebalancer",
    "register_data_source",
    "register_cost_model",
    "register_scheduler",
    "register_strategy",
    "register_model",
]
