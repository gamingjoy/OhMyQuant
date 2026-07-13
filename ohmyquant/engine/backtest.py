"""回测引擎（主引擎）

N 池向量化回测引擎，整合选股器/风控/分配器/组合优化器。
参考 halo_index 的 BacktestEngine，泛化到任意数量池。

流程:
  1. 加载数据（DataCatalog）
  2. 计算因子（FactorLibrary）
  3. 计算前向收益 + IC 分析
  4. 筛选强因子
  5. 选股（每个调仓日，每个池）
  6. 回测主循环（调仓日检查→池间分配→风控暴露度→组合日收益→交易成本→净值更新）
"""
from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl

from ..core.config_models import StrategyConfig
from ..core.logging import get_logger
from ..data.base import DataCatalog
from ..factors.analysis import FactorAnalyzer
from ..factors.library import FactorLibrary, get_factor_library
from .allocators import create_allocator
from .base import BacktestResult, BaseEngine
from .portfolio import PortfolioOptimizer
from .risk_managers import create_risk_manager
from .selectors import create_selector

logger = get_logger(__name__)

FORWARD_RETURN_HORIZON = 20


class BacktestEngine(BaseEngine):
    """N 池向量化回测引擎

    用法:
        from ohmyquant.data.sources.duckdb_source import DuckDBSource
        from ohmyquant.data.base import DataCatalog
        from ohmyquant.core.config_models import StrategyConfig

        catalog = DataCatalog(DuckDBSource(data_root="..."))
        config = StrategyConfig()
        engine = BacktestEngine(catalog, config)
        result = engine.run(
            pools={"pool_a": ["000001.SZ", "600000.SH"]},
            start_date="2024-01-01",
            end_date="2024-06-30",
        )
    """

    def __init__(
        self,
        data_catalog: DataCatalog,
        config: StrategyConfig | dict | None = None,
        factor_library: FactorLibrary | None = None,
    ):
        self.data_catalog = data_catalog
        self.factor_library = factor_library or get_factor_library()

        # 统一配置为 flat dict
        if isinstance(config, StrategyConfig):
            self.config = config
            flat = config.to_flat_dict()
        elif config is None:
            self.config = StrategyConfig()
            flat = self.config.to_flat_dict()
        else:
            flat = config
            self.config = StrategyConfig(**config) if isinstance(config, dict) else None

        # 提取子配置
        self.backtest_cfg = flat.get("backtest", {})
        if isinstance(self.backtest_cfg, dict):
            self.backtest_start = self.backtest_cfg.get("start_date", "2015-01-01")
            self.backtest_end = self.backtest_cfg.get("end_date", "2026-06-01")
            self.data_start_date = self.backtest_cfg.get("data_start_date", "2010-01-01")
            self.train_end = self.backtest_cfg.get("train_end", "2024-12-31")
            self.transaction_cost = self.backtest_cfg.get("transaction_cost", 0.001)
            self.trading_days = self.backtest_cfg.get("trading_days", 242)
        else:
            # StrategyConfig 对象
            bt = self.config.backtest
            self.backtest_start = bt.start_date
            self.backtest_end = bt.end_date
            self.data_start_date = bt.data_start_date
            self.train_end = bt.train_end
            self.transaction_cost = bt.transaction_cost
            self.trading_days = bt.trading_days

        selection_cfg = self._get_sub_config(flat, "selection")
        risk_cfg = self._get_sub_config(flat, "risk")
        allocation_cfg = self._get_sub_config(flat, "allocation")
        portfolio_cfg = self._get_sub_config(flat, "portfolio")
        rebalance_cfg = self._get_sub_config(flat, "rebalance")

        # 创建可插拔组件
        self.selector = create_selector(selection_cfg)
        self.risk_manager = create_risk_manager(risk_cfg)
        self.allocator = create_allocator(allocation_cfg)
        self.portfolio_optimizer = PortfolioOptimizer(portfolio_cfg)

        # 调仓配置
        self.rebalance_freq = rebalance_cfg.get("frequency", "monthly")
        self.rebalance_weekday = rebalance_cfg.get("weekday", 0)
        self.rebalance_method = rebalance_cfg.get("method", "cost_benefit")

        # 创建调度器和调仓器（延迟导入避免循环依赖）
        from ..execution import create_rebalancer, create_scheduler

        self.scheduler = create_scheduler(rebalance_cfg)
        # method == "none" 时不创建调仓器，使用 Phase 4 的 flat cost 逻辑
        self.rebalancer = (
            create_rebalancer(rebalance_cfg)
            if self.rebalance_method != "none"
            else None
        )

        # 因子列表
        self.factor_names = flat.get("factors", [])

        # 个股权重上限（从 portfolio 配置读取）
        self.max_stock_weight = portfolio_cfg.get("max_stock_weight", 0.025)

    @staticmethod
    def _get_sub_config(flat: dict, key: str) -> dict:
        """从 flat dict 提取子配置"""
        sub = flat.get(key, {})
        if hasattr(sub, "model_dump"):
            return sub.model_dump()
        return sub if isinstance(sub, dict) else {}

    def run(
        self,
        pools: dict[str, list[str]] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> BacktestResult:
        """运行回测

        Args:
            pools: {pool_name: [stock_codes]}，None 则从配置读取
            start_date: 回测开始日期，None 则用配置
            end_date: 回测结束日期，None 则用配置

        Returns:
            BacktestResult
        """
        pools = pools or self._get_pools_from_config()
        if not pools:
            raise ValueError("未指定股票池 pools")

        start_date = start_date or self.backtest_start
        end_date = end_date or self.backtest_end

        logger.info(f"开始回测: {start_date} → {end_date}, 池: {list(pools.keys())}")

        # 1. 加载各池数据
        pool_data = self._load_pool_data(pools, start_date, end_date)

        # 2. 计算各池因子
        pool_factors = self._compute_pool_factors(pool_data)

        # 3. 计算前向收益和 IC
        pool_ic_df = self._compute_pool_ic(pool_data, pool_factors)

        # 4. 筛选强因子
        pool_strong_factors = self._select_strong_factors(pool_ic_df)

        # 保存供回测主循环使用
        self._pool_ic_df = pool_ic_df
        self._pool_strong_factors = pool_strong_factors

        # 5. 选股
        stock_weights_by_date = self._run_selection(
            pools, pool_data, pool_factors, pool_ic_df, pool_strong_factors
        )

        # 6. 回测主循环
        result = self._run_backtest_loop(
            pools, pool_data, stock_weights_by_date, start_date
        )

        return result

    def _get_pools_from_config(self) -> dict[str, list[str]]:
        """从配置读取股票池"""
        if self.config and self.config.pools:
            return dict(self.config.pools)
        return {}

    # ------------------------------------------------------------------
    # 数据加载
    # ------------------------------------------------------------------

    def _load_pool_data(
        self,
        pools: dict[str, list[str]],
        start_date: str,
        end_date: str,
    ) -> dict[str, dict[str, pl.DataFrame]]:
        """加载各池 OHLCV + 估值数据

        Returns:
            {pool_name: {"open": wide_df, "close": wide_df, ..., "pe_ratio": wide_df, ...}}
        """
        from ..data.base import pivot_to_wide

        pool_data = {}
        for pool_name, codes in pools.items():
            logger.info(f"加载池 {pool_name} 数据: {len(codes)} 只股票")
            ohlcv = self.data_catalog.get_ohlcv(
                codes, self.data_start_date, end_date, adjust="post"
            )

            # 尝试加载估值数据（仅股票，ETF 无估值）
            if codes and not codes[0].startswith(("51", "15", "56", "58")):
                try:
                    val_df = self.data_catalog.get_valuation(
                        codes, self.data_start_date, end_date
                    )
                    if val_df is not None and len(val_df) > 0:
                        for col in ["pe_ratio", "pb_ratio", "ps_ratio",
                                     "turnover_ratio", "market_cap", "dividend_ratio"]:
                            if col in val_df.columns:
                                ohlcv[col] = pivot_to_wide(val_df, col)
                        logger.debug(f"池 {pool_name} 估值数据已加载")
                except Exception as e:
                    logger.debug(f"池 {pool_name} 估值数据加载跳过: {e}")

            pool_data[pool_name] = ohlcv
        return pool_data

    # ------------------------------------------------------------------
    # 因子计算
    # ------------------------------------------------------------------

    def _compute_pool_factors(
        self, pool_data: dict[str, dict[str, pl.DataFrame]]
    ) -> dict[str, dict[str, pl.DataFrame]]:
        """计算各池因子

        Returns:
            {pool_name: {factor_name: factor_wide_df}}
        """
        pool_factors = {}

        # 如果未指定因子，根据可用字段自动选择（含估值字段）
        if not self.factor_names:
            first_data = next(iter(pool_data.values()), {})
            available_fields = list(first_data.keys())
            self.factor_names = self.factor_library.get_factors_by_fields(available_fields)
            logger.info(f"自动选择因子: {self.factor_names}")

        for pool_name, ohlcv in pool_data.items():
            logger.info(f"计算池 {pool_name} 因子: {self.factor_names}")
            factors = self.factor_library.compute_factors(self.factor_names, ohlcv)
            pool_factors[pool_name] = factors

        return pool_factors

    # ------------------------------------------------------------------
    # IC 分析
    # ------------------------------------------------------------------

    def _compute_pool_ic(
        self,
        pool_data: dict[str, dict[str, pl.DataFrame]],
        pool_factors: dict[str, dict[str, pl.DataFrame]],
    ) -> dict[str, pl.DataFrame]:
        """计算各池的 IC 数据

        Returns:
            {pool_name: ic_df}  ic_df: date + 各因子 IC 列

        Side effect: 存储 forward returns 到 self._pool_fwd_returns 供 ModelSelector 使用
        """
        pool_ic_df = {}
        self._pool_fwd_returns: dict[str, pl.DataFrame] = {}

        for pool_name, ohlcv in pool_data.items():
            close = ohlcv.get("close")
            if close is None or pool_name not in pool_factors:
                continue

            # 计算前向收益
            forward_returns = self._compute_forward_returns(close, FORWARD_RETURN_HORIZON)
            self._pool_fwd_returns[pool_name] = forward_returns

            # 对每个因子计算 IC 并合并
            factors = pool_factors[pool_name]
            ic_df = None

            for factor_name, factor_values in factors.items():
                try:
                    factor_ic = FactorAnalyzer.compute_ic(factor_values, forward_returns)
                    factor_ic = factor_ic.rename({"ic": factor_name})

                    if ic_df is None:
                        ic_df = factor_ic
                    else:
                        ic_df = ic_df.join(factor_ic, on="date")
                except Exception as e:
                    logger.warning(f"计算因子 {factor_name} IC 失败: {e}")

            if ic_df is not None:
                pool_ic_df[pool_name] = ic_df
                logger.info(f"池 {pool_name} IC 计算完成: {len(factors)} 个因子")

        return pool_ic_df

    @staticmethod
    def _compute_forward_returns(close: pl.DataFrame, horizon: int) -> pl.DataFrame:
        """计算前向收益宽表

        forward_return[t] = close[t + horizon] / close[t] - 1
        """
        return BacktestEngine._compute_returns(close, -horizon)

    @staticmethod
    def _compute_daily_returns(close: pl.DataFrame) -> pl.DataFrame:
        """计算日收益宽表

        daily_return[t] = close[t] / close[t-1] - 1
        """
        return BacktestEngine._compute_returns(close, 1)

    @staticmethod
    def _compute_returns(close: pl.DataFrame, shift: int) -> pl.DataFrame:
        """计算收益宽表（通用）

        shift > 0: 日收益 close[t]/close[t-shift] - 1
        shift < 0: 前向收益 close[t+|shift|]/close[t] - 1
        """
        date_col = close["date"]
        numeric_cols = [c for c in close.columns if c != "date"]
        close_numeric = close.select(numeric_cols)
        if shift > 0:
            ret_numeric = close_numeric / close_numeric.shift(shift) - 1
        else:
            ret_numeric = close_numeric.shift(shift) / close_numeric - 1
        return ret_numeric.with_columns(date_col)

    # ------------------------------------------------------------------
    # 强因子筛选
    # ------------------------------------------------------------------

    def _select_strong_factors(
        self, pool_ic_df: dict[str, pl.DataFrame]
    ) -> dict[str, list[str]]:
        """为每个池筛选强因子

        Returns:
            {pool_name: [factor_name, ...]}
        """
        pool_strong = {}

        for pool_name, ic_df in pool_ic_df.items():
            try:
                strong = self.selector.select_strong_factors(ic_df, self.train_end)
                if not strong:
                    factor_cols = [c for c in ic_df.columns if c != "date"]
                    logger.warning(f"池 {pool_name} 无强因子通过阈值，使用全部 {len(factor_cols)} 个因子")
                    pool_strong[pool_name] = factor_cols
                else:
                    pool_strong[pool_name] = strong
                    logger.info(f"池 {pool_name} 强因子: {strong}")
            except Exception as e:
                logger.warning(f"池 {pool_name} 强因子筛选失败: {e}")
                # 退化为使用所有因子
                factor_cols = [c for c in ic_df.columns if c != "date"]
                pool_strong[pool_name] = factor_cols

        return pool_strong

    # ------------------------------------------------------------------
    # 选股
    # ------------------------------------------------------------------

    def _run_selection(
        self,
        pools: dict[str, list[str]],
        pool_data: dict[str, dict[str, pl.DataFrame]],
        pool_factors: dict[str, dict[str, pl.DataFrame]],
        pool_ic_df: dict[str, pl.DataFrame],
        pool_strong_factors: dict[str, list[str]],
    ) -> dict[str, dict[str, dict[str, float]]]:
        """在每个调仓日为每个池选股

        Returns:
            {date_str: {pool_name: {code: weight}}}
        """
        # 获取所有池共有的日期
        all_dates = self._get_common_dates(pool_data)
        if not all_dates:
            return {}

        # 计算调仓日，并过滤到回测区间内
        # 数据从 data_start_date 加载（供 ML/RL 模型 lookback），但选股只在 backtest_start 之后执行
        rebalance_dates = self.scheduler.get_rebalance_dates(all_dates)
        rebalance_dates = {
            d for d in rebalance_dates
            if self.backtest_start <= d <= self.backtest_end
        }

        stock_weights_by_date: dict[str, dict[str, dict[str, float]]] = {}

        # 预计算每个池的 regime 序列（用于 regime_adaptive 选股）
        pool_regimes = self._precompute_regimes(pool_data, all_dates)

        for date_idx, date_str in enumerate(all_dates):
            if date_str not in rebalance_dates:
                continue

            pool_weights: dict[str, dict[str, float]] = {}

            for pool_name in pools:
                if pool_name not in pool_factors or pool_name not in pool_ic_df:
                    continue

                close = pool_data[pool_name].get("close")
                if close is None:
                    continue

                factors = pool_factors[pool_name]
                ic_df = pool_ic_df[pool_name]
                strong = pool_strong_factors.get(pool_name, [])
                stock_codes = pools[pool_name]

                regime = pool_regimes.get(pool_name, {}).get(date_str)

                try:
                    weights = self.selector.select(
                        factors=factors,
                        ic_df=ic_df,
                        stock_codes=stock_codes,
                        current_idx=date_idx,
                        close=close,
                        regime=regime,
                        strong_factors=strong,
                        fwd_returns=self._pool_fwd_returns.get(pool_name),
                    )

                    if weights:
                        # 应用组合约束
                        weights = self.portfolio_optimizer.apply_weight_cap(weights)
                        pool_weights[pool_name] = weights
                except Exception as e:
                    logger.warning(f"选股失败 {pool_name} @ {date_str}: {e}")

            if pool_weights:
                stock_weights_by_date[date_str] = pool_weights

        logger.info(f"选股完成: {len(stock_weights_by_date)} 个调仓日")
        return stock_weights_by_date

    def _precompute_regimes(
        self,
        pool_data: dict[str, dict[str, pl.DataFrame]],
        all_dates: list[str],
    ) -> dict[str, dict[str, str]]:
        """预计算各池的 regime 序列"""
        pool_regimes: dict[str, dict[str, str]] = {}

        for pool_name, ohlcv in pool_data.items():
            close = ohlcv.get("close")
            if close is None:
                continue

            # 计算等权组合日收益作为市场代理
            close_cols = [c for c in close.columns if c != "date"]
            if not close_cols:
                continue

            # 日收益
            daily_ret = self._compute_daily_returns(close)
            # 等权平均
            eq_ret = daily_ret.select(
                pl.mean_horizontal([pl.col(c) for c in close_cols]).alias("ret")
            )["ret"]

            regime_map: dict[str, str] = {}
            for i, date_str in enumerate(all_dates):
                if i >= 60:
                    try:
                        regime, _ = self.risk_manager.detect_regime(eq_ret, i)
                        regime_map[date_str] = regime
                    except Exception:
                        regime_map[date_str] = "weak_trend"
                else:
                    regime_map[date_str] = "weak_trend"

            pool_regimes[pool_name] = regime_map

        return pool_regimes

    @staticmethod
    def _get_common_dates(
        pool_data: dict[str, dict[str, pl.DataFrame]]
    ) -> list[str]:
        """获取所有池共有的日期列表（统一为 YYYY-MM-DD 字符串）"""
        def _to_str(d):
            if isinstance(d, str):
                return d
            if hasattr(d, "strftime"):
                return d.strftime("%Y-%m-%d")
            return str(d)

        date_sets = []
        for ohlcv in pool_data.values():
            close = ohlcv.get("close")
            if close is not None and "date" in close.columns:
                dates = [_to_str(d) for d in close["date"].to_list()]
                date_sets.append(set(dates))

        if not date_sets:
            return []

        common = date_sets[0]
        for ds in date_sets[1:]:
            common &= ds

        # 按顺序返回
        first_close = next(iter(pool_data.values())).get("close")
        if first_close is not None:
            all_dates = [_to_str(d) for d in first_close["date"].to_list()]
            return [d for d in all_dates if d in common]
        return sorted(common)

    # ------------------------------------------------------------------
    # 回测主循环
    # ------------------------------------------------------------------

    def _run_backtest_loop(
        self,
        pools: dict[str, list[str]],
        pool_data: dict[str, dict[str, pl.DataFrame]],
        stock_weights_by_date: dict[str, dict[str, dict[str, float]]],
        backtest_start: str,
    ) -> BacktestResult:
        """回测主循环"""
        all_dates = self._get_common_dates(pool_data)
        if not all_dates:
            return BacktestResult(nav=pl.Series([]), dates=[])

        # 找到回测起始索引
        bt_start_idx = 0
        for i, d in enumerate(all_dates):
            if str(d) >= backtest_start:
                bt_start_idx = i
                break

        # 预计算各池日收益宽表
        pool_daily_returns = {}
        pool_close = {}
        for pool_name, ohlcv in pool_data.items():
            close = ohlcv["close"]
            pool_close[pool_name] = close
            daily_ret = self._compute_daily_returns(close)
            pool_daily_returns[pool_name] = daily_ret

        # 预计算各池等权组合日收益序列（用于分配器和自适应调度器）
        pool_eq_returns = {}
        for pool_name, daily_ret_df in pool_daily_returns.items():
            ret_cols = [c for c in daily_ret_df.columns if c != "date"]
            if ret_cols:
                eq_ret = daily_ret_df.select(
                    pl.mean_horizontal([pl.col(c) for c in ret_cols]).alias("ret")
                )["ret"]
                pool_eq_returns[pool_name] = eq_ret

        # 调仓日（自适应调度器需日收益数据，传入第一个池的等权收益）
        first_eq_ret = next(iter(pool_eq_returns.values()), None) if pool_eq_returns else None
        rebalance_dates = self.scheduler.get_rebalance_dates(
            all_dates, daily_returns=first_eq_ret
        )

        # 初始化状态
        nav_list = [1.0]
        daily_returns_list: list[float] = []
        pool_weights = {pool: 1.0 / len(pools) for pool in pools}
        prev_pool_weights = dict(pool_weights)
        current_exposure = 1.0
        prev_scale = 1.0
        prev_effective_weights: dict[str, float] = {}  # 用于成本模型

        pool_weight_log: list[dict] = []
        exposure_log: list[dict] = []
        result_stock_weights: dict[str, dict[str, float]] = {}

        # 选股日期排序
        stock_rebal_dates_sorted = sorted(stock_weights_by_date.keys()) if stock_weights_by_date else []
        stock_rebal_idx = -1
        current_pool_stock_weights: dict[str, dict[str, float]] = {}

        # 构建净值 Series 用于风控
        nav_series = pl.Series([1.0])
        daily_ret_series = pl.Series([], dtype=pl.Float64)

        for i in range(1, len(all_dates)):
            date = all_dates[i]
            date_str = str(date)
            cost = 0.0

            # 1. 更新当前持仓（取最近的选股结果）
            while (
                stock_rebal_idx + 1 < len(stock_rebal_dates_sorted)
                and stock_rebal_dates_sorted[stock_rebal_idx + 1] <= date_str
            ):
                stock_rebal_idx += 1
                sw_date = stock_rebal_dates_sorted[stock_rebal_idx]
                current_pool_stock_weights = stock_weights_by_date[sw_date]

            # 2. 调仓日检查
            if date_str in rebalance_dates and i >= bt_start_idx:
                # 检测 regime
                if pool_eq_returns:
                    first_ret = next(iter(pool_eq_returns.values()))
                    try:
                        regime, _ = self.risk_manager.detect_regime(first_ret, i)
                    except Exception:
                        regime = "weak_trend"
                else:
                    regime = "weak_trend"

                # 分配池间权重
                try:
                    new_pool_weights = self.allocator.allocate(
                        pool_eq_returns,
                        i,
                        prev_pool_weights,
                        regime,
                        pool_ic_df=getattr(self, "_pool_ic_df", {}),
                        pool_strong_factors=getattr(self, "_pool_strong_factors", {}),
                    )
                    pool_weights = self.allocator.smooth_weights(
                        new_pool_weights, prev_pool_weights
                    )
                except Exception as e:
                    logger.warning(f"池间分配失败 @ {date_str}: {e}")
                    pool_weights = dict(prev_pool_weights)

                prev_pool_weights = dict(pool_weights)

                pool_weight_log.append(
                    {
                        "date": date_str,
                        "pool_weights": dict(pool_weights),
                        "regime": regime,
                    }
                )

            # 3. 风控暴露度
            try:
                effective_scale, regime = self.risk_manager.compute_exposure(
                    nav_series,
                    daily_ret_series if len(daily_ret_series) > 0 else pl.Series([0.0]),
                    i,
                    current_exposure,
                )
            except Exception as e:
                logger.warning(f"风控计算失败 @ {date_str}: {e}")
                effective_scale = current_exposure
                regime = "weak_trend"

            current_exposure = effective_scale

            # 4. 交易成本
            if date_str in rebalance_dates and i >= bt_start_idx:
                if self.rebalancer is not None:
                    # 使用成本模型计算（method != "none"）
                    new_eff_weights = self._compute_effective_weights(
                        current_pool_stock_weights,
                        pool_weights,
                        effective_scale,
                        self.max_stock_weight,
                    )
                    cost = self.rebalancer.cost_model.estimate(
                        prev_effective_weights, new_eff_weights
                    )
                    prev_effective_weights = dict(new_eff_weights)
                elif self.transaction_cost > 0:
                    # Phase 4 旧逻辑：flat cost（method == "none" 时向后兼容）
                    weight_turnover = sum(
                        abs(pool_weights.get(k, 0) - prev_pool_weights.get(k, 0))
                        for k in set(pool_weights) | set(prev_pool_weights)
                    )
                    scale_turnover = abs(effective_scale - prev_scale)
                    cost = self.transaction_cost * (weight_turnover + scale_turnover) / 2
            prev_scale = effective_scale

            # 5. 组合日收益
            daily_ret = self._compute_portfolio_daily_return(
                current_pool_stock_weights,
                pool_daily_returns,
                pool_weights,
                effective_scale,
                self.max_stock_weight,
                i,
            )

            daily_ret -= cost

            # 6. 净值更新
            new_nav = nav_list[-1] * (1 + daily_ret)
            nav_list.append(new_nav)
            daily_returns_list.append(daily_ret)

            # 更新风控用的序列
            nav_series = pl.Series(nav_list)
            daily_ret_series = pl.Series(daily_returns_list)

            # 7. 日志
            if i >= bt_start_idx:
                # 记录有效持仓权重
                effective_weights = self._compute_effective_weights(
                    current_pool_stock_weights,
                    pool_weights,
                    effective_scale,
                    self.max_stock_weight,
                )
                if effective_weights:
                    result_stock_weights[date_str] = effective_weights

                exposure_log.append(
                    {
                        "date": date_str,
                        "effective_scale": effective_scale,
                        "pool_weights": dict(pool_weights),
                        "regime": regime,
                        "transaction_cost": cost,
                        "daily_return": daily_ret,
                        "nav": new_nav,
                    }
                )

        # 截取回测区间的净值（归一化起点为1.0，排除预热期收益）
        nav_raw = nav_list[bt_start_idx:]
        bt_start_nav = nav_raw[0] if nav_raw else 1.0
        nav_array = [v / bt_start_nav for v in nav_raw]
        dates_array = [str(d) for d in all_dates[bt_start_idx:]]
        daily_returns_bt = daily_returns_list[bt_start_idx:]

        result = BacktestResult(
            nav=pl.Series(nav_array),
            dates=dates_array,
            strategy_name=self.config.strategy_name if self.config else "",
            strategy_version=self.config.strategy_version if self.config else "",
            stock_weights_by_date=result_stock_weights,
            pool_weight_log=pool_weight_log,
            exposure_log=exposure_log,
            daily_returns=pl.Series(daily_returns_bt),
            config=self.config,
        )

        logger.info(
            f"回测完成: {len(dates_array)} 天, 最终净值 {result.final_nav:.4f}"
        )

        return result

    def _compute_portfolio_daily_return(
        self,
        pool_stock_weights: dict[str, dict[str, float]],
        pool_daily_returns: dict[str, pl.DataFrame],
        pool_weights: dict[str, float],
        effective_scale: float,
        max_stock_weight: float,
        current_idx: int,
    ) -> float:
        """计算 N 池通用组合日收益

        参考 halo_index 的 _compute_capped_portfolio_return，泛化到 N 池。
        """
        if effective_scale <= 0:
            return 0.0

        # 1. 合并所有池的个股总权重 = pool_weight * stock_weight * effective_scale
        all_weights: dict[str, float] = {}
        for pool_name, stock_weights in pool_stock_weights.items():
            pool_w = pool_weights.get(pool_name, 0)
            if pool_w <= 0 or not stock_weights:
                continue

            for code, stock_w in stock_weights.items():
                total_w = stock_w * pool_w * effective_scale
                if code in all_weights:
                    all_weights[code] += total_w
                else:
                    all_weights[code] = total_w

        if not all_weights:
            return 0.0

        # 2. 应用个股总权重上限（迭代截断）
        all_weights = self._iterative_cap(all_weights, max_stock_weight)

        # 3. 加权求和
        daily_ret = 0.0
        for pool_name, stock_weights in pool_stock_weights.items():
            if pool_name not in pool_daily_returns:
                continue

            ret_df = pool_daily_returns[pool_name]
            if current_idx >= len(ret_df):
                continue

            ret_row = ret_df.row(current_idx, named=True)

            for code in stock_weights:
                if code in ret_row and ret_row[code] is not None:
                    val = ret_row[code]
                    if isinstance(val, (int, float)) and not np.isnan(val):
                        # 使用截断后的权重（如果该 code 在 all_weights 中）
                        w = all_weights.get(code, 0)
                        if w > 0:
                            daily_ret += w * float(val)

        return daily_ret

    @staticmethod
    def _iterative_cap(
        weights: dict[str, float], cap: float, iterations: int = 10
    ) -> dict[str, float]:
        """迭代截断权重上限"""
        result = dict(weights)

        for _ in range(iterations):
            over_cap = {k: v for k, v in result.items() if v > cap}
            if not over_cap:
                break

            excess = sum(v - cap for v in over_cap.values())
            for k in over_cap:
                result[k] = cap

            under_cap = {k: v for k, v in result.items() if v < cap}
            if under_cap:
                under_total = sum(under_cap.values())
                if under_total > 0:
                    for k in under_cap:
                        result[k] += excess * (under_cap[k] / under_total)
                        result[k] = min(result[k], cap)

        return result

    @staticmethod
    def _compute_effective_weights(
        pool_stock_weights: dict[str, dict[str, float]],
        pool_weights: dict[str, float],
        effective_scale: float,
        max_stock_weight: float,
    ) -> dict[str, float]:
        """计算有效持仓权重（用于日志记录）"""
        all_weights: dict[str, float] = {}
        for pool_name, stock_weights in pool_stock_weights.items():
            pool_w = pool_weights.get(pool_name, 0)
            if pool_w <= 0 or not stock_weights:
                continue

            for code, stock_w in stock_weights.items():
                total_w = stock_w * pool_w * effective_scale
                if code in all_weights:
                    all_weights[code] += total_w
                else:
                    all_weights[code] = total_w

        # 应用权重上限
        all_weights = BacktestEngine._iterative_cap(all_weights, max_stock_weight)

        # 过滤零权重
        return {k: v for k, v in all_weights.items() if v > 1e-6}


__all__ = ["BacktestEngine"]
