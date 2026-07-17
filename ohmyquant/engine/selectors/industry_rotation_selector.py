"""行业轮动选股器

基于行业动量进行行业轮动，在强势行业中选强势个股。
适用于沪深300等大盘股池的行业轮动策略。

selection:
  method: industry_rotation    # 使用此选股器
  top_n: 10                  # 最终选股数量
  max_stock_weight: 0.10     # 单股上限
  ind:
    data_root: "..."         # 数据根目录(加载行业映射)
    top_industries: 5        # 选 Top-N 行业
    stocks_per_industry: 2   # 每行业选 M 只
    momentum_short: 20       # 短期动量窗口（行业排名用）
    momentum_long: 60        # 长期动量窗口（行业排名用）
    weight_short: 0.6        # 短期动量权重
    weight_long: 0.4         # 长期动量权重
    max_industry_weight: 0.30  # 单行业权重上限
    market_filter: true      # 大盘趋势过滤
    market_index: "000300.XSHG"  # 大盘指数
    market_ma_short: 20      # 短期均线
    market_ma_long: 60       # 长期均线
    # 多因子选股（可选，启用后个股层用因子评分替代动量）
    use_factors: false       # 是否启用多因子选股
    factor_names: [...]      # 因子名列表
    factor_weights: {...}    # 因子权重（按因子名）
    # ML选股（可选，启用后个股层用LightGBM预测收益替代因子评分）
    use_ml: false            # 是否启用ML选股
    ml_train_window: 252     # 训练窗口（天）
    ml_retrain_freq: 21      # 重训练频率（天）
    ml_target_horizon: 20    # 预测目标horizon（天）
    ml_n_estimators: 150     # LightGBM 树数
    ml_max_depth: 3          # 最大深度
    ml_learning_rate: 0.05   # 学习率
"""
from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl

from ...core.logging import get_logger
from ...core.plugin_system import register_selector
from ..selector import BaseSelector

logger = get_logger(__name__)


