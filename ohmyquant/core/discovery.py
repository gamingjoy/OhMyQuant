"""插件自动发现

通过扫描包目录自动导入所有子模块，触发 @register_* 装饰器注册。
新增插件只需把 .py 放进对应包，无需修改 __init__.py —— 导入包时即自动发现并注册。

用法：
    from ohmyquant.core.discovery import discover_modules
    discover_modules("ohmyquant.factors.builtin")  # 扫描并注册该包下所有因子模块
"""
from __future__ import annotations

import importlib
import pkgutil

from .logging import get_logger

logger = get_logger(__name__)


def discover_modules(package: str) -> int:
    """扫描一个包并导入其所有子模块，触发装饰器注册。

    递归遍历包目录（pkgutil.walk_packages），逐个 importlib.import_module。
    每个模块独立处理：ImportError 视为可选依赖缺失而静默跳过，
    其他异常记 warning 后跳过，不中断整体发现流程。

    Args:
        package: 包的完整 dotted 路径，如 "ohmyquant.factors.builtin"

    Returns:
        int: 成功导入的子模块数
    """
    try:
        pkg = importlib.import_module(package)
    except ImportError as e:
        logger.debug(f"发现包失败 {package}: {e}")
        return 0

    pkg_path = getattr(pkg, "__path__", None)
    if not pkg_path:
        return 0

    count = 0
    for _finder, name, _ispkg in pkgutil.walk_packages(pkg_path, prefix=f"{package}."):
        try:
            importlib.import_module(name)
            count += 1
        except ImportError as e:
            logger.debug(f"跳过模块（可选依赖缺失）{name}: {e}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"导入模块失败 {name}: {e}")

    if count:
        logger.debug(f"插件包 {package}: 已发现 {count} 个模块")
    return count


__all__ = ["discover_modules"]
