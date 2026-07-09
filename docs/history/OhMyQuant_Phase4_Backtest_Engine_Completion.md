# OhMyQuant Phase 4: 回测引擎补全实施计划

## Summary

完成 OhMyQuant 框架 Phase 4（回测引擎）的剩余实现。当前 Phase 4 已完成基类（`base.py`/`context.py`/`selector.py`）和 4 个选股器（ICIR/Hybrid/Adaptive/ML），但缺失风控管理器、分配器、组合优化器和主引擎。本计划补全这 11 个文件，使 `BacktestEngine` 能端到端运行多池回测。

设计原则：polars-first（所有数据处理用 polars）、N 池架构（不局限于 halo_index 的 2 池）、插件化（通过 `PluginRegistry.create()` 实例化风控/分配器）、配置驱动（所有参数来自 `StrategyConfig`）。

## Current State Analysis

### 已完成（Phase 4 前半部分）
- [engine/base.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/engine/base.py) — `BacktestResult` 数据类（nav/dates/stock_weights_by_date/pool_weight_log/exposure_log）+ `BaseEngine` ABC
- [engine/context.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/engine/context.py) — `BacktestContext` 状态容器（current_idx/current_date/nav/daily_returns/current_exposure/current_regime）
- [engine/selector.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/engine/selector.py) — `BaseSelector` ABC，含 `select()`/`select_strong_factors()` 抽象方法 + `apply_weight_cap()` 工具方法
- [engine/selectors/](file:///d:/Work/Project/OhMyQuant/ohmyquant/engine/selectors/__init__.py) — `ICIRSelector`(registered "icir") / `HybridSelector`("hybrid") / `AdaptiveICIRSelector`("adaptive") / `MLSelector`("ml"，可选 LightGBM) + `create_selector()` 工厂

### 缺失（Phase 4 后半部分，本计划补全）
1. `engine/risk.py` — `BaseRiskManager` ABC
2. `engine/risk_managers/__init__.py` — 导出 + `create_risk_manager()` 工厂
3. `engine/risk_managers/vol_target.py` — `VolTargetRiskManager`（"vol_target"）
4. `engine/risk_managers/cvar_manager.py` — `CVaRRiskManager`（"cvar"）
5. `engine/risk_managers/drawdown_defense.py` — `DrawdownDefenseRiskManager`（"drawdown"）
6. `engine/risk_managers/regime_adaptive.py` — `RegimeAdaptiveRiskManager`（"regime_adaptive"，主力风控）
7. `engine/allocator.py` — `BaseAllocator` ABC
8. `engine/allocators/__init__.py` — 导出 + `create_allocator()` 工厂
9. `engine/allocators/equal_allocator.py` — `EqualAllocator`（"equal"）
10. `engine/allocators/hrp_allocator.py` — `HRPAllocator`（"hrp"）
11. `engine/allocators/icir_allocator.py` — `ICIRWeightedAllocator`（"icir_weighted"）
12. `engine/portfolio.py` — `PortfolioOptimizer`（个股权重上限/行业上限/换手率/最少持仓数）
13. `engine/backtest.py` — `BacktestEngine` 主引擎（整合所有组件）
14. `engine/__init__.py` — 模块导出（当前不存在）

### 关键参考
- [halo_index/src/engine/risk.py](file:///D:/Work/Project/halo_index/src/engine/risk.py) — `RiskManager` 类，含 `detect_market_regime`/`compute_cvar_scale`/`compute_dynamic_vol_target`/`compute_regime_adaptive_trend_exposure`/`compute_enhanced_drawdown_control`/`compute_managed_vol_scale`/`compute_tail_risk_scale`/`compute_composite_exposure`。基于 pandas，需移植到 polars。
- [halo_index/src/engine/allocation.py](file:///D:/Work/Project/halo_index/src/engine/allocation.py) — `PoolAllocator` 类，含 `compute_pool_hrp_weights`/`compute_pool_ic_ir_weights`/`compute_adaptive_pool_weights`/`smooth_weights`。硬编码 2 池（AI/Halo），需泛化到 N 池。
- [halo_index/src/engine/portfolio.py](file:///D:/Work/Project/halo_index/src/engine/portfolio.py) — `PortfolioOptimizer` 类，操作 `list[dict]` 持仓格式。
- [halo_index/src/engine/backtest.py](file:///D:/Work/Project/halo_index/src/engine/backtest.py) — `BacktestEngine` 主循环，`_run_backtest_loop` 方法展示了调仓日检查→池间分配→风控暴露度→组合日收益→交易成本→净值更新的完整流程。

### 现有 API 约束（必须遵循）
- **PluginRegistry**: `PluginRegistry.create(PluginType.RISK_MANAGER, name, config)` / `PluginRegistry.create(PluginType.ALLOCATOR, name, config)`
- **装饰器**: `@register_risk_manager("name")` / `@register_allocator("name")`
- **配置字段**（来自 [config_models.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/core/config_models.py)):
  - `RiskConfig`: target_vol, cvar_limit_factor, cvar_penalty_strength, vol_trend_mode, vol_trend_strength, corr_risk_strength, tail_risk_strength, var_threshold, lookback, min_exposure_scale
  - `AllocationConfig`: lookback, weight_change_limit, weight_blend, method(equal/hrp/icir_weighted)
  - `PortfolioConfig`: max_stock_weight, max_industry_weight, max_turnover, min_stocks, weight_cap_iterations
- **DataCatalog API**: `get_ohlcv(codes, start, end)` → `{"open":wide_df,...}`; `get_close(codes, start, end)` → wide_df; `get_valuation()`/`get_money_flow()`/`get_margin()`/`get_industry_map()`/`get_index_data()`/`get_trade_calendar()`
- **FactorLibrary**: `compute_factors(factor_names, data_dict)` → `{factor_name: factor_df}`
- **FactorAnalyzer**: `compute_ic(factor_values, forward_returns, method)` → ic_df; `compute_icir(ic_series)` → FactorStats
- **FactorOptimizer**: `select_strong_factors(ic_df, train_end, min_ic, min_icir, corr_threshold)` → list[str]; `compute_icir_weights(ic_df, factor_names, current_date, window, decay)` → dict
- **BaseSelector.select()** 签名: `select(factors, ic_df, stock_codes, current_idx, close, regime, strong_factors, **kwargs) -> dict[str,float] | None`
- **宽表格式**: `pl.DataFrame`，列为 `date` + 各 code 列，date 作为行

## Proposed Changes

### 1. `engine/risk.py` — BaseRiskManager ABC

**What**: 定义风控管理器的抽象基类，所有风控插件实现此接口。

**Why**: 引擎需要统一的风控接口，使 `VolTargetRiskManager`/`CVaRRiskManager`/`DrawdownDefenseRiskManager`/`RegimeAdaptiveRiskManager` 可互换。

**How**:
```python
class BaseRiskManager(ABC):
    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self.target_vol = cfg.get("target_vol", 0.25)
        self.lookback = cfg.get("lookback", 60)
        self.min_exposure_scale = cfg.get("min_exposure_scale", 0.5)
        # 子类可读取更多字段

    @abstractmethod
    def compute_exposure(
        self,
        nav: pl.Series,
        daily_returns: pl.Series,
        current_idx: int,
        current_exposure: float,
        **kwargs,
    ) -> tuple[float, str]:
        """计算当日有效暴露度

        Returns:
            (effective_scale, regime)
        """
        ...

    @abstractmethod
    def detect_regime(
        self,
        daily_returns: pl.Series,
        current_idx: int,
        lookback: int | None = None,
    ) -> tuple[str, float]:
        """检测市场状态

        Returns:
            (regime, confidence)
        """
        ...

    # 共享工具方法
    @staticmethod
    def _annualized_vol(daily_returns_slice: pl.Series, trading_days: int = 242) -> float:
        """计算年化波动率"""
        ...

    @staticmethod
    def _compute_cvar(daily_returns_slice: pl.Series, alpha: float = 0.05) -> float:
        """计算 CVaR"""
        ...
```

### 2. `engine/risk_managers/vol_target.py` — VolTargetRiskManager

**What**: 简单波动率目标风控，仅根据实现波动率调整暴露度。

**Why**: 提供轻量级风控选项，适合简单策略或作为基线对比。

**How**: 注册为 `"vol_target"`。`compute_exposure` 返回 `clip(target_vol / current_vol, min_exposure_scale, 1.5)`。`detect_regime` 根据 vol 是否超过 `target_vol * 1.3` 判断 high_vol/sideway。移植 halo_index `compute_cvar_scale` 的波动率缩放部分（去掉 CVaR 惩罚）。

### 3. `engine/risk_managers/cvar_manager.py` — CVaRRiskManager

**What**: 基于 CVaR 的风控，当尾部风险超过阈值时降低暴露度。

**Why**: 独立的尾部风险控制，适合关注极端下跌的场景。

**How**: 注册为 `"cvar"`。移植 halo_index `compute_cvar_scale` 完整逻辑（含 CVaR 惩罚）。`detect_regime` 复用基类的简单判断。`compute_exposure` 调用 `compute_cvar_scale` 逻辑。

### 4. `engine/risk_managers/drawdown_defense.py` — DrawdownDefenseRiskManager

**What**: 回撤防御风控，根据当前回撤深度动态降低仓位。

**Why**: 专注于最大回撤控制，适合保守型策略。

**How**: 注册为 `"drawdown"`。移植 halo_index `compute_enhanced_drawdown_control`：回撤 >18% → 30% 仓位，>12% → 45%，>8% → 60%，>4% → 80%，否则 100%。加入崩盘信号检测（近 5 日收益 < -5% 时额外惩罚）。`detect_regime` 复用基类。

### 5. `engine/risk_managers/regime_adaptive.py` — RegimeAdaptiveRiskManager（主力）

**What**: 综合风控，集成 regime 检测 + 波动率目标 + CVaR + 趋势暴露 + 回撤控制 + 尾部风险。

**Why**: 这是默认推荐的风控器，对应 halo_index 的完整 `RiskManager`。提供最全面的风险管理。

**How**: 注册为 `"regime_adaptive"`。移植 halo_index `RiskManager` 的全部方法：
- `detect_market_regime` — 基于 vol + 趋势斜率 + MA20/MA40 + 阳线比例判断 strong_trend/weak_trend/sideway/high_vol
- `compute_cvar_scale` — 波动率目标 + CVaR 惩罚 + 长短期平滑
- `compute_dynamic_vol_target` — 根据 regime 动态调整目标波动率
- `compute_regime_adaptive_trend_exposure` — 根据 regime 设定基础暴露度 + MA120 趋势过滤
- `compute_enhanced_drawdown_control` — 回撤分级降仓 + 崩盘信号
- `compute_managed_vol_scale` — 管理波动率模式（managed_vol/trend）
- `compute_tail_risk_scale` — VaR/CVaR 尾部风险缩放
- `compute_composite_exposure` — 综合所有信号：`effective_scale = vol_scale * ((1-factor_weight)*base_exposure + factor_weight*factor_signal*current_exposure) * proactive_scale`

所有方法从 pandas 迁移到 polars。`compute_exposure` 调用 `compute_composite_exposure` 并返回 `(effective_scale, regime)`。

### 6. `engine/risk_managers/__init__.py`

**What**: 导出所有风控管理器 + `create_risk_manager()` 工厂函数。

**How**:
```python
from .vol_target import VolTargetRiskManager
from .cvar_manager import CVaRRiskManager
from .drawdown_defense import DrawdownDefenseRiskManager
from .regime_adaptive import RegimeAdaptiveRiskManager

def create_risk_manager(config: dict | None = None):
    from ...core.plugin_system import PluginRegistry, PluginType
    cfg = config or {}
    method = cfg.get("method", "regime_adaptive")  # 默认主力风控
    return PluginRegistry.create(PluginType.RISK_MANAGER, method, config=cfg)
```

### 7. `engine/allocator.py` — BaseAllocator ABC

**What**: 定义池间分配器的抽象基类，支持 N 池。

**Why**: 引擎需要统一的池间权重分配接口。halo_index 硬编码 2 池（AI/Halo），需泛化。

**How**:
```python
class BaseAllocator(ABC):
    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self.lookback = cfg.get("lookback", 60)
        self.weight_change_limit = cfg.get("weight_change_limit", 0.10)
        self.weight_blend = cfg.get("weight_blend", 0.25)

    @abstractmethod
    def allocate(
        self,
        pool_returns: dict[str, pl.Series],  # {pool_name: daily_return_series}
        current_idx: int,
        prev_weights: dict[str, float],
        regime: str | None = None,
        **kwargs,
    ) -> dict[str, float]:
        """计算各池权重

        Returns:
            {pool_name: weight}，权重和为 1.0
        """
        ...

    def smooth_weights(
        self,
        new_weights: dict[str, float],
        prev_weights: dict[str, float],
    ) -> dict[str, float]:
        """权重平滑：变化过大时混合新旧权重"""
        delta = sum(abs(new_weights.get(k, 0) - prev_weights.get(k, 0))
                    for k in set(new_weights) | set(prev_weights))
        if delta > self.weight_change_limit:
            blended = {}
            for k in new_weights:
                blended[k] = (self.weight_blend * new_weights[k]
                              + (1 - self.weight_blend) * prev_weights.get(k, 0))
            total = sum(blended.values())
            return {k: v / total for k, v in blended.items()} if total > 0 else new_weights
        return new_weights

    @staticmethod
    def get_rebalance_dates(dates: list[str], freq: str = "monthly") -> set[str]:
        """根据频率计算调仓日"""
        ...
```

### 8. `engine/allocators/equal_allocator.py` — EqualAllocator

**What**: 等权分配器，所有池等权重。

**Why**: 最简单的基线分配方案，适合对比评估。

**How**: 注册为 `"equal"`。`allocate` 返回 `{pool: 1/N for each pool}`。

### 9. `engine/allocators/hrp_allocator.py` — HRPAllocator

**What**: 基于分层风险平价（HRP）的分配器，根据各池收益协方差分配。

**Why**: 风险平价是经典的多资产分配方法，halo_index 的 `compute_pool_hrp_weights` 即是简化版 HRP。

**How**: 注册为 `"hrp"`。泛化 halo_index `compute_pool_hrp_weights` 到 N 池：构建池收益 DataFrame → 计算协方差矩阵 → 对每对池用 HRP 公式 `alpha = 1 - V0/(V0+V1-2*sqrt(V0*V1)*corr)` 计算权重。N>2 时使用递归二分分割或退化为 inverse-variance weighting。

### 10. `engine/allocators/icir_allocator.py` — ICIRWeightedAllocator

**What**: 基于各池强因子 ICIR 加权的分配器。

**Why**: 根据各池因子预测能力动态分配，ICIR 高的池获得更多权重。

**How**: 注册为 `"icir_weighted"`。泛化 halo_index `compute_pool_ic_ir_weights` 到 N 池：对每个池，计算其强因子的平均 ICIR → 按ICIR 比例分配权重 → clip 到 [0.2, 0.8] 防止过度集中。支持与 HRP 混合（`weight_blend` 参数）。

### 11. `engine/allocators/__init__.py`

**What**: 导出所有分配器 + `create_allocator()` 工厂。

**How**:
```python
from .equal_allocator import EqualAllocator
from .hrp_allocator import HRPAllocator
from .icir_allocator import ICIRWeightedAllocator

def create_allocator(config: dict | None = None):
    from ...core.plugin_system import PluginRegistry, PluginType
    cfg = config or {}
    method = cfg.get("method", "equal")
    return PluginRegistry.create(PluginType.ALLOCATOR, method, config=cfg)
```

### 12. `engine/portfolio.py` — PortfolioOptimizer

**What**: 组合约束优化器，处理个股/行业权重上限、换手率限制、最少持仓数。

**Why**: 引擎输出的最终权重需满足组合约束，halo_index 已有参考实现但基于 `list[dict]`，本框架采用 `dict[str,float]` 权重格式。

**How**: 移植 halo_index `PortfolioOptimizer` 但改为操作 `dict[str, float]` 权重：
- `apply_weight_cap(weights: dict[str,float], cap: float) -> dict[str,float]` — 个股权重上限迭代截断（复用 `BaseSelector.apply_weight_cap` 逻辑）
- `apply_industry_cap(weights: dict[str,float], industry_map: dict[str,str], cap: float) -> dict[str,float]` — 行业权重上限按比例缩减
- `apply_turnover_limit(new_weights, old_weights, max_turnover) -> dict[str,float]` — 换手率限制按比例缩减变化
- `enforce_min_stocks(weights, min_stocks) -> dict[str,float]` — 检查最少持仓数（仅警告）
- `optimize(weights, old_weights, industry_map) -> dict[str,float]` — 串联执行所有约束

### 13. `engine/backtest.py` — BacktestEngine（主引擎）

**What**: 整合所有组件的主回测引擎，N 池向量化架构。

**Why**: 这是 Phase 4 的核心交付物，连接数据层、因子平台、选股器、风控、分配器、组合优化器。

**How**: 继承 `BaseEngine`，构造函数接收 `DataCatalog` + `StrategyConfig`（或 flat dict）。

**`__init__`**:
- 从 config 提取 selection/risk/allocation/portfolio 子配置
- 通过 `create_selector(selection_cfg)` / `create_risk_manager(risk_cfg)` / `create_allocator(allocation_cfg)` 创建插件实例
- 实例化 `PortfolioOptimizer(portfolio_cfg)`
- 保存 `data_catalog`、`factor_library`、`train_end`、`transaction_cost` 等参数

**`run(pools, start_date, end_date) -> BacktestResult`** 流程:

1. **数据加载**：对每个 pool，`data_catalog.get_ohlcv(pool_stocks, data_start_date, end_date)` 获取 `{open/high/low/close/volume/money: wide_df}`
2. **因子计算**：`factor_library.compute_factors(config.factors, ohlcv_data)` → `{factor_name: wide_df}`
3. **前向收益**：基于 close 计算 20 日前向收益宽表
4. **IC 分析**：对每个因子调用 `FactorAnalyzer.compute_ic(factor_values, forward_returns)` → 拼接成 `ic_df`（date + 各因子 IC 列）
5. **强因子筛选**：`selector.select_strong_factors(ic_df, train_end)` → `strong_factors` 列表
6. **选股**：遍历调仓日，对每个 pool 调用 `selector.select(factors, ic_df, pool_stocks, current_idx, close, regime, strong_factors)` → `stock_weights_by_date[date][pool] = {code: weight}`
7. **回测主循环**（参考 halo_index `_run_backtest_loop`）：
   ```
   for i in range(1, len(dates)):
       date = dates[i]
       # 1. 更新当前持仓（从 stock_weights_by_date 取最近的）
       # 2. 调仓日检查：if date in rebalance_dates:
       #      regime = risk_manager.detect_regime(daily_returns, i)
       #      new_pool_weights = allocator.allocate(pool_returns, i, prev_pool_weights, regime)
       #      pool_weights = allocator.smooth_weights(new_pool_weights, prev_pool_weights)
       # 3. 风控暴露度：effective_scale, regime = risk_manager.compute_exposure(nav, daily_returns, i, current_exposure)
       # 4. 组合日收益：daily_ret = sum(pool_weights[p] * pool_stock_returns[p] * effective_scale) - cost
       #      其中 pool_stock_returns = sum(stock_weight[code] * stock_daily_return[code] for code in pool)
       # 5. 交易成本：if date in rebalance_dates: cost = transaction_cost * (weight_turnover + scale_turnover)
       # 6. 净值更新：nav.append(nav[-1] * (1 + daily_ret))
       # 7. 日志：stock_weights_log[date], pool_weight_log, exposure_log
   ```
8. **构建 BacktestResult**：填充 nav(pl.Series)、dates(list)、stock_weights_by_date、pool_weight_log、exposure_log、daily_returns、config

**N 池通用组合收益计算**（参考 halo_index `_compute_capped_portfolio_return`，泛化到 N 池）：
```python
def _compute_portfolio_daily_return(
    pool_stock_weights: dict[str, dict[str, float]],  # {pool: {code: weight}}
    pool_stock_returns: dict[str, dict[str, float]],  # {pool: {code: daily_return}}
    pool_weights: dict[str, float],                   # {pool: weight}
    effective_scale: float,
    max_stock_weight: float,
) -> float:
    # 1. 合并所有池的个股总权重 = pool_weight * stock_weight * effective_scale
    # 2. 应用个股总权重上限（迭代截断）
    # 3. 加权求和：sum(weight * return)
```

### 14. `engine/__init__.py` — 模块导出

**What**: 导出引擎层公共 API。

**How**:
```python
from .base import BacktestResult, BaseEngine
from .context import BacktestContext
from .selector import BaseSelector
from .selectors import create_selector, ICIRSelector, HybridSelector, AdaptiveICIRSelector
from .risk import BaseRiskManager
from .risk_managers import create_risk_manager, RegimeAdaptiveRiskManager
from .allocator import BaseAllocator
from .allocators import create_allocator, EqualAllocator, HRPAllocator, ICIRWeightedAllocator
from .portfolio import PortfolioOptimizer
from .backtest import BacktestEngine

__all__ = [
    "BacktestResult", "BaseEngine", "BacktestContext",
    "BaseSelector", "create_selector", "ICIRSelector", "HybridSelector", "AdaptiveICIRSelector",
    "BaseRiskManager", "create_risk_manager", "RegimeAdaptiveRiskManager",
    "BaseAllocator", "create_allocator", "EqualAllocator", "HRPAllocator", "ICIRWeightedAllocator",
    "PortfolioOptimizer", "BacktestEngine",
]
```

## Assumptions & Decisions

1. **polars-first**：所有风控/分配器/引擎内部数据处理使用 polars Series/DataFrame，不依赖 pandas。halo_index 的 pandas 代码需移植。
2. **N 池架构**：分配器和引擎支持任意数量池（不限于 halo_index 的 AI/Halo 2 池）。`pools` 参数为 `dict[str, list[str]]`（pool_name → stock_codes）。
3. **权重格式统一**：个股权重用 `dict[str, float]`（code → weight），池权重用 `dict[str, float]`（pool_name → weight）。不使用 halo_index 的 `list[dict]` 持仓格式。
4. **默认风控**：`RegimeAdaptiveRiskManager` 作为默认且最全面的风控器（对应 `risk.method` 未指定时）。其他三个（vol_target/cvar/drawdown）作为轻量替代。
5. **默认分配器**：`EqualAllocator` 作为默认（最简单），HRP 和 ICIRWeighted 作为进阶选项。`allocation.method` 字段控制。
6. **风控配置传递**：`RiskConfig` 无 `method` 字段，需在 `RiskConfig` 中通过 `model_config = {"extra": "allow"}` 已支持的额外字段 `method` 指定。引擎从 `risk_cfg.get("method", "regime_adaptive")` 读取。
7. **TRADING_DAYS**：使用 242（与 halo_index 一致，config_models.py 中 `BacktestConfig.trading_days` 默认 242）。
8. **Regime 类型**：使用 `Regime` 类型别名（`str`），值为 `"strong_trend"`/`"weak_trend"`/`"sideway"`/`"high_vol"`（与 [types.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/core/types.py) 一致）。
9. **不实现因子衰减信号**：halo_index 的 `compute_factor_decay_signal` 和 `compute_pool_correlation_scale` 依赖多池 IC 数据，在 N 池通用架构中复杂度过高，暂不移植到 `RegimeAdaptiveRiskManager`。`compute_composite_exposure` 中 `factor_weight` 设为 0，仅用 vol_scale * base_exposure * proactive_scale。
10. **调仓频率**：支持 daily/weekly/monthly/quarterly/adaptive，由 `RebalanceConfig.frequency` 控制。adaptive 模式根据 regime 动态调整（高波动时降低频率）。调仓频率逻辑在 `BaseAllocator.get_rebalance_dates()` 静态方法实现，引擎调用。
11. **交易成本**：单边换手率 × `transaction_cost`。换手率 = (权重变化 + 暴露度变化) / 2。
12. **不引入新依赖**：仅使用已安装的 polars/numpy/scipy。HRP 简化实现不依赖 `PyPortfolioOpt`。

## Verification Steps

1. **导入测试**：
   ```bash
   python -c "from ohmyquant.engine import BacktestEngine, create_selector, create_risk_manager, create_allocator; print('OK')"
   ```
   验证所有模块可导入，无循环依赖。

2. **插件注册测试**：
   ```bash
   python -c "
   from ohmyquant.core.plugin_system import PluginRegistry, PluginType
   from ohmyquant.engine.risk_managers import *
   from ohmyquant.engine.allocators import *
   print('Risk managers:', PluginRegistry.list_plugins(PluginType.RISK_MANAGER))
   print('Allocators:', PluginRegistry.list_plugins(PluginType.ALLOCATOR))
   "
   ```
   预期输出：4 个风控器（vol_target/cvar/drawdown/regime_adaptive）+ 3 个分配器（equal/hrp/icir_weighted）。

3. **工厂方法测试**：
   ```bash
   python -c "
   from ohmyquant.engine import create_risk_manager, create_allocator
   rm = create_risk_manager({'method': 'regime_adaptive', 'target_vol': 0.25})
   al = create_allocator({'method': 'hrp', 'lookback': 60})
   print(type(rm).__name__, type(al).__name__)
   "
   ```
   预期输出：`RegimeAdaptiveRiskManager HRPAllocator`。

4. **风控器单元测试**（手动）：
   ```bash
   python -c "
   import polars as pl
   import numpy as np
   from ohmyquant.engine.risk_managers import RegimeAdaptiveRiskManager
   rm = RegimeAdaptiveRiskManager({'target_vol': 0.25, 'lookback': 60})
   # 模拟 100 日收益
   np.random.seed(42)
   rets = pl.Series(np.random.normal(0.001, 0.02, 100))
   nav = pl.Series(np.cumprod(1 + rets.to_numpy()))
   scale, regime = rm.compute_exposure(nav, rets, 99, 1.0)
   print(f'scale={scale:.3f}, regime={regime}')
   r, conf = rm.detect_regime(rets, 99)
   print(f'regime={r}, confidence={conf:.3f}')
   "
   ```
   验证风控器能正常计算暴露度和市场状态。

5. **分配器单元测试**（手动）：
   ```bash
   python -c "
   import polars as pl
   import numpy as np
   from ohmyquant.engine.allocators import HRPAllocator
   al = HRPAllocator({'lookback': 60})
   np.random.seed(42)
   pool_returns = {
       'pool_a': pl.Series(np.random.normal(0.001, 0.015, 100)),
       'pool_b': pl.Series(np.random.normal(0.0008, 0.02, 100)),
   }
   weights = al.allocate(pool_returns, 99, {'pool_a': 0.5, 'pool_b': 0.5})
   print(weights)
   "
   ```
   验证分配器能计算合理权重（和为 1.0）。

6. **PortfolioOptimizer 测试**：
   ```bash
   python -c "
   from ohmyquant.engine.portfolio import PortfolioOptimizer
   po = PortfolioOptimizer({'max_stock_weight': 0.025, 'max_industry_weight': 0.15})
   weights = {'a': 0.10, 'b': 0.08, 'c': 0.05, 'd': 0.03, 'e': 0.02}
   capped = po.apply_weight_cap(weights, 0.025)
   print(capped)
   "
   ```
   验证权重截断后无个股超过 0.025。

7. **端到端冒烟测试**（需真实数据，可选）：
   ```bash
   python -c "
   from ohmyquant.data.sources.duckdb_source import DuckDBSource
   from ohmyquant.data.base import DataCatalog
   from ohmyquant.engine.backtest import BacktestEngine
   from ohmyquant.core.config_models import StrategyConfig
   
   source = DuckDBSource(data_root='D:/Work/Project/download_a_share/data')
   catalog = DataCatalog(source)
   config = StrategyConfig()
   engine = BacktestEngine(catalog, config)
   # 用少量股票小范围回测
   result = engine.run(
       pools={'test_pool': ['000001.SZ', '600000.SH']},
       start_date='2024-01-01',
       end_date='2024-06-30',
   )
   print(f'Final NAV: {result.final_nav:.4f}, Days: {result.n_days}')
   "
   ```
   验证引擎能端到端运行并生成净值序列。

## 实现顺序

严格按依赖关系顺序实现（每个文件依赖前一个）：

1. `engine/risk.py`（ABC，无依赖）
2. `engine/risk_managers/vol_target.py`（依赖 risk.py）
3. `engine/risk_managers/cvar_manager.py`（依赖 risk.py）
4. `engine/risk_managers/drawdown_defense.py`（依赖 risk.py）
5. `engine/risk_managers/regime_adaptive.py`（依赖 risk.py，最复杂）
6. `engine/risk_managers/__init__.py`（依赖 2-5）
7. `engine/allocator.py`（ABC，无依赖）
8. `engine/allocators/equal_allocator.py`（依赖 allocator.py）
9. `engine/allocators/hrp_allocator.py`（依赖 allocator.py）
10. `engine/allocators/icir_allocator.py`（依赖 allocator.py）
11. `engine/allocators/__init__.py`（依赖 8-10）
12. `engine/portfolio.py`（独立，无依赖）
13. `engine/backtest.py`（依赖以上所有 + data_catalog + factor_library）
14. `engine/__init__.py`（依赖 13）

每完成一个文件立即用 `python -c "import ..."` 验证导入正确，避免错误累积。
