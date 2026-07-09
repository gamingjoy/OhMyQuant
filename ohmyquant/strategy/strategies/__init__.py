"""策略实现

导入所有策略模块以触发 @register_strategy 装饰器注册。
"""
from __future__ import annotations

# 导入策略模块以触发注册（try/except 避免循环依赖）
try:
    from .ycj.v1.strategy import YCJStrategyV1  # noqa: F401
except ImportError:
    pass

try:
    from .ycj.v2.strategy import YCJStrategyV2  # noqa: F401
except ImportError:
    pass

try:
    from .dh.v1.strategy import DHStrategyV1  # noqa: F401
except ImportError:
    pass

try:
    from .etf.v1.strategy import ETFRotationV1  # noqa: F401
except ImportError:
    pass

try:
    from .etf.v2.strategy import ETFMixedV2  # noqa: F401
except ImportError:
    pass

try:
    from .dl.v1.strategy import DLStrategyV1  # noqa: F401
except ImportError:
    pass

try:
    from .rl.v1.strategy import RLStrategyV1  # noqa: F401
except ImportError:
    pass
