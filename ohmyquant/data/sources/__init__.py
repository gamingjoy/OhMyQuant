"""数据源实现

导入时自动发现并注册本目录下所有数据源模块。
新增数据源：在本目录下新建 .py，用 @register_data_source 装饰器注册，无需修改本文件。
"""
from ...core.discovery import discover_modules

discover_modules(__name__)

__all__: list[str] = []
