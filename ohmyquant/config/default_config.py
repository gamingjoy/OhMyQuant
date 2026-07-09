"""默认配置

提供 OhMyQuant 的默认配置：
  - 全局配置
  - 回测配置
  - 数据配置
  - 策略配置
  - 日志配置

配置结构：
  - DEFAULT_CONFIG: 默认配置字典
  - ConfigLoader: 配置加载器
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

import polars as pl

from ..core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_CONFIG: Dict[str, Any] = {
    "global": {
        "project_name": "OhMyQuant",
        "version": "1.0.0",
        "log_level": "INFO",
        "log_format": "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
    },
    "backtest": {
        "start_date": "2020-01-01",
        "end_date": "2024-12-31",
        "initial_capital": 1000000.0,
        "benchmark": "000300.SH",
        "frequency": "daily",
        "slippage": 0.001,
        "transaction_cost": 0.0003,
        "tax_rate": 0.001,
    },
    "data": {
        "data_dir": "./data",
        "cache_dir": "./cache",
        "update_frequency": "daily",
        "sources": ["jqdata", "local_parquet"],
    },
    "strategy": {
        "default_strategy": "ycj",
        "default_version": "v1",
        "rebalance_frequency": "monthly",
        "max_positions": 50,
        "min_weight": 0.001,
        "max_weight": 0.1,
    },
    "analysis": {
        "risk_free_rate": 0.02,
        "confidence_level": 0.95,
        "rolling_window": 60,
    },
    "tracking": {
        "experiment_dir": "./experiments",
        "log_dir": "./logs",
        "enable_tracking": True,
    },
}


class ConfigLoader:
    """配置加载器"""

    def __init__(self, config_path: str | None = None):
        """初始化

        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path
        self.config = DEFAULT_CONFIG.copy()

        if config_path and os.path.exists(config_path):
            self._load_config(config_path)

    def _load_config(self, config_path: str) -> None:
        """加载配置文件

        Args:
            config_path: 配置文件路径
        """
        try:
            if config_path.endswith(".json"):
                with open(config_path, "r", encoding="utf-8") as f:
                    user_config = json.load(f)
            elif config_path.endswith(".yaml") or config_path.endswith(".yml"):
                try:
                    import yaml

                    with open(config_path, "r", encoding="utf-8") as f:
                        user_config = yaml.safe_load(f)
                except ImportError:
                    logger.warning("需要安装 PyYAML 来加载 YAML 配置")
                    return
            else:
                logger.warning(f"不支持的配置文件格式: {config_path}")
                return

            self._merge_config(self.config, user_config)
            logger.info(f"配置已加载: {config_path}")

        except Exception as e:
            logger.error(f"加载配置失败: {e}")

    def _merge_config(self, base: Dict[str, Any], override: Dict[str, Any]) -> None:
        """递归合并配置

        Args:
            base: 基础配置
            override: 覆盖配置
        """
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值

        Args:
            key: 配置键（支持点分隔，如 "backtest.start_date"）
            default: 默认值

        Returns:
            Any: 配置值
        """
        keys = key.split(".")
        value = self.config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, key: str, value: Any) -> None:
        """设置配置值

        Args:
            key: 配置键（支持点分隔）
            value: 配置值
        """
        keys = key.split(".")
        config = self.config

        for i, k in enumerate(keys[:-1]):
            if k not in config:
                config[k] = {}
            config = config[k]

        config[keys[-1]] = value

    def save(self, config_path: str) -> None:
        """保存配置到文件

        Args:
            config_path: 配置文件路径
        """
        try:
            os.makedirs(os.path.dirname(config_path), exist_ok=True)

            if config_path.endswith(".json"):
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(self.config, f, indent=2, ensure_ascii=False)
            elif config_path.endswith(".yaml") or config_path.endswith(".yml"):
                try:
                    import yaml

                    with open(config_path, "w", encoding="utf-8") as f:
                        yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True)
                except ImportError:
                    logger.warning("需要安装 PyYAML 来保存 YAML 配置")

            logger.info(f"配置已保存: {config_path}")

        except Exception as e:
            logger.error(f"保存配置失败: {e}")

    def get_backtest_config(self) -> Dict[str, Any]:
        """获取回测配置

        Returns:
            Dict: 回测配置
        """
        return self.config.get("backtest", {})

    def get_data_config(self) -> Dict[str, Any]:
        """获取数据配置

        Returns:
            Dict: 数据配置
        """
        return self.config.get("data", {})

    def get_strategy_config(self) -> Dict[str, Any]:
        """获取策略配置

        Returns:
            Dict: 策略配置
        """
        return self.config.get("strategy", {})


__all__ = ["DEFAULT_CONFIG", "ConfigLoader"]
