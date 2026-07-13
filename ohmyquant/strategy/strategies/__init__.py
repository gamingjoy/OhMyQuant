"""策略实现

自动发现并注册 strategies/ 下所有策略模块（含迭代版本目录 iterations/）。
新增策略：在 strategies/<type>/<version>/ 下新建 strategy.py + @register_strategy，无需修改本文件。
"""
from ...core.discovery import discover_modules

discover_modules(__name__)