@register_selector("industry_rotation")
class IndustryRotationSelector(BaseSelector):
    """行业轮动选股器

    流程:
      1. 惰性加载行业映射 {code: sw_l1_name}
      2. 用 close 计算短期/长期动量 → 行业综合动量排名
      3. 选 Top-N 行业
      4. 每个选中行业内选 Top-M 只股票:
         - use_factors=false: 按个股动量排序
         - use_factors=true: 按多因子复合评分排序（聚宽260因子）
      5. 等权配置，应用个股权重上限
      6. (可选)大盘趋势过滤：跌破短期均线降仓50%，跌破长期均线空仓
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        ir_cfg = self.config.get("industry_rotation", {})
        self.data_root = ir_cfg.get(
            "data_root", "D:/Work/Project/download_a_share/data"
        )
        self.top_industries: int = ir_cfg.get("top_industries", 5)
        self.stocks_per_industry: int = ir_cfg.get("stocks_per_industry", 2)
        self.momentum_short: int = ir_cfg.get("momentum_short", 20)
        self.momentum_long: int = ir_cfg.get("momentum_long", 60)
        self.weight_short: float = ir_cfg.get("weight_short", 0.6)
        self.weight_long: float = ir_cfg.get("weight_long", 0.4)
        self.max_industry_weight: float = ir_cfg.get("max_industry_weight", 0.30)
        # 大盘趋势过滤
        self.market_filter: bool = ir_cfg.get("market_filter", False)
        self.market_index: str = ir_cfg.get("market_index", "000300.XSHG")
        self.market_ma_short: int = ir_cfg.get("market_ma_short", 20)
        self.market_ma_long: int = ir_cfg.get("market_ma_long", 60)
        # 多因子选股
        self.use_factors: bool = ir_cfg.get("use_factors", False)
        self.factor_names: list[str] = ir_cfg.get("factor_names", [])
        self.factor_weights: dict[str, float] = ir_cfg.get("factor_weights", {})
        # ML选股（LightGBM预测未来收益）
        self.use_ml: bool = ir_cfg.get("use_ml", False)
        self.ml_train_window: int = ir_cfg.get("ml_train_window", 252)
        self.ml_retrain_freq: int = ir_cfg.get("ml_retrain_freq", 21)
        self.ml_target_horizon: int = ir_cfg.get("ml_target_horizon", 20)
        self.ml_n_estimators: int = ir_cfg.get("ml_n_estimators", 150)
        self.ml_max_depth: int = ir_cfg.get("ml_max_depth", 3)
        self.ml_learning_rate: float = ir_cfg.get("ml_learning_rate", 0.05)
        self._industry_map: dict[str, str] | None = None
        self._market_close: pl.DataFrame | None = None
        self._factor_data: pl.DataFrame | None = None
        self._ml_model: Any = None
        self._ml_last_train_idx: int = -999

    def _load_industry_map(self) -> dict[str, str]:
        """惰性加载行业映射（申万一级行业）"""
        if self._industry_map is not None:
            return self._industry_map
        try:
            from ...data.sources.duckdb_source import DuckDBSource

            source = DuckDBSource({"data_root": self.data_root})
            self._industry_map = source.load_industry_map()
            logger.info(f"行业映射加载: {len(self._industry_map)} 只股票")
        except Exception as e:
            logger.warning(f"行业映射加载失败: {e}")
            self._industry_map = {}
        return self._industry_map

    def _load_market_close(self) -> pl.DataFrame | None:
        """惰性加载大盘指数收盘价（过滤 null 值）"""
        if self._market_close is not None:
            return self._market_close
        if not self.market_filter:
            return None
        try:
            from ...data.sources.duckdb_source import DuckDBSource

            source = DuckDBSource({"data_root": self.data_root})
            df = source.load_index_data(self.market_index)
            if df is not None and len(df) > 0:
                # 过滤 null close 值（早期数据可能缺失）
                self._market_close = (
                    df.select(["date", "close"])
                    .drop_nulls("close")
                    .sort("date")
                )
                logger.info(
                    f"大盘指数加载: {self.market_index}, "
                    f"{len(self._market_close)} 天（已过滤null）"
                )
        except Exception as e:
            logger.warning(f"大盘指数加载失败: {e}")
            self._market_close = None
        return self._market_close

    def _load_factor_data(self) -> pl.DataFrame | None:
        """惰性加载聚宽因子宽表数据"""
        if self._factor_data is not None:
            return self._factor_data
        if not self.use_factors or not self.factor_names:
            return None
        try:
            from ...data.sources.duckdb_source import DuckDBSource

            source = DuckDBSource({"data_root": self.data_root})
            df = source.load_factor_wide(factor_names=self.factor_names)
            if df is not None and len(df) > 0:
                self._factor_data = df.sort("date")
                logger.info(
                    f"因子数据加载: {len(df)} 行, {len(self.factor_names)} 个因子"
                )
        except Exception as e:
            logger.warning(f"因子数据加载失败: {e}")
            self._factor_data = None
        return self._factor_data

    def _compute_factor_scores(
        self, select_date: Any, stock_codes: list[str]
    ) -> dict[str, float]:
        """计算多因子复合评分

        对给定日期的截面因子值做 z-score 标准化后加权求和。

        Args:
            select_date: 选股日期
            stock_codes: 候选股票列表

        Returns:
            {code: composite_score}
        """
        factor_data = self._load_factor_data()
        if factor_data is None:
            return {}

        # 日期对齐：取 select_date 当天或之前最近的因子数据
        if hasattr(select_date, "date"):
            select_date_obj = select_date.date()
        else:
            select_date_obj = select_date

        # 过滤到选股日及之前的因子数据，取每个code最新的一条
        factor_before = factor_data.filter(
            pl.col("date").dt.date() <= select_date_obj
        )
        if len(factor_before) == 0:
            return {}

        # 取每个code最新截面（因子数据可能不是每天更新）
        factor截面 = (
            factor_before.sort("date", descending=True)
            .group_by("code")
            .first()
        )

        # 只保留候选池中的股票
        factor截面 = factor截面.filter(pl.col("code").is_in(stock_codes))
        if len(factor截面) == 0:
            return {}

        # 对每个因子做 z-score 标准化
        scores: dict[str, float] = {}
        factor_cols = [
            c for c in factor截面.columns if c in self.factor_names
        ]
        if not factor_cols:
            return {}

        # 计算每个因子的 z-score
        factor_scores: dict[str, dict[str, float]] = {}  # {factor: {code: zscore}}
        for factor_name in factor_cols:
            col_data = factor截面.select(["code", factor_name]).drop_nulls(
                factor_name
            )
            if len(col_data) < 5:
                continue
            vals = col_data[factor_name].to_numpy()
            mean = np.mean(vals)
            std = np.std(vals, ddof=1)
            if std < 1e-10:
                continue
            zscores = (vals - mean) / std
            codes = col_data["code"].to_list()
            factor_scores[factor_name] = {
                code: float(z) for code, z in zip(codes, zscores)
            }

        if not factor_scores:
            return {}

        # 加权求和（支持负权重实现反向因子：weight_sum 用 abs(w) 归一化）
        for code in stock_codes:
            total = 0.0
            weight_sum = 0.0
            for factor_name, code_scores in factor_scores.items():
                if code in code_scores:
                    w = self.factor_weights.get(factor_name, 1.0)
                    total += w * code_scores[code]
                    weight_sum += abs(w)
            if weight_sum > 0:
                scores[code] = total / weight_sum

        return scores

    def _compute_market_scale(self, select_idx: int, close: pl.DataFrame) -> float:
        """计算大盘趋势过滤系数

        跌破短期均线 → 0.5（降仓50%）
        跌破长期均线 → 0.0（空仓）
        否则 → 1.0（满仓）

        Args:
            select_idx: 选股截面索引（用 t-1 的数据）
            close: 候选池收盘价宽表（用于对齐日期）

        Returns:
            仓位缩放系数 [0.0, 1.0]
        """
        market_close = self._load_market_close()
        if market_close is None:
            return 1.0

        # 用候选池日期对齐大盘指数
        if select_idx >= len(close) or select_idx < self.market_ma_long + 1:
            return 1.0

        # 取选股日的日期
        select_date = close.row(select_idx, named=True).get("date")
        if select_date is None:
            return 1.0

        # 转为 date 类型比较（避免字符串比较 "2024-01-05 00:00:00" > "2024-01-05" 的bug）
        if hasattr(select_date, "date"):
            select_date_obj = select_date.date()
        else:
            from datetime import datetime
            select_date_obj = select_date if isinstance(select_date, datetime) else None
            if select_date_obj is None:
                return 1.0

        # 取大盘指数在 select_date 之前（含当天）的数据
        market_before = market_close.filter(pl.col("date").dt.date() <= select_date_obj)
        if len(market_before) < self.market_ma_long + 1:
            return 1.0

        prices = market_before["close"].to_list()
        current_price = prices[-1]
        ma_short = float(np.mean(prices[-self.market_ma_short:]))
        ma_long = float(np.mean(prices[-self.market_ma_long:]))

        if current_price < ma_long:
            return 0.0  # 跌破长期均线，空仓
        elif current_price < ma_short:
            return 0.5  # 跌破短期均线，降仓50%
        return 1.0

    def _build_ml_training_data(
        self, select_idx: int, close: pl.DataFrame, stock_codes: list[str]
    ) -> tuple[np.ndarray | None, np.ndarray | None]:
        """构建ML训练数据（向量化）

        用历史因子值预测未来收益。
        X = 因子值, y = 未来 horizon 日收益率

        Args:
            select_idx: 选股截面索引（用 t-1 数据）
            close: 候选池收盘价宽表
            stock_codes: 候选股票列表

        Returns:
            (X, y) 或 (None, None)
        """
        factor_data = self._load_factor_data()
        if factor_data is None:
            return None, None

        horizon = self.ml_target_horizon
        train_start_idx = max(0, select_idx - self.ml_train_window)
        train_end_idx = select_idx - horizon

        if train_end_idx <= train_start_idx + 60:
            return None, None

        close_dates = close["date"].to_list()
        start_date = close_dates[train_start_idx]
        end_date = close_dates[train_end_idx]
        # 统一为 date 类型（close 中可能是 datetime）
        if hasattr(start_date, "date"):
            start_date = start_date.date()
        if hasattr(end_date, "date"):
            end_date = end_date.date()

        factor_cols = [c for c in factor_data.columns if c in self.factor_names]
        if not factor_cols:
            return None, None

        # close 宽表转长表，按 code 分组计算未来收益
        close_long = close.melt(
            id_vars="date", variable_name="code", value_name="close"
        )
        # 统一 date 类型为 date（与因子数据对齐）
        close_long = close_long.with_columns(
            pl.col("date").cast(pl.Date).alias("date")
        )
        close_long = close_long.filter(
            pl.col("close").is_not_null()
            & pl.col("code").is_in(stock_codes)
            & (pl.col("date") >= start_date)
            & (pl.col("date") <= end_date)
        ).sort(["code", "date"])

        # 按 code 分组计算 horizon 日未来收益
        close_long = close_long.with_columns(
            pl.col("close").shift(-horizon).over("code").alias("close_future")
        ).with_columns(
            (pl.col("close_future") / pl.col("close") - 1.0).alias("fwd_return")
        )

        close_long = close_long.drop_nulls("fwd_return")

        if len(close_long) == 0:
            return None, None

        # 因子数据过滤到训练期，统一 date 类型
        factor_filtered = factor_data.select(
            ["date", "code"] + factor_cols
        ).with_columns(
            pl.col("date").cast(pl.Date).alias("date")
        ).filter(
            pl.col("code").is_in(stock_codes)
            & (pl.col("date") >= start_date)
            & (pl.col("date") <= end_date)
        )

        # inner join on (date, code)
        train_df = close_long.join(
            factor_filtered, on=["date", "code"], how="inner"
        ).drop_nulls(factor_cols)

        if len(train_df) < 200:
            return None, None

        # 截面 z-score 标准化（每个日期内，对每个因子做 z-score）
        # 这样模型学习相对排名而非绝对水平
        zscore_exprs = []
        for fc in factor_cols:
            zscore_exprs.append(
                ((pl.col(fc).cast(pl.Float64) - pl.col(fc).cast(pl.Float64).mean().over("date"))
                 / (pl.col(fc).cast(pl.Float64).std().over("date") + 1e-10)).alias(fc)
            )
        train_df = train_df.with_columns(zscore_exprs)
        # 替换 inf/nan 为 0
        train_df = train_df.with_columns(
            [pl.when(pl.col(fc).is_finite()).then(pl.col(fc)).otherwise(0.0).alias(fc) for fc in factor_cols]
        )

        X = train_df.select(factor_cols).to_numpy()
        y = train_df["fwd_return"].to_numpy()

        # 过滤极端收益（去极值）
        y_median = float(np.median(y))
        y_mad = float(np.median(np.abs(y - y_median)))
        if y_mad > 0:
            z = 0.6745 * (y - y_median) / y_mad
            mask = np.abs(z) < 5.0
            X = X[mask]
            y = y[mask]

        if len(X) < 200:
            return None, None

        logger.info(
            f"ML训练数据: {len(X)} 样本, {X.shape[1]} 特征, "
            f"窗口=[{start_date}, {end_date}]"
        )
        return X, y

    def _build_ml_prediction_features(
        self, select_date: Any, stock_codes: list[str]
    ) -> tuple[np.ndarray | None, list[str]]:
        """构建ML预测截面特征

        取 select_date 当天或之前最近的因子截面。
        """
        factor_data = self._load_factor_data()
        if factor_data is None:
            return None, []

        if hasattr(select_date, "date"):
            select_date_obj = select_date.date()
        else:
            select_date_obj = select_date

        factor_before = factor_data.filter(
            pl.col("date").dt.date() <= select_date_obj
        )
        if len(factor_before) == 0:
            return None, []

        # 取每个 code 最新截面
        factor截面 = (
            factor_before.sort("date", descending=True)
            .group_by("code")
            .first()
        )
        factor截面 = factor截面.filter(
            pl.col("code").is_in(stock_codes)
        )

        factor_cols = [c for c in factor截面.columns if c in self.factor_names]
        factor截面 = factor截面.drop_nulls(factor_cols)

        if len(factor截面) == 0:
            return None, []

        # 截面 z-score 标准化（与训练数据一致）
        for fc in factor_cols:
            mean_val = factor截面[fc].cast(pl.Float64).mean()
            std_val = factor截面[fc].cast(pl.Float64).std()
            if std_val is not None and float(std_val) > 1e-10:
                factor截面 = factor截面.with_columns(
                    ((pl.col(fc).cast(pl.Float64) - float(mean_val)) / float(std_val)).alias(fc)
                )
            else:
                factor截面 = factor截面.with_columns(
                    pl.lit(0.0).alias(fc)
                )

        X = factor截面.select(factor_cols).to_numpy()
        codes = factor截面["code"].to_list()
        return X, codes

    def _compute_ml_scores(
        self, select_idx: int, close: pl.DataFrame, stock_codes: list[str]
    ) -> dict[str, float]:
        """ML选股：用LightGBM预测未来收益作为评分

        Returns:
            {code: predicted_return}
        """
        # 判断是否需要重训练
        need_retrain = (
            self._ml_model is None
            or (select_idx - self._ml_last_train_idx) >= self.ml_retrain_freq
        )

        if need_retrain:
            try:
                X, y = self._build_ml_training_data(select_idx, close, stock_codes)
            except Exception as e:
                logger.warning(f"ML训练数据构建失败: {e}")
                return {}
            if X is None or len(X) < 200:
                logger.warning("ML训练数据不足，回退到因子评分")
                return {}

            try:
                import lightgbm as lgb

                self._ml_model = lgb.LGBMRegressor(
                    n_estimators=self.ml_n_estimators,
                    max_depth=self.ml_max_depth,
                    learning_rate=self.ml_learning_rate,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    verbose=-1,
                    n_jobs=-1,
                )
                self._ml_model.fit(X, y)
                self._ml_last_train_idx = select_idx
                logger.info(
                    f"ML模型训练完成: {self.ml_n_estimators} 树, "
                    f"深度={self.ml_max_depth}"
                )
            except Exception as e:
                logger.warning(f"ML训练失败: {e}")
                return {}

        # 构建预测特征
        select_date = close.row(select_idx, named=True).get("date")
        X_pred, pred_codes = self._build_ml_prediction_features(
            select_date, stock_codes
        )
        if X_pred is None or len(X_pred) == 0:
            return {}

        scores = self._ml_model.predict(X_pred)
        return {code: float(s) for code, s in zip(pred_codes, scores)}

    def select(
        self,
        factors: dict[str, pl.DataFrame],
        ic_df: pl.DataFrame,
        stock_codes: list[str],
        current_idx: int,
        close: pl.DataFrame,
        regime: str | None = None,
        strong_factors: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, float] | None:
        """行业轮动选股

        Args: 见 BaseSelector.select
        Returns: {code: weight} 或 None
        """
        # 数据不足，跳过（多预留1天避免前视偏差：用 t-1 截面选股，t 日持有）
        select_idx = current_idx - 1
        if select_idx < self.momentum_long + 1:
            return None

        industry_map = self._load_industry_map()
        if not industry_map:
            return None

        # 大盘趋势过滤（用 t-1 数据判断）
        market_scale = 1.0
        if self.market_filter:
            market_scale = self._compute_market_scale(select_idx, close)
            if market_scale <= 0.0:
                logger.debug(f"大盘跌破长期均线，空仓 @ idx={current_idx}")
                return None  # 空仓

        # 计算短期/长期动量（基于 close）
        close_cols = [c for c in close.columns if c != "date"]
        close_numeric = close.select(close_cols)
        mom_short = close_numeric / close_numeric.shift(self.momentum_short) - 1
        mom_long = close_numeric / close_numeric.shift(self.momentum_long) - 1

        if select_idx >= len(mom_short):
            return None

        # 取昨日截面动量（防前视偏差：t-1 日选股，t 日持有赚 close[t]/close[t-1]-1）
        short_row = mom_short.row(select_idx, named=True)
        long_row = mom_long.row(select_idx, named=True)

        # 计算每只股票的综合动量 + 行业归属
        stock_momentum: dict[str, float] = {}
        stock_industry: dict[str, str] = {}
        for code in stock_codes:
            if code not in industry_map:
                continue
            s = short_row.get(code)
            l = long_row.get(code)
            if s is None or l is None:
                continue
            if isinstance(s, (int, float)) and isinstance(l, (int, float)):
                if not (np.isnan(s) or np.isnan(l)):
                    stock_momentum[code] = (
                        self.weight_short * float(s) + self.weight_long * float(l)
                    )
                    stock_industry[code] = industry_map[code]

        if not stock_momentum:
            return None

        # 按行业分组，计算行业平均动量
        industry_stocks: dict[str, list[str]] = {}
        industry_momentum_sum: dict[str, float] = {}
        for code, mom in stock_momentum.items():
            ind = stock_industry[code]
            industry_stocks.setdefault(ind, []).append(code)
            industry_momentum_sum[ind] = industry_momentum_sum.get(ind, 0.0) + mom

        # 行业平均动量
        industry_momentum: dict[str, float] = {
            ind: industry_momentum_sum[ind] / len(industry_stocks[ind])
            for ind in industry_stocks
        }

        # 选 Top-N 行业
        sorted_industries = sorted(
            industry_momentum.items(), key=lambda x: x[1], reverse=True
        )
        top_industries = [ind for ind, _ in sorted_industries[: self.top_industries]]

        if not top_industries:
            return None

        # 每个选中行业选 Top-M 只股票
        # use_ml=true: 按ML预测收益排序
        # use_factors=true: 按多因子复合评分排序
        # 否则: 按个股动量排序
        stock_scores: dict[str, float] = stock_momentum  # 默认用动量
        if self.use_ml:
            ml_scores = self._compute_ml_scores(select_idx, close, stock_codes)
            if ml_scores:
                stock_scores = ml_scores
                logger.debug(f"使用ML预测评分: {len(ml_scores)} 只有评分")
            elif self.use_factors:
                # ML失败时回退到因子评分
                select_date = close.row(select_idx, named=True).get("date")
                factor_scores = self._compute_factor_scores(select_date, stock_codes)
                if factor_scores:
                    stock_scores = factor_scores
        elif self.use_factors:
            select_date = close.row(select_idx, named=True).get("date")
            factor_scores = self._compute_factor_scores(select_date, stock_codes)
            if factor_scores:
                stock_scores = factor_scores
                logger.debug(
                    f"使用多因子评分: {len(factor_scores)} 只有评分"
                )

        selected: list[str] = []
        for ind in top_industries:
            stocks_in_ind = industry_stocks[ind]
            sorted_stocks = sorted(
                stocks_in_ind,
                key=lambda c: stock_scores.get(c, -float("inf")),
                reverse=True,
            )
            selected.extend(sorted_stocks[: self.stocks_per_industry])

        if not selected:
            return None

        # 等权配置
        n_stocks = len(selected)
        base_weight = 1.0 / n_stocks
        weights = {code: base_weight for code in selected}

        # 应用个股权重上限
        weights = self.apply_weight_cap(weights, self.max_stock_weight)

        # 应用大盘趋势过滤系数（降仓）
        if market_scale < 1.0:
            weights = {k: v * market_scale for k, v in weights.items()}
            logger.debug(
                f"大盘趋势过滤: 仓位×{market_scale:.1f} @ idx={current_idx}"
            )

        logger.debug(
            f"行业轮动选股: {n_stocks} 只, "
            f"行业数={len(top_industries)}, "
            f"权重范围=[{min(weights.values()):.3f}, {max(weights.values()):.3f}]"
        )
        return weights

    def select_strong_factors(
        self, ic_df: pl.DataFrame, train_end: str
    ) -> list[str]:
        """返回所有因子（行业轮动不依赖 IC 筛选）"""
        return [c for c in ic_df.columns if c != "date"]


__all__ = ["IndustryRotationSelector"]
