"""因子计算引擎：原始因子 + 衍生因子 + 预处理 + 标签构造

数据流:
  factors_wide (260因子) ──┐
  stock_daily_wide (衍生) ─┼──→ 合并 ──→ Winsorize ──→ Z-score ──→ X
  stock_hk_hold (北向) ────┘
  stock_daily_wide (收益) ──→ 5日前向超额收益 ──→ y

关键时序约束:
  - 因子值使用t日开盘前已知的数据（前一日收盘后计算）
  - 标签使用t日到t+5日的收益（严格未来数据）
  - 训练集尾部排除5天样本（防标签泄露到预测集）
"""
from __future__ import annotations

import numpy as np
import polars as pl
from typing import Any

from ohmyquant.core.logging import get_logger
import os

logger = get_logger(__name__)


class FactorEngine:
    """因子计算与预处理引擎"""

    def __init__(self, source, config: dict):
        """
        Args:
            source: DuckDBSource 实例
            config: 策略配置字典
        """
        self.source = source
        self.data_root = config.get("data", {}).get("data_root", os.getenv("DATA_ROOT", "data"))
        factors_cfg = config.get("factor_config", {})
        self.winsorize_q = factors_cfg.get("winsorize_quantile", 0.01)
        self.use_hk_hold = factors_cfg.get("use_hk_hold", True)
        self.hk_hold_window = factors_cfg.get("hk_hold_window", 5)
        self.derive_factors = factors_cfg.get("derive_factors", True)
        # 新增差异化数据源 (与factors_wide无重叠的orthogonal信号)
        self.use_margin = factors_cfg.get("use_margin", True)       # 融资融券
        self.use_money_flow = factors_cfg.get("use_money_flow", True)  # 大单资金流
        self.use_unlock = factors_cfg.get("use_unlock", True)       # 解禁压力
        self.prediction_horizon = config.get("walk_forward", {}).get("prediction_horizon", 5)
        self.benchmark = config.get("walk_forward", {}).get("benchmark", "000300.XSHG")

        # 缓存
        self._raw_factors_df: pl.DataFrame | None = None
        self._derived_df: pl.DataFrame | None = None
        self._hk_hold_df: pl.DataFrame | None = None
        self._margin_df: pl.DataFrame | None = None
        self._money_flow_df: pl.DataFrame | None = None
        self._unlock_df: pl.DataFrame | None = None
        self._price_df: pl.DataFrame | None = None
        self._all_factor_names: list[str] | None = None

    # ------------------------------------------------------------------
    # 数据加载
    # ------------------------------------------------------------------

    def _load_raw_factors(self, start_date: str, end_date: str, pool_codes: list[str]) -> pl.DataFrame:
        """加载factors_wide原始因子，自动筛选覆盖率>80%的因子

        优化：直接SQL查询，只加载池内股票+指定日期范围，避免全量加载
        """
        if self._raw_factors_df is not None:
            return self._raw_factors_df

        logger.info("加载factors_wide原始因子(仅池内股票)...")
        # 先获取所有因子列名
        schema_df = self.source.con.execute("SELECT * FROM factors_wide LIMIT 0").pl()
        all_factor_cols = [c for c in schema_df.columns if c not in ("date", "code")]
        logger.info(f"factors_wide共 {len(all_factor_cols)} 个因子列")

        # 构建SQL：只查询池内股票+日期范围，避免全量加载
        codes_normalized = [self.source.normalize_code(c) for c in pool_codes]
        # DuckDB IN 子句限制，分批处理
        batch_size = 300
        dfs = []
        for i in range(0, len(codes_normalized), batch_size):
            batch = codes_normalized[i:i+batch_size]
            codes_str = ", ".join(f"'{c}'" for c in batch)
            cols_str = ", ".join(all_factor_cols)
            sql = f"""
                SELECT date, code, {cols_str}
                FROM factors_wide
                WHERE code IN ({codes_str})
                  AND date >= '{start_date}'
                  AND date <= '{end_date}'
            """
            arrow_tbl = self.source.con.execute(sql).arrow()
            batch_df = pl.from_arrow(arrow_tbl)
            dfs.append(batch_df)

        df = pl.concat(dfs)
        if len(df) == 0:
            raise RuntimeError("无法加载factors_wide数据")

        # 统一类型
        df = df.with_columns(
            pl.col("date").cast(pl.Date),
            pl.col("code").map_elements(self.source.denormalize_code, return_dtype=pl.Utf8),
        )

        logger.info(f"加载完成: {len(df)} 行, {len(df.columns)-2} 因子")

        # 筛选覆盖率>80%的因子
        total_rows = len(df)
        coverage_threshold = 0.80
        valid_factors = []
        for col in all_factor_cols:
            if col in df.columns:
                non_null = df.select(pl.col(col).is_not_null().sum()).item()
                coverage = non_null / total_rows if total_rows > 0 else 0
                if coverage >= coverage_threshold:
                    valid_factors.append(col)

        logger.info(f"覆盖率>{coverage_threshold*100:.0f}%的因子: {len(valid_factors)}/{len(all_factor_cols)}")

        # 只保留有效因子 + date + code
        keep_cols = ["date", "code"] + valid_factors
        df = df.select([c for c in keep_cols if c in df.columns])

        self._raw_factors_df = df
        self._all_factor_names = valid_factors
        return df

    def _load_price_data(self, start_date: str, end_date: str, pool_codes: list[str]) -> pl.DataFrame:
        """加载日线行情（后复权），用于计算衍生因子和标签"""
        if self._price_df is not None:
            return self._price_df

        logger.info("加载日线行情(后复权)...")
        df = self.source.load_daily_price(pool_codes, start_date, end_date, adjust="post")
        if df is None or len(df) == 0:
            raise RuntimeError("无法加载行情数据")

        df = df.with_columns(pl.col("date").cast(pl.Date))
        df = df.sort(["code", "date"])
        self._price_df = df
        return df

    def _compute_derived_factors(self, price_df: pl.DataFrame) -> pl.DataFrame:
        """从行情数据计算衍生因子"""
        if not self.derive_factors:
            return pl.DataFrame()

        logger.info("计算衍生因子...")
        df = price_df.sort(["code", "date"])

        # 均线因子（加drv_前缀避免与factors_wide原始因子冲突）
        for n in [5, 10, 20, 60]:
            df = df.with_columns(
                pl.col("close").rolling_mean(window_size=n).over("code").alias(f"drv_MA{n}")
            )
            df = df.with_columns(
                ((pl.col("close") - pl.col(f"drv_MA{n}")) / pl.col(f"drv_MA{n}") * 100).alias(f"drv_BIAS{n}")
            )

        # 多周期动量
        for n in [1, 5, 10, 20, 60]:
            df = df.with_columns(
                (pl.col("close") / pl.col("close").shift(n).over("code") - 1).alias(f"drv_MOM_{n}d")
            )

        # 波动率
        df = df.with_columns(
            (pl.col("close") / pl.col("close").shift(1).over("code") - 1).alias("_daily_ret")
        )
        for n in [5, 10, 20, 60]:
            df = df.with_columns(
                pl.col("_daily_ret").rolling_std(window_size=n).over("code").alias(f"drv_VOL_{n}")
            )

        # 成交量比
        for n in [5, 20]:
            df = df.with_columns(
                (pl.col("volume") / pl.col("volume").rolling_mean(window_size=n).over("code")).alias(f"drv_VR_{n}")
            )

        # 反转因子
        df = df.with_columns(
            (-pl.col("drv_MOM_5d")).alias("drv_R5"),
            (-pl.col("drv_MOM_20d")).alias("drv_R20"),
        )

        # 波动率比
        df = df.with_columns(
            (pl.col("drv_VOL_20") / pl.col("drv_VOL_60")).alias("drv_VRatio_20_60")
        )

        df = df.drop("_daily_ret")

        # 衍生因子列名
        derived_cols = [
            "drv_MA5", "drv_MA10", "drv_MA20", "drv_MA60",
            "drv_BIAS5", "drv_BIAS10", "drv_BIAS20", "drv_BIAS60",
            "drv_MOM_1d", "drv_MOM_5d", "drv_MOM_10d", "drv_MOM_20d", "drv_MOM_60d",
            "drv_VOL_5", "drv_VOL_10", "drv_VOL_20", "drv_VOL_60",
            "drv_VR_5", "drv_VR_20", "drv_R5", "drv_R20", "drv_VRatio_20_60",
        ]
        keep_cols = ["date", "code"] + [c for c in derived_cols if c in df.columns]
        return df.select(keep_cols)

    def _load_hk_hold_factor(self, start_date: str, end_date: str) -> pl.DataFrame:
        """加载北向资金因子"""
        if not self.use_hk_hold:
            return pl.DataFrame()

        if self._hk_hold_df is not None:
            return self._hk_hold_df

        logger.info("加载北向资金因子...")
        w = self.hk_hold_window
        factor_name = f"hk_hold_ratio_change_{w}d"

        hk_df = self.source.con.execute(f"""
            SELECT date, code, share_ratio
            FROM stock_hk_hold
            ORDER BY code, date
        """).pl()

        if len(hk_df) == 0:
            logger.warning("北向资金数据为空")
            return pl.DataFrame()

        # 统一类型：date → Date, code → denormalized
        hk_df = hk_df.with_columns(
            pl.col("date").cast(pl.Date),
            pl.col("code").map_elements(self.source.denormalize_code, return_dtype=pl.Utf8),
        )
        hk_df = hk_df.group_by(["date", "code"]).agg(
            pl.col("share_ratio").sum().alias("hk_hold_ratio")
        )
        hk_df = hk_df.sort(["code", "date"])
        hk_df = hk_df.with_columns(
            (pl.col("hk_hold_ratio") - pl.col("hk_hold_ratio").shift(w).over("code")).alias(factor_name)
        )
        hk_df = hk_df.select(["date", "code", factor_name])

        self._hk_hold_df = hk_df
        return hk_df

    def _load_margin_factors(self, start_date: str, end_date: str, pool_codes: list[str]) -> pl.DataFrame:
        """加载融资融券因子 (杠杆资金动向, 与factors_wide无重叠)

        因子:
          margin_fin_chg5d  - 融资余额5日变化率 (杠杆做多情绪)
          margin_fin_chg20d - 融资余额20日变化率
          margin_sec_chg5d  - 融券余额5日变化率 (做空情绪)
        """
        if not self.use_margin:
            return pl.DataFrame()

        if self._margin_df is not None:
            return self._margin_df

        logger.info("加载融资融券因子...")
        codes_normalized = [self.source.normalize_code(c) for c in pool_codes]
        batch_size = 300
        dfs = []
        for i in range(0, len(codes_normalized), batch_size):
            batch = codes_normalized[i:i+batch_size]
            codes_str = ", ".join(f"'{c}'" for c in batch)
            sql = f"""
                SELECT date, code, fin_value, sec_value
                FROM stock_margin_trading
                WHERE code IN ({codes_str})
                  AND date >= '{start_date}'
                  AND date <= '{end_date}'
            """
            arrow_tbl = self.source.con.execute(sql).arrow()
            dfs.append(pl.from_arrow(arrow_tbl))

        if not dfs or sum(len(d) for d in dfs) == 0:
            logger.warning("融资融券数据为空")
            return pl.DataFrame()

        df = pl.concat(dfs)
        df = df.with_columns(
            pl.col("date").cast(pl.Date),
            pl.col("code").map_elements(self.source.denormalize_code, return_dtype=pl.Utf8),
        )
        df = df.sort(["code", "date"])

        # 融资余额5日/20日变化率
        for n in [5, 20]:
            df = df.with_columns(
                ((pl.col("fin_value") / pl.col("fin_value").shift(n).over("code")) - 1.0)
                .alias(f"margin_fin_chg{n}d")
            )
        # 融券余额5日变化率
        df = df.with_columns(
            ((pl.col("sec_value") / pl.col("sec_value").shift(5).over("code")) - 1.0)
            .alias("margin_sec_chg5d")
        )

        factor_cols = ["margin_fin_chg5d", "margin_fin_chg20d", "margin_sec_chg5d"]
        result = df.select(["date", "code"] + factor_cols)
        self._margin_df = result
        return result

    def _load_money_flow_factors(self, start_date: str, end_date: str, pool_codes: list[str]) -> pl.DataFrame:
        """加载大单资金流因子 (主力资金动向, 细粒度补充现有money_flow_20)

        因子:
          mf_net_big_5d  - 大单+超大单5日净流入均值 (标准化: /流通市值代理)
          mf_net_big_20d - 大单+超大单20日净流入均值
          mf_big_ratio_5d - 大单净流入占比5日均值 (相对总成交, scale-invariant)
        """
        if not self.use_money_flow:
            return pl.DataFrame()

        if self._money_flow_df is not None:
            return self._money_flow_df

        logger.info("加载大单资金流因子...")
        codes_normalized = [self.source.normalize_code(c) for c in pool_codes]
        batch_size = 300
        dfs = []
        for i in range(0, len(codes_normalized), batch_size):
            batch = codes_normalized[i:i+batch_size]
            codes_str = ", ".join(f"'{c}'" for c in batch)
            sql = f"""
                SELECT date, code,
                       inflow_l, inflow_xl, outflow_l, outflow_xl,
                       inflow_m, inflow_s, outflow_m, outflow_s
                FROM stock_money_flow
                WHERE code IN ({codes_str})
                  AND date >= '{start_date}'
                  AND date <= '{end_date}'
            """
            arrow_tbl = self.source.con.execute(sql).arrow()
            dfs.append(pl.from_arrow(arrow_tbl))

        if not dfs or sum(len(d) for d in dfs) == 0:
            logger.warning("资金流数据为空")
            return pl.DataFrame()

        df = pl.concat(dfs)
        df = df.with_columns(
            pl.col("date").cast(pl.Date),
            pl.col("code").map_elements(self.source.denormalize_code, return_dtype=pl.Utf8),
        )
        df = df.sort(["code", "date"])

        # 大单+超大单净流入
        df = df.with_columns(
            ((pl.col("inflow_l") + pl.col("inflow_xl"))
             - (pl.col("outflow_l") + pl.col("outflow_xl"))).alias("_net_big")
        )
        # 总成交额代理 = 所有流入+流出
        df = df.with_columns(
            (pl.col("inflow_l") + pl.col("inflow_m") + pl.col("inflow_s") + pl.col("inflow_xl")
             + pl.col("outflow_l") + pl.col("outflow_m") + pl.col("outflow_s") + pl.col("outflow_xl")
            ).alias("_total_flow")
        )
        # 大单净流入占比 (当日, scale-invariant)
        df = df.with_columns(
            pl.when(pl.col("_total_flow") > 0)
            .then(pl.col("_net_big") / pl.col("_total_flow"))
            .otherwise(0.0)
            .alias("_big_ratio")
        )

        # 5日/20日均值
        for n in [5, 20]:
            df = df.with_columns(
                pl.col("_net_big").rolling_mean(window_size=n).over("code").alias(f"mf_net_big_{n}d"),
            )
        df = df.with_columns(
            pl.col("_big_ratio").rolling_mean(window_size=5).over("code").alias("mf_big_ratio_5d"),
        )

        factor_cols = ["mf_net_big_5d", "mf_net_big_20d", "mf_big_ratio_5d"]
        result = df.select(["date", "code"] + factor_cols)
        self._money_flow_df = result
        return result

    def _load_unlock_factors(self, start_date: str, end_date: str, pool_codes: list[str]) -> pl.DataFrame:
        """加载解禁压力因子 (已知未来事件, 卖压信号, 与factors_wide无重叠)

        解禁日程在招股/增发时已公告, 属t日已知信息, 合法用于预测。
        采用前瞻窗口: 解禁比例在[t+1, t+N]日累计, 代表未来卖压。

        因子:
          unlock_rate_20d - 未来20交易日累计解禁比例
          unlock_rate_60d - 未来60交易日累计解禁比例
        """
        if not self.use_unlock:
            return pl.DataFrame()

        if self._unlock_df is not None:
            return self._unlock_df

        logger.info("加载解禁压力因子...")
        codes_normalized = [self.source.normalize_code(c) for c in pool_codes]
        batch_size = 300
        dfs = []
        for i in range(0, len(codes_normalized), batch_size):
            batch = codes_normalized[i:i+batch_size]
            codes_str = ", ".join(f"'{c}'" for c in batch)
            sql = f"""
                SELECT date, code, rate1
                FROM stock_locked_shares
                WHERE code IN ({codes_str})
                  AND date >= '{start_date}'
                  AND date <= '{end_date}'
            """
            arrow_tbl = self.source.con.execute(sql).arrow()
            dfs.append(pl.from_arrow(arrow_tbl))

        if not dfs or sum(len(d) for d in dfs) == 0:
            logger.warning("解禁数据为空")
            return pl.DataFrame()

        df = pl.concat(dfs)
        df = df.with_columns(
            pl.col("date").cast(pl.Date),
            pl.col("code").map_elements(self.source.denormalize_code, return_dtype=pl.Utf8),
        )
        df = df.sort(["code", "date"])

        # 解禁事件稀疏, 用cumsum差分实现前瞻窗口:
        # forward_sum_N(t) = cumsum(t+N) - cumsum(t) = sum of rate1 in [t+1, t+N]
        # 需要在完整交易日历网格上计算 (非交易日无行)
        df = df.with_columns(
            pl.col("rate1").fill_null(0.0).cum_sum().over("code").alias("_cumsum")
        )
        df = df.with_columns(
            (pl.col("_cumsum").shift(-20).over("code") - pl.col("_cumsum")).alias("unlock_rate_20d"),
            (pl.col("_cumsum").shift(-60).over("code") - pl.col("_cumsum")).alias("unlock_rate_60d"),
        )

        factor_cols = ["unlock_rate_20d", "unlock_rate_60d"]
        result = df.select(["date", "code"] + factor_cols)
        self._unlock_df = result
        return result

    # ------------------------------------------------------------------
    # 因子合并与预处理
    # ------------------------------------------------------------------

    def load_all_factors(
        self, start_date: str, end_date: str, pool_codes: list[str]
    ) -> pl.DataFrame:
        """加载并合并所有因子（原始 + 衍生 + 北向 + 融资融券 + 资金流 + 解禁）

        Returns:
            DataFrame: columns = [date, code, factor1, factor2, ...]
        """
        # 1. 原始因子
        raw_df = self._load_raw_factors(start_date, end_date, pool_codes)
        raw_factors = [c for c in raw_df.columns if c not in ("date", "code")]

        # 2. 衍生因子
        price_df = self._load_price_data(start_date, end_date, pool_codes)
        derived_df = self._compute_derived_factors(price_df)
        derived_factors = [c for c in derived_df.columns if c not in ("date", "code")] if len(derived_df) > 0 else []

        # 3. 北向资金因子
        hk_df = self._load_hk_hold_factor(start_date, end_date)
        hk_factors = [c for c in hk_df.columns if c not in ("date", "code")] if len(hk_df) > 0 else []

        # 4. 新增差异化因子 (融资融券 + 大单资金流 + 解禁压力)
        margin_df = self._load_margin_factors(start_date, end_date, pool_codes)
        margin_factors = [c for c in margin_df.columns if c not in ("date", "code")] if len(margin_df) > 0 else []
        money_flow_df = self._load_money_flow_factors(start_date, end_date, pool_codes)
        money_flow_factors = [c for c in money_flow_df.columns if c not in ("date", "code")] if len(money_flow_df) > 0 else []
        unlock_df = self._load_unlock_factors(start_date, end_date, pool_codes)
        unlock_factors = [c for c in unlock_df.columns if c not in ("date", "code")] if len(unlock_df) > 0 else []

        # 5. 合并
        logger.info(
            f"合并因子: 原始{len(raw_factors)} + 衍生{len(derived_factors)} + 北向{len(hk_factors)}"
            f" + 融资融券{len(margin_factors)} + 资金流{len(money_flow_factors)} + 解禁{len(unlock_factors)}"
        )
        df = raw_df
        if len(derived_df) > 0:
            df = df.join(derived_df, on=["date", "code"], how="left")
        if len(hk_df) > 0:
            df = df.join(hk_df, on=["date", "code"], how="left")
        if len(margin_df) > 0:
            df = df.join(margin_df, on=["date", "code"], how="left")
        if len(money_flow_df) > 0:
            df = df.join(money_flow_df, on=["date", "code"], how="left")
        if len(unlock_df) > 0:
            df = df.join(unlock_df, on=["date", "code"], how="left")

        # 6. 更新因子名列表
        self._all_factor_names = (
            raw_factors + derived_factors + hk_factors
            + margin_factors + money_flow_factors + unlock_factors
        )
        logger.info(f"合并后总因子数: {len(self._all_factor_names)}, 总行数: {len(df)}")

        return df

    @property
    def all_factor_names(self) -> list[str]:
        """所有可用因子名"""
        if self._all_factor_names is None:
            raise RuntimeError("请先调用 load_all_factors()")
        return self._all_factor_names

    # ------------------------------------------------------------------
    # 标签构造
    # ------------------------------------------------------------------

    def compute_labels(
        self, price_df: pl.DataFrame, benchmark_df: pl.DataFrame, horizon: int = 5
    ) -> pl.DataFrame:
        """计算5日前向超额收益标签

        Args:
            price_df: 行情数据 [date, code, close, ...]
            benchmark_df: 基准指数数据 [date, close, ...]
            horizon: 前向天数

        Returns:
            DataFrame: [date, code, label]
            label = stock_return(t, t+horizon) - benchmark_return(t, t+horizon)
        """
        logger.info(f"计算{horizon}日前向超额收益标签...")

        # 个股前向收益
        df = price_df.sort(["code", "date"])
        df = df.with_columns(
            (pl.col("close").shift(-horizon).over("code") / pl.col("close") - 1).alias("fwd_return")
        )

        # 基准前向收益
        bench = benchmark_df.sort("date")
        bench = bench.with_columns(
            (pl.col("close").shift(-horizon) / pl.col("close") - 1).alias("bench_fwd_return")
        )
        bench = bench.select(["date", "bench_fwd_return"])
        bench = bench.with_columns(pl.col("date").cast(pl.Date))

        # 合并计算超额收益
        df = df.with_columns(pl.col("date").cast(pl.Date))
        df = df.join(bench, on="date", how="left")
        df = df.with_columns(
            (pl.col("fwd_return") - pl.col("bench_fwd_return")).alias("label")
        )

        # 只保留需要的列
        result = df.select(["date", "code", "label"])
        return result

    # ------------------------------------------------------------------
    # 因子预处理
    # ------------------------------------------------------------------

    def winsorize(self, arr: np.ndarray, lower_q: float = 0.01, upper_q: float = 0.99) -> np.ndarray:
        """去极值：截尾到[lower_q, upper_q]分位"""
        lo = np.nanquantile(arr, lower_q)
        hi = np.nanquantile(arr, upper_q)
        return np.clip(arr, lo, hi)

    def zscore(self, arr: np.ndarray) -> np.ndarray:
        """Z-score标准化（忽略NaN）"""
        mean = np.nanmean(arr)
        std = np.nanstd(arr, ddof=1)
        if std < 1e-10:
            return np.zeros_like(arr)
        return (arr - mean) / std

    def preprocess_cross_section(
        self,
        factor_df: pl.DataFrame,
        factor_names: list[str],
        train_mask: np.ndarray | None = None,
        train_stats: dict[str, tuple[float, float]] | None = None,
    ) -> tuple[pl.DataFrame, dict[str, tuple[float, float]]]:
        """截面预处理：Winsorize → Z-score

        训练时: 计算并保存 Winsorize 分位 + Z-score 均值/标准差
        预测时: 使用训练集的统计量

        Args:
            factor_df: 因子数据 [date, code, factor1, ...]
            factor_names: 要预处理的因子名列表
            train_mask: 布尔数组，True=训练集行（用于计算统计量）
            train_stats: 预计算的统计量（预测时传入），格式 {factor: (lo, hi, mean, std)}

        Returns:
            (预处理后的DataFrame, 统计量字典)
        """
        stats: dict[str, tuple[float, float]] = {}

        # 确定计算统计量的行
        if train_stats is not None:
            # 预测模式：使用传入的统计量
            compute_mask = None
            stats = train_stats
        elif train_mask is not None:
            # 训练模式：用训练集行计算统计量
            compute_mask = train_mask
        else:
            # 默认：用全部行
            compute_mask = None

        result = factor_df
        for factor_name in factor_names:
            if factor_name not in result.columns:
                continue

            col_data = result[factor_name].to_numpy()

            if train_stats is None:
                # 训练模式：计算统计量
                if compute_mask is not None:
                    train_data = col_data[compute_mask]
                else:
                    train_data = col_data

                lo = np.nanquantile(train_data, self.winsorize_q)
                hi = np.nanquantile(train_data, 1 - self.winsorize_q)
                clipped = np.clip(train_data, lo, hi)
                mean = np.nanmean(clipped)
                std = np.nanstd(clipped, ddof=1)
                if std < 1e-10:
                    std = 1.0
                stats[factor_name] = (lo, hi, mean, std)
            else:
                # 预测模式：使用训练统计量
                lo, hi, mean, std = train_stats.get(factor_name, (0, 1, 0, 1))

            # 应用预处理
            clipped = np.clip(col_data, lo, hi)
            zscoreed = (clipped - mean) / std
            zscoreed = np.where(np.isnan(zscoreed), 0.0, zscoreed)
            result = result.with_columns(pl.Series(factor_name, zscoreed))

        return result, stats

    # ------------------------------------------------------------------
    # 数据准备（供Walk Forward调用）
    # ------------------------------------------------------------------

    def prepare_data(
        self,
        start_date: str,
        end_date: str,
        pool_codes: list[str],
    ) -> dict[str, Any]:
        """准备全部数据：因子 + 标签

        Returns:
            dict:
                "factor_df": pl.DataFrame [date, code, factor1, ...]
                "label_df": pl.DataFrame [date, code, label]
                "price_df": pl.DataFrame [date, code, close, open, ...]
                "factor_names": list[str]
                "pool_codes": list[str]
        """
        # 加载因子
        factor_df = self.load_all_factors(start_date, end_date, pool_codes)

        # 加载行情（用于标签）
        price_df = self._load_price_data(start_date, end_date, pool_codes)

        # 加载基准
        bench_df = self.source.load_index_data(self.benchmark, start_date, end_date)

        # 计算标签
        label_df = self.compute_labels(price_df, bench_df, self.prediction_horizon)

        return {
            "factor_df": factor_df,
            "label_df": label_df,
            "price_df": price_df,
            "factor_names": self.all_factor_names,
            "pool_codes": pool_codes,
        }
