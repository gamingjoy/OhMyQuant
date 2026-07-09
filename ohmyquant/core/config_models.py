"""Pydantic v2 配置模型

定义策略配置的数据结构和校验规则。
所有配置在加载后都会通过 Pydantic 模型校验，确保类型正确和约束满足。
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class BacktestConfig(BaseModel):
    """回测参数"""

    start_date: str = "2015-01-01"
    end_date: str = "2026-06-01"
    data_start_date: str = "2010-01-01"
    train_end: str = "2024-12-31"
    val_end: str | None = None
    trading_days: int = Field(242, ge=200, le=366)
    transaction_cost: float = Field(0.001, ge=0, le=0.05)
    use_valuation: bool = False
    use_money_flow: bool = False
    use_margin: bool = False
    use_crowding: bool = False

    model_config = {"extra": "allow"}


class SelectionConfig(BaseModel):
    """选股参数"""

    method: str = "icir"  # icir / ml / hybrid / adaptive
    ic_decay: float = Field(0.65, gt=0, le=1.0)
    use_icir: bool = True
    icir_window: int = Field(60, ge=10, le=504)
    icir_floor: float = Field(0.3, ge=0, le=1.0)
    drift_window: int = Field(63, ge=5, le=252)
    drift_threshold: float = Field(0.58, ge=0, le=1.0)
    drift_boost: float = 1.0
    max_stock_weight: float = Field(0.025, gt=0, le=1.0)
    top_n: int = Field(10, ge=1, le=500)
    min_ic: float = 0.02
    min_ic_ir: float = 0.1
    rolling_factor_select: bool = False
    rolling_select_window: int = 252
    factor_corr_threshold: float = Field(0.85, ge=0, le=1.0)
    industry_neutral: bool = False
    regime_adaptive_icir: bool = False
    factor_momentum: bool = False
    factor_momentum_window: int = 20
    factor_momentum_up: float = 1.2
    factor_momentum_down: float = 0.8
    hybrid: dict[str, Any] = Field(default_factory=dict)
    ml: dict[str, Any] = Field(default_factory=dict)
    adaptive: dict[str, Any] = Field(default_factory=dict)
    model_name: str = ""
    model: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}

    @model_validator(mode="after")
    def validate_top_n_weight(self) -> "SelectionConfig":
        max_total = self.max_stock_weight * self.top_n
        if max_total < 0.5:
            import warnings

            warnings.warn(
                f"top_n={self.top_n} × max_stock_weight={self.max_stock_weight:.1%} "
                f"= {max_total:.1%}，总仓位可能过低",
                stacklevel=2,
            )
        return self


class RiskConfig(BaseModel):
    """风控参数"""

    target_vol: float = Field(0.25, gt=0, le=1.0)
    cvar_limit_factor: float = Field(1.5, gt=0)
    cvar_penalty_strength: float = Field(0.5, ge=0, le=2.0)
    vol_trend_mode: str = "managed_vol"
    vol_trend_strength: float = 2.0
    corr_risk_strength: float = 0.5
    tail_risk_strength: float = 0.3
    var_threshold: float = -0.03
    lookback: int = Field(60, ge=10, le=504)
    min_exposure_scale: float = Field(0.5, ge=0, le=1.0)

    model_config = {"extra": "allow"}


class AllocationConfig(BaseModel):
    """池间分配参数"""

    lookback: int = Field(60, ge=10, le=504)
    weight_change_limit: float = Field(0.10, ge=0, le=1.0)
    weight_blend: float = Field(0.25, ge=0, le=1.0)
    method: str = "equal"  # equal / hrp / icir_weighted

    model_config = {"extra": "allow"}


class PortfolioConfig(BaseModel):
    """组合约束参数"""

    max_stock_weight: float = Field(0.025, gt=0, le=1.0)
    max_industry_weight: float = Field(0.15, gt=0, le=1.0)
    max_turnover: float = Field(0.5, ge=0, le=2.0)
    min_stocks: int = Field(10, ge=1)
    weight_cap_iterations: int = Field(10, ge=1, le=100)

    model_config = {"extra": "allow"}


class DataConfig(BaseModel):
    """数据源参数"""

    source: str = "duckdb"  # duckdb / local_parquet / jqdata
    data_root: str = "D:/Work/Project/download_a_share/data"
    cache_dir: str | None = None

    model_config = {"extra": "allow"}


class RebalanceConfig(BaseModel):
    """调仓参数"""

    frequency: str = "monthly"  # daily / weekly / monthly / quarterly / adaptive
    weekday: int = Field(0, ge=0, le=6)
    min_hold_days: int = 0
    cost_benefit_threshold: float = 0.0
    method: str = "cost_benefit"  # cost_benefit / simple / none
    cost_model: dict[str, Any] = Field(
        default_factory=lambda: {"name": "stock_cn"}
    )  # 成本模型子配置

    model_config = {"extra": "allow"}


class StrategyConfig(BaseModel):
    """完整策略配置（Pydantic v2 校验）

    这是配置系统的核心模型，包含策略运行所需的全部参数。
    通过 ConfigManager.build_config() 构建，自动合并三层配置并校验。
    """

    strategy_version: str = "v1"
    strategy_name: str = ""
    strategy_type: str = "ycj"  # ycj / dh
    description: str = ""

    backtest: BacktestConfig = Field(default_factory=BacktestConfig)
    selection: SelectionConfig = Field(default_factory=SelectionConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    allocation: AllocationConfig = Field(default_factory=AllocationConfig)
    portfolio: PortfolioConfig = Field(default_factory=PortfolioConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    rebalance: RebalanceConfig = Field(default_factory=RebalanceConfig)

    # 因子列表（可选，由策略定义）
    factors: list[str] = Field(default_factory=list)
    # 股票池（可选）
    pools: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}

    @model_validator(mode="after")
    def sync_weights(self) -> "StrategyConfig":
        """同步 portfolio.max_stock_weight → selection.max_stock_weight"""
        if self.portfolio.max_stock_weight != self.selection.max_stock_weight:
            self.selection.max_stock_weight = self.portfolio.max_stock_weight
        return self

    def to_flat_dict(self) -> dict[str, Any]:
        """扁平化为 BacktestEngine 兼容格式

        将嵌套结构转为顶层标量 + 子 dict，兼容 halo_index 的 BacktestEngine。
        """
        bt = self.backtest
        flat: dict[str, Any] = {
            "strategy_version": self.strategy_version,
            "strategy_name": self.strategy_name,
            "strategy_type": self.strategy_type,
            "backtest_start": bt.start_date,
            "backtest_end": bt.end_date,
            "data_start_date": bt.data_start_date,
            "train_end": bt.train_end,
            "transaction_cost": bt.transaction_cost,
            "trading_days": bt.trading_days,
            "use_valuation": bt.use_valuation,
            "use_money_flow": bt.use_money_flow,
            "use_margin": bt.use_margin,
            "use_crowding": bt.use_crowding,
            "selection": self.selection.model_dump(),
            "risk": self.risk.model_dump(),
            "allocation": self.allocation.model_dump(),
            "portfolio": self.portfolio.model_dump(),
            "data": self.data.model_dump(),
            "rebalance": self.rebalance.model_dump(),
            "factors": self.factors,
            "pools": self.pools,
        }
        return flat


__all__ = [
    "BacktestConfig",
    "SelectionConfig",
    "RiskConfig",
    "AllocationConfig",
    "PortfolioConfig",
    "DataConfig",
    "RebalanceConfig",
    "StrategyConfig",
]
