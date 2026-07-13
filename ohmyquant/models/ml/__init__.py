"""机器学习模型（LightGBM / XGBoost）

自动发现本目录下所有模型模块。新增模型：新建 .py + @register_model，无需修改本文件。
"""
from ...core.discovery import discover_modules

discover_modules(__name__)
