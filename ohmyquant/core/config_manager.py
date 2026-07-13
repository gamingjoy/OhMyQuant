"""层次化配置管理器

基于 OmegaConf 实现三层配置合并：
  全局默认 (config/global_defaults.yaml)
    → 策略版本 (strategies/ycj/v2/config.yaml)
    → 运行时覆盖 (dict)

合并后通过 Pydantic v2 模型校验，返回 StrategyConfig 对象。
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml
from omegaconf import OmegaConf

from .config_models import StrategyConfig
from .exceptions import ConfigError, StrategyVersionNotFoundError
from .logging import get_logger

logger = get_logger(__name__)


def _deep_merge(base: dict, override: dict) -> dict:
    """深度合并两个 dict，override 覆盖 base"""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


class ConfigManager:
    """层次化配置管理器

    用法:
        mgr = ConfigManager()
        config = mgr.build_config("ycj", "v2")
        # 或带运行时覆盖
        config = mgr.build_config("ycj", "v2", overrides={"selection": {"top_n": 20}})
    """

    def __init__(self, project_root: str | Path | None = None):
        """初始化配置管理器

        Args:
            project_root: 项目根目录，None 则自动推断
        """
        if project_root is None:
            project_root = self._infer_project_root()
        self.project_root = Path(project_root)
        self._global_defaults: dict | None = None

    @staticmethod
    def _infer_project_root() -> Path:
        """推断项目根目录"""
        # 从当前文件向上找到 ohmyquant 包的父目录
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "ohmyquant").is_dir() and (parent / "config").is_dir():
                return parent
            if parent.name == "ohmyquant":
                return parent.parent
        # fallback: 当前工作目录
        return Path.cwd()

    # ------------------------------------------------------------------
    # 全局默认配置
    # ------------------------------------------------------------------

    def load_global_defaults(self) -> dict:
        """加载全局默认配置"""
        if self._global_defaults is not None:
            return self._global_defaults

        path = self.project_root / "config" / "global_defaults.yaml"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                self._global_defaults = yaml.safe_load(f) or {}
            logger.debug(f"加载全局默认配置: {path}")
        else:
            self._global_defaults = self._builtin_defaults()
            logger.debug("使用内置默认配置")
        return self._global_defaults

    @staticmethod
    def _builtin_defaults() -> dict:
        """内置默认配置（当 global_defaults.yaml 不存在时使用）"""
        return {
            "strategy_type": "ycj",
            "backtest": {
                "start_date": "2015-01-01",
                "end_date": "2026-06-01",
                "data_start_date": "2010-01-01",
                "train_end": "2024-12-31",
                "trading_days": 242,
                "transaction_cost": 0.001,
                "use_valuation": False,
                "use_money_flow": False,
                "use_margin": False,
                "use_crowding": False,
            },
            "selection": {
                "method": "icir",
                "ic_decay": 0.65,
                "use_icir": True,
                "icir_window": 60,
                "icir_floor": 0.3,
                "top_n": 10,
                "max_stock_weight": 0.025,
                "min_ic": 0.02,
                "min_ic_ir": 0.1,
                "rolling_factor_select": False,
                "regime_adaptive_icir": False,
                "factor_momentum": False,
            },
            "risk": {
                "target_vol": 0.25,
                "cvar_limit_factor": 1.5,
                "cvar_penalty_strength": 0.5,
                "lookback": 60,
                "min_exposure_scale": 0.8,
            },
            "allocation": {
                "lookback": 60,
                "weight_change_limit": 0.10,
                "weight_blend": 0.25,
                "method": "equal",
            },
            "portfolio": {
                "max_stock_weight": 0.025,
                "max_industry_weight": 0.15,
                "max_turnover": 0.5,
                "min_stocks": 10,
            },
            "data": {
                "source": "duckdb",
                "data_root": "D:/Work/Project/download_a_share/data",
            },
            "rebalance": {
                "frequency": "monthly",
                "weekday": 0,
                "method": "cost_benefit",
            },
        }

    # ------------------------------------------------------------------
    # 策略版本配置
    # ------------------------------------------------------------------

    def _resolve_version_dir(self, strategy_type: str, version: str) -> Path:
        """解析版本目录

        主版本 v1 → strategies/{type}/v1
        迭代版本 v1.1 → strategies/{type}/v1/iterations/v1_1
        """
        base = self.project_root / "ohmyquant" / "strategies" / strategy_type
        if not base.exists():
            raise StrategyVersionNotFoundError(strategy_type, version, [])

        if "." in version:
            main_ver = version.split(".")[0]
            iter_dirname = version.replace(".", "_")
            version_dir = base / main_ver / "iterations" / iter_dirname
        else:
            version_dir = base / version

        if not version_dir.exists():
            available = self._list_available_versions(strategy_type)
            raise StrategyVersionNotFoundError(strategy_type, version, available)

        return version_dir

    def _list_available_versions(self, strategy_type: str) -> list[str]:
        """列出可用版本"""
        import re

        base = self.project_root / "ohmyquant" / "strategies" / strategy_type
        versions: list[str] = []
        if not base.exists():
            return versions

        for name in sorted(os.listdir(base)):
            if not re.match(r"^v\d+$", name):
                continue
            if (base / name / "config.yaml").exists():
                versions.append(name)
            # 迭代版本
            iter_dir = base / name / "iterations"
            if iter_dir.is_dir():
                for iter_name in sorted(os.listdir(iter_dir)):
                    if re.match(r"^v\d+_\d+$", iter_name):
                        versions.append(iter_name.replace("_", ".", 1))

        def sort_key(v: str) -> tuple:
            parts = v.lstrip("v").split(".")
            return tuple(int(p) for p in parts)

        return sorted(versions, key=sort_key)

    def load_strategy_config(self, strategy_type: str, version: str) -> dict:
        """加载策略版本配置"""
        version_dir = self._resolve_version_dir(strategy_type, version)
        config_path = version_dir / "config.yaml"
        if not config_path.exists():
            raise ConfigError(f"配置文件不存在: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        logger.debug(f"加载策略配置: {config_path}")
        return config

    # ------------------------------------------------------------------
    # 构建完整配置
    # ------------------------------------------------------------------

    def build_config(
        self,
        strategy_type: str,
        version: str | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> StrategyConfig:
        """构建完整配置（三层合并 + Pydantic 校验）

        Args:
            strategy_type: 策略类型 "ycj" 或 "dh"
            version: 版本号，None 则用该类型的默认版本
            overrides: 运行时覆盖配置

        Returns:
            StrategyConfig: Pydantic 校验后的配置对象
        """
        # 层1: 全局默认
        merged = copy.deepcopy(self.load_global_defaults())

        # 层2: 策略版本
        if version is None:
            version = self._get_default_version(strategy_type)
        version_cfg = self.load_strategy_config(strategy_type, version)
        merged = _deep_merge(merged, version_cfg)

        # 确保必要字段
        merged.setdefault("strategy_type", strategy_type)
        merged.setdefault("strategy_version", version)

        # 层3: 运行时覆盖
        if overrides:
            merged = _deep_merge(merged, overrides)

        # Pydantic 校验
        try:
            config = StrategyConfig(**merged)
        except Exception as e:
            raise ConfigError(f"配置校验失败 [{strategy_type}/{version}]: {e}") from e

        logger.info(
            f"构建配置: {strategy_type}/{version} "
            f"(method={config.selection.method}, top_n={config.selection.top_n})"
        )
        return config

    def _get_default_version(self, strategy_type: str) -> str:
        """获取策略类型的默认版本"""
        available = self._list_available_versions(strategy_type)
        if not available:
            raise StrategyVersionNotFoundError(strategy_type, "default", [])
        return available[0]

    # ------------------------------------------------------------------
    # 配置文件生成（策略迭代后自动生成可复用配置）
    # ------------------------------------------------------------------

    def save_config(
        self,
        config: StrategyConfig,
        output_path: str | Path,
    ) -> Path:
        """保存配置到 YAML 文件

        策略迭代后自动生成可复用的配置文件。

        Args:
            config: 策略配置
            output_path: 输出路径
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        config_dict = config.model_dump(exclude_none=True)
        # 移除空 dict 和空 list
        config_dict = self._clean_dict(config_dict)

        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(
                config_dict,
                f,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
            )

        logger.info(f"配置已保存: {output_path}")
        return output_path

    @staticmethod
    def _clean_dict(d: dict) -> dict:
        """移除空值"""
        cleaned = {}
        for k, v in d.items():
            if isinstance(v, dict):
                cleaned_v = ConfigManager._clean_dict(v)
                if cleaned_v:
                    cleaned[k] = cleaned_v
            elif isinstance(v, list):
                if v:
                    cleaned[k] = v
            elif v is not None:
                cleaned[k] = v
        return cleaned

    def list_strategy_types(self) -> list[str]:
        """列出所有策略类型"""
        base = self.project_root / "ohmyquant" / "strategies"
        if not base.exists():
            return []
        return sorted(
            d.name for d in base.iterdir() if d.is_dir() and not d.name.startswith("_")
        )

    def list_versions(self, strategy_type: str, include_iterations: bool = False) -> list[str]:
        """列出策略的所有版本"""
        versions = self._list_available_versions(strategy_type)
        if include_iterations:
            return versions
        return [v for v in versions if "." not in v]


# 全局单例（懒加载）
_global_manager: ConfigManager | None = None


def get_config_manager() -> ConfigManager:
    """获取全局 ConfigManager 单例"""
    global _global_manager
    if _global_manager is None:
        _global_manager = ConfigManager()
    return _global_manager


__all__ = ["ConfigManager", "get_config_manager"]
