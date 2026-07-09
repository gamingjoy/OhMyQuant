"""策略运行器

统一运行入口，负责创建数据目录、初始化回测引擎、执行策略并返回结果。

提供 `StrategyRunner.run()` 作为唯一入口，兼容 `Strategy.from_version().run()` 模式。

设计目标：
  - 统一的数据目录创建逻辑
  - 自动配置数据源
  - 集成 BacktestEngine
  - 支持多种运行模式（回测/模拟/实盘）
  - 提供完整的执行日志和结果汇总
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core.config_models import StrategyConfig
from ..core.logging import get_logger
from ..data.base import DataCatalog
from ..data.sources.csv_source import CSVSource
from ..data.sources.duckdb_source import DuckDBSource
from ..data.sources.jqdata_source import JQDataSource
from ..data.sources.local_parquet_source import LocalParquetSource
from ..engine.backtest import BacktestEngine
from ..engine.base import BacktestResult

from .base import BaseStrategy
from .registry import StrategyRegistry

logger = get_logger(__name__)


@dataclass
class StrategyResult:
    """策略运行结果"""

    backtest_result: BacktestResult
    strategy: BaseStrategy
    config: StrategyConfig
    runtime_info: dict[str, Any] = field(default_factory=dict)


class StrategyRunner:
    """策略运行器

    负责初始化数据目录、创建回测引擎、执行策略。
    """

    def __init__(self, config: StrategyConfig | dict | None = None):
        """初始化运行器

        Args:
            config: 策略配置
        """
        if config is None:
            self.config = StrategyConfig()
        elif isinstance(config, dict):
            self.config = StrategyConfig(**config)
        else:
            self.config = config

        self.data_catalog: DataCatalog | None = None
        self.backtest_engine: BacktestEngine | None = None
        self.tracker: Any = None

    def _create_data_catalog(self) -> DataCatalog:
        """创建数据目录

        通过 PluginRegistry 按名创建数据源（热插拔：任意已注册数据源均可配置使用），
        未注册或创建失败时回退到 duckdb。

        Returns:
            DataCatalog: 数据目录实例
        """
        from ..core.plugin_system import PluginRegistry, PluginType
        from ..core.exceptions import PluginNotFoundError

        data_source_name = self.config.data.source
        data_root = self.config.data.data_root

        try:
            source = PluginRegistry.create(
                PluginType.DATA_SOURCE,
                data_source_name,
                config={"data_root": data_root},
            )
        except PluginNotFoundError:
            logger.warning(f"未知数据源: {data_source_name}，使用 duckdb")
            source = PluginRegistry.create(
                PluginType.DATA_SOURCE, "duckdb", config={"data_root": data_root}
            )
        return DataCatalog(source)

    def _create_backtest_engine(self) -> BacktestEngine:
        """创建回测引擎

        Returns:
            BacktestEngine: 回测引擎实例
        """
        if self.data_catalog is None:
            self.data_catalog = self._create_data_catalog()

        flat_config = self.config.to_flat_dict()
        return BacktestEngine(self.data_catalog, flat_config)

    def _resolve_pools(self) -> dict[str, list[str]]:
        """解析股票池配置，支持动态池（基于指数成分股）

        配置格式：
          静态池:  pools: {main: ["600519.SH", "601318.SH"]}
          动态池:  pools: {main: {index: "000300.XSHG"}}
          默认:    无 pools 配置时使用 CSI 300
        """
        raw_pools = self.config.pools
        if not raw_pools:
            raw_pools = {"main": {"index": "000300.XSHG"}}

        resolved: dict[str, list[str]] = {}
        for name, definition in raw_pools.items():
            if isinstance(definition, list):
                resolved[name] = definition
            elif isinstance(definition, dict) and "index" in definition:
                index_code = definition["index"]
                codes = self.data_catalog.get_index_constituents(index_code)
                if not codes:
                    logger.warning(f"池 {name} 指数成分股加载失败: {index_code}，使用空池")
                    codes = []
                else:
                    logger.info(f"池 {name} 动态加载 {index_code}: {len(codes)} 只股票")
                resolved[name] = codes
            elif isinstance(definition, dict) and "stocks" in definition:
                resolved[name] = definition["stocks"]
            else:
                resolved[name] = []

        return resolved

    def run(self) -> StrategyResult:
        """执行策略

        Returns:
            StrategyResult: 策略运行结果
        """
        logger.info(
            f"开始执行策略: {self.config.strategy_type} {self.config.strategy_version}"
        )

        # 创建数据目录
        self.data_catalog = self._create_data_catalog()
        logger.info(f"数据目录已创建: {self.config.data.source}")

        # 创建回测引擎
        self.backtest_engine = self._create_backtest_engine()

        # 获取股票池配置（支持动态池：pools: {main: {index: "000300.XSHG"}}）
        pools = self._resolve_pools()

        # 执行回测
        bt_start = self.config.backtest.start_date
        bt_end = self.config.backtest.end_date

        result = self.backtest_engine.run(pools=pools, start_date=bt_start, end_date=bt_end)

        logger.info(
            f"策略执行完成: 天数={result.n_days}, 最终净值={result.final_nav:.4f}, "
            f"调仓日志数={len(result.pool_weight_log)}"
        )

        return StrategyResult(
            backtest_result=result,
            strategy=None,
            config=self.config,
            runtime_info={
                "strategy_type": self.config.strategy_type,
                "strategy_version": self.config.strategy_version,
                "data_source": self.config.data.source,
            },
        )

    @classmethod
    def run_strategy(
        cls,
        strategy_type: str,
        version: str,
        config_overrides: dict | None = None,
    ) -> StrategyResult:
        """便捷方法：从版本运行策略

        Args:
            strategy_type: 策略类型（ycj/dh）
            version: 版本号（v1/v2）
            config_overrides: 运行时配置覆盖

        Returns:
            StrategyResult: 策略运行结果
        """
        # 创建策略实例
        strategy = StrategyRegistry.create(strategy_type, version, config_overrides)

        # 创建运行器
        runner = cls(strategy.config)

        # 执行策略
        result = runner.run()
        result.strategy = strategy

        return result


def run(strategy_type: str, version: str, **kwargs) -> StrategyResult:
    """便捷函数：运行策略

    Args:
        strategy_type: 策略类型（ycj/dh）
        version: 版本号（v1/v2）
        **kwargs: 配置覆盖参数

    Returns:
        StrategyResult: 策略运行结果
    """
    return StrategyRunner.run_strategy(strategy_type, version, kwargs)


__all__ = ["StrategyRunner", "StrategyResult", "run"]
