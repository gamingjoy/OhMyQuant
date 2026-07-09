"""内置因子库

导入时自动注册所有内置因子到 PluginRegistry。
"""
from . import fundamental, momentum, reversal, technical, valuation, volatility, volume_price

__all__ = [
    "momentum",
    "reversal",
    "volatility",
    "volume_price",
    "valuation",
    "technical",
    "fundamental",
]
