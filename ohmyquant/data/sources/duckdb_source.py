"""DuckDB 数据源

通过 DuckDB SQL 视图查询 Parquet 文件，性能优于直接扫描 Parquet（支持谓词下推）。
兼容 download_a_share 的数据目录结构。

数据目录结构:
  data/
  ├── stock_daily_wide_partitioned/year=YYYY/data.parquet  (行情+估值+融资融券+资金流+行业)
  ├── etf_daily_wide_partitioned/year=YYYY/data.parquet
  ├── parquet/
  │   ├── trade_calendar/year=YYYY/data.parquet
  │   ├── index_daily_price/year=YYYY/data.parquet
  │   ├── stock_valuation/...
  │   ├── stock_money_flow/...
  │   └── ...
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from ...core.logging import get_logger
from ...core.plugin_system import PluginType, register_data_source
from ...core.types import Code, DateLike
from ..base import DataSource

logger = get_logger(__name__)


@register_data_source("duckdb")
class DuckDBSource(DataSource):
    """DuckDB 数据源

    通过 DuckDB 创建视图查询 Parquet，Arrow→polars 零拷贝。
    兼容 download_a_share 的数据目录。

    用法:
        source = DuckDBSource({"data_root": "D:/Work/Project/download_a_share/data"})
        df = source.load_daily_price(["000001.SZ"], "2024-01-01", "2024-12-31")
    """

    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self.data_root = Path(cfg.get("data_root", "D:/Work/Project/download_a_share/data"))
        self._con: Any = None  # duckdb connection (lazy init)

    @property
    def con(self):
        """惰性初始化 DuckDB 连接"""
        if self._con is None:
            try:
                import duckdb
            except ImportError as e:
                raise ImportError("DuckDB 未安装，请运行: pip install duckdb") from e
            self._con = duckdb.connect()
            self._create_views()
        return self._con

    def _create_views(self):
        """创建 DuckDB 视图覆盖 Parquet 文件"""
        import duckdb

        views = {
            "stock_daily_wide": "stock_daily_wide_partitioned/**/*.parquet",
            "etf_daily_wide": "etf_daily_wide_partitioned/**/*.parquet",
            "trade_calendar": "parquet/trade_calendar/**/*.parquet",
            "index_daily_price": "parquet/index_daily_price/**/*.parquet",
            "stock_valuation": "parquet/stock_valuation/**/*.parquet",
            "stock_money_flow": "parquet/stock_money_flow/**/*.parquet",
            "stock_margin_trading": "parquet/stock_margin_trading/**/*.parquet",
            "stock_industry": "parquet/stock_industry/**/*.parquet",
            "stock_st_status": "parquet/stock_st_status/**/*.parquet",
            "security_info": "parquet/security_info/**/*.parquet",
            "index_constituents": "parquet/index_constituents/**/*.parquet",
            # 财务报表
            "stock_income": "parquet/stock_income/**/*.parquet",
            "stock_balance": "parquet/stock_balance/**/*.parquet",
            "stock_cash_flow": "parquet/stock_cash_flow/**/*.parquet",
            "stock_indicator": "parquet/stock_indicator/**/*.parquet",
            # 龙虎榜 / 北向资金 / 限售解禁
            "stock_billboard": "parquet/stock_billboard/**/*.parquet",
            "stock_hk_hold": "parquet/stock_hk_hold/**/*.parquet",
            "stock_locked_shares": "parquet/stock_locked_shares/**/*.parquet",
            # 行业日频 / 概念
            "stock_industry_daily": "parquet/stock_industry_daily/**/*.parquet",
            # 因子宽表
            "factors_wide": "parquet/factors_wide/**/*.parquet",
            # ETF 扩展数据
            "etf_net_value": "parquet/etf_net_value/**/*.parquet",
            "etf_share": "parquet/etf_share/**/*.parquet",
            "etf_margin_trading": "parquet/etf_margin_trading/**/*.parquet",
            "etf_portfolio_stock": "parquet/etf_portfolio_stock/**/*.parquet",
            # 概念分类 + 聚宽原始因子库
            "stock_concept": "parquet/stock_concept/**/*.parquet",
            "factors": "parquet/factors/**/*.parquet",
        }

        for view_name, pattern in views.items():
            glob_path = str(self.data_root / pattern).replace("\\", "/")
            try:
                # 排除分区列 year，使用 union_by_name 处理跨年 schema 不一致
                self._con.execute(
                    f"CREATE OR REPLACE VIEW {view_name} AS "
                    f"SELECT * EXCLUDE (year) FROM read_parquet('{glob_path}', hive_partitioning=1, union_by_name=true)"
                )
                logger.debug(f"创建视图: {view_name}")
            except Exception as e:
                logger.debug(f"跳过视图 {view_name}: {e}")

    # ------------------------------------------------------------------
    # 行情数据
    # ------------------------------------------------------------------

    def load_daily_price(
        self,
        codes: list[Code],
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
        adjust: str = "post",
    ) -> pl.DataFrame:
        """加载日频行情（从宽表）"""
        if not codes:
            return pl.DataFrame()

        asset_type = self._detect_asset_type(codes[0])
        table = "etf_daily_wide" if asset_type == "etf" else "stock_daily_wide"

        codes_normalized = [self.normalize_code(c) for c in codes]
        codes_str = ", ".join(f"'{c}'" for c in codes_normalized)

        prefix = "postfq_" if adjust == "post" else ""
        sql = f"""
            SELECT
                date,
                code,
                {prefix}open AS open,
                {prefix}high AS high,
                {prefix}low AS low,
                {prefix}close AS close,
                {prefix}volume AS volume,
                money,
                paused,
                high_limit,
                low_limit
            FROM {table}
            WHERE code IN ({codes_str})
        """
        if start_date is not None:
            sql += f" AND date >= '{start_date}'"
        if end_date is not None:
            sql += f" AND date <= '{end_date}'"
        sql += " ORDER BY code, date"

        try:
            arrow_tbl = self.con.execute(sql).arrow()
            df = pl.from_arrow(arrow_tbl)
        except Exception as e:
            logger.error(f"加载行情失败: {e}")
            return pl.DataFrame()

        # 代码反标准化
        df = df.with_columns(
            pl.col("code").map_elements(self.denormalize_code, return_dtype=pl.Utf8)
        )
        return df

    def load_valuation(
        self,
        codes: list[Code],
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """加载估值数据（从宽表）"""
        if not codes:
            return pl.DataFrame()

        codes_normalized = [self.normalize_code(c) for c in codes]
        codes_str = ", ".join(f"'{c}'" for c in codes_normalized)

        sql = f"""
            SELECT
                date, code,
                turnover_ratio, market_cap, circulating_market_cap,
                pe_ratio, pe_ratio_lyr, pb_ratio, ps_ratio,
                pcf_ratio, pcf_ratio2, capitalization, circulating_cap,
                dividend_ratio
            FROM stock_daily_wide
            WHERE code IN ({codes_str})
        """
        if start_date is not None:
            sql += f" AND date >= '{start_date}'"
        if end_date is not None:
            sql += f" AND date <= '{end_date}'"
        sql += " ORDER BY code, date"

        arrow_tbl = self.con.execute(sql).arrow()
        df = pl.from_arrow(arrow_tbl)
        return df.with_columns(
            pl.col("code").map_elements(self.denormalize_code, return_dtype=pl.Utf8)
        )

    def load_money_flow(
        self,
        codes: list[Code],
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """加载资金流向（从宽表）"""
        if not codes:
            return pl.DataFrame()

        codes_normalized = [self.normalize_code(c) for c in codes]
        codes_str = ", ".join(f"'{c}'" for c in codes_normalized)

        sql = f"""
            SELECT
                date, code,
                fin_value, fin_buy_value, fin_refund_value,
                sec_value, sec_sell_value, sec_refund_value, fin_sec_value,
                inflow_l, inflow_m, inflow_s, inflow_xl,
                outflow_l, outflow_m, outflow_s, outflow_xl
            FROM stock_daily_wide
            WHERE code IN ({codes_str})
        """
        if start_date is not None:
            sql += f" AND date >= '{start_date}'"
        if end_date is not None:
            sql += f" AND date <= '{end_date}'"
        sql += " ORDER BY code, date"

        arrow_tbl = self.con.execute(sql).arrow()
        df = pl.from_arrow(arrow_tbl)
        return df.with_columns(
            pl.col("code").map_elements(self.denormalize_code, return_dtype=pl.Utf8)
        )

    def load_margin(
        self,
        codes: list[Code],
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """加载融资融券（从宽表）"""
        if not codes:
            return pl.DataFrame()

        codes_normalized = [self.normalize_code(c) for c in codes]
        codes_str = ", ".join(f"'{c}'" for c in codes_normalized)

        sql = f"""
            SELECT
                date, code,
                fin_value, fin_buy_value, fin_refund_value,
                sec_value, sec_sell_value, sec_refund_value, fin_sec_value
            FROM stock_daily_wide
            WHERE code IN ({codes_str})
        """
        if start_date is not None:
            sql += f" AND date >= '{start_date}'"
        if end_date is not None:
            sql += f" AND date <= '{end_date}'"
        sql += " ORDER BY code, date"

        arrow_tbl = self.con.execute(sql).arrow()
        df = pl.from_arrow(arrow_tbl)
        return df.with_columns(
            pl.col("code").map_elements(self.denormalize_code, return_dtype=pl.Utf8)
        )

    def load_industry_map(self, date: DateLike | None = None) -> dict[str, str]:
        """加载行业映射（从宽表取最新截面）"""
        sql = """
            SELECT code, sw_l1_name
            FROM stock_daily_wide
        """
        if date is not None:
            sql += f" WHERE date <= '{date}'"
        sql += " ORDER BY date DESC"

        try:
            arrow_tbl = self.con.execute(sql).arrow()
            df = pl.from_arrow(arrow_tbl)
        except Exception:
            return {}

        # 取每只股票最新的行业分类
        df = df.unique(subset=["code"], keep="first").drop_nulls("sw_l1_name")
        result: dict[str, str] = {}
        for row in df.iter_rows(named=True):
            code = self.denormalize_code(row["code"])
            result[code] = row["sw_l1_name"]
        return result

    def load_index_data(
        self,
        index_code: Code,
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """加载指数行情"""
        code_normalized = self.normalize_code(index_code)
        sql = f"""
            SELECT date, code, open, high, low, close, volume, money, pre_close, avg
            FROM index_daily_price
            WHERE code = '{code_normalized}'
        """
        if start_date is not None:
            sql += f" AND date >= '{start_date}'"
        if end_date is not None:
            sql += f" AND date <= '{end_date}'"
        sql += " ORDER BY date"

        arrow_tbl = self.con.execute(sql).arrow()
        df = pl.from_arrow(arrow_tbl)
        return df.with_columns(
            pl.col("code").map_elements(self.denormalize_code, return_dtype=pl.Utf8)
        )

    # ------------------------------------------------------------------
    # 交易日历与元数据
    # ------------------------------------------------------------------

    def get_trade_calendar(self, start_date: str, end_date: str) -> list[str]:
        """获取交易日历"""
        sql = f"""
            SELECT date
            FROM trade_calendar
            WHERE is_trade_day = true
              AND date >= '{start_date}'
              AND date <= '{end_date}'
            ORDER BY date
        """
        try:
            arrow_tbl = self.con.execute(sql).arrow()
            df = pl.from_arrow(arrow_tbl)
            return df["date"].dt.strftime("%Y-%m-%d").to_list()
        except Exception as e:
            logger.warning(f"获取交易日历失败，使用内置规则: {e}")
            from .calendar import TradeCalendar

            return TradeCalendar._builtin_calendar(start_date, end_date)

    def get_latest_date(self) -> str:
        """获取最新数据日期"""
        try:
            sql = "SELECT MAX(date) as latest FROM stock_daily_wide"
            arrow_tbl = self.con.execute(sql).arrow()
            df = pl.from_arrow(arrow_tbl)
            latest = df["latest"][0]
            if hasattr(latest, "strftime"):
                return latest.strftime("%Y-%m-%d")
            return str(latest)[:10]
        except Exception:
            from datetime import date

            return date.today().strftime("%Y-%m-%d")

    def filter_tradable(self, codes: list[Code], date: DateLike | None = None) -> set[Code]:
        """过滤可交易标的（非ST、非停牌）"""
        if not codes:
            return set()
        codes_normalized = [self.normalize_code(c) for c in codes]
        codes_str = ", ".join(f"'{c}'" for c in codes_normalized)

        sql = f"""
            SELECT code, paused, is_st
            FROM stock_daily_wide
            WHERE code IN ({codes_str})
        """
        if date is not None:
            sql += f" AND date = (SELECT MAX(date) FROM stock_daily_wide WHERE date <= '{date}')"
        else:
            sql += " AND date = (SELECT MAX(date) FROM stock_daily_wide)"

        try:
            arrow_tbl = self.con.execute(sql).arrow()
            df = pl.from_arrow(arrow_tbl)
        except Exception:
            return set(codes)

        # 过滤停牌和ST
        tradable = df.filter(
            (pl.col("paused") == False) & (pl.col("is_st") == False)
        )
        return {self.denormalize_code(c) for c in tradable["code"].to_list()}

    def get_all_stocks(self, date: DateLike | None = None) -> list[Code]:
        """获取全部股票代码"""
        sql = "SELECT DISTINCT code FROM stock_daily_wide"
        if date is not None:
            sql += f" WHERE date = (SELECT MAX(date) FROM stock_daily_wide WHERE date <= '{date}')"
        else:
            sql += " WHERE date = (SELECT MAX(date) FROM stock_daily_wide)"

        try:
            arrow_tbl = self.con.execute(sql).arrow()
            df = pl.from_arrow(arrow_tbl)
            return [self.denormalize_code(c) for c in df["code"].to_list()]
        except Exception:
            return []

    def get_all_etfs(self, date: DateLike | None = None) -> list[Code]:
        """获取全部ETF代码"""
        sql = "SELECT DISTINCT code FROM etf_daily_wide"
        if date is not None:
            sql += f" WHERE date = (SELECT MAX(date) FROM etf_daily_wide WHERE date <= '{date}')"
        else:
            sql += " WHERE date = (SELECT MAX(date) FROM etf_daily_wide)"

        try:
            arrow_tbl = self.con.execute(sql).arrow()
            df = pl.from_arrow(arrow_tbl)
            return [self.denormalize_code(c) for c in df["code"].to_list()]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # 扩展数据：财务报表 / 龙虎榜 / 北向资金 / 限售解禁 / 因子宽表
    # ------------------------------------------------------------------

    def load_financial_statement(
        self,
        statement_type: str,
        codes: list[Code],
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """加载财务报表

        Args:
            statement_type: income / balance / cash_flow / indicator
            codes: 股票代码列表
            start_date: 开始日期（按报告期 statDate 过滤）
            end_date: 结束日期（按报告期 statDate 过滤）
        """
        table_map = {
            "income": "stock_income",
            "balance": "stock_balance",
            "cash_flow": "stock_cash_flow",
            "indicator": "stock_indicator",
        }
        table = table_map.get(statement_type)
        if table is None or not codes:
            return pl.DataFrame()

        codes_normalized = [self.normalize_code(c) for c in codes]
        codes_str = ", ".join(f"'{c}'" for c in codes_normalized)

        sql = f"SELECT * FROM {table} WHERE code IN ({codes_str})"
        if start_date is not None:
            sql += f" AND statDate >= '{start_date}'"
        if end_date is not None:
            sql += f" AND statDate <= '{end_date}'"
        sql += " ORDER BY code, statDate"

        try:
            arrow_tbl = self.con.execute(sql).arrow()
            df = pl.from_arrow(arrow_tbl)
            return df.with_columns(
                pl.col("code").map_elements(self.denormalize_code, return_dtype=pl.Utf8)
            )
        except Exception as e:
            logger.warning(f"加载财务报表 {statement_type} 失败: {e}")
            return pl.DataFrame()

    def load_billboard(
        self,
        codes: list[Code] | None = None,
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """加载龙虎榜数据"""
        sql = "SELECT * FROM stock_billboard WHERE 1=1"
        if codes:
            codes_normalized = [self.normalize_code(c) for c in codes]
            codes_str = ", ".join(f"'{c}'" for c in codes_normalized)
            sql += f" AND code IN ({codes_str})"
        if start_date is not None:
            sql += f" AND date >= '{start_date}'"
        if end_date is not None:
            sql += f" AND date <= '{end_date}'"
        sql += " ORDER BY date, code"

        try:
            arrow_tbl = self.con.execute(sql).arrow()
            df = pl.from_arrow(arrow_tbl)
            if "code" in df.columns:
                df = df.with_columns(
                    pl.col("code").map_elements(self.denormalize_code, return_dtype=pl.Utf8)
                )
            return df
        except Exception as e:
            logger.warning(f"加载龙虎榜失败: {e}")
            return pl.DataFrame()

    def load_hk_holdings(
        self,
        codes: list[Code],
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """加载沪深港通持股（北向资金）"""
        if not codes:
            return pl.DataFrame()
        codes_normalized = [self.normalize_code(c) for c in codes]
        codes_str = ", ".join(f"'{c}'" for c in codes_normalized)

        sql = f"SELECT * FROM stock_hk_hold WHERE code IN ({codes_str})"
        if start_date is not None:
            sql += f" AND date >= '{start_date}'"
        if end_date is not None:
            sql += f" AND date <= '{end_date}'"
        sql += " ORDER BY code, date"

        try:
            arrow_tbl = self.con.execute(sql).arrow()
            df = pl.from_arrow(arrow_tbl)
            return df.with_columns(
                pl.col("code").map_elements(self.denormalize_code, return_dtype=pl.Utf8)
            )
        except Exception as e:
            logger.warning(f"加载北向资金失败: {e}")
            return pl.DataFrame()

    def load_locked_shares(
        self,
        codes: list[Code] | None = None,
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """加载限售解禁数据"""
        sql = "SELECT * FROM stock_locked_shares WHERE 1=1"
        if codes:
            codes_normalized = [self.normalize_code(c) for c in codes]
            codes_str = ", ".join(f"'{c}'" for c in codes_normalized)
            sql += f" AND code IN ({codes_str})"
        if start_date is not None:
            sql += f" AND date >= '{start_date}'"
        if end_date is not None:
            sql += f" AND date <= '{end_date}'"
        sql += " ORDER BY date, code"

        try:
            arrow_tbl = self.con.execute(sql).arrow()
            df = pl.from_arrow(arrow_tbl)
            if "code" in df.columns:
                df = df.with_columns(
                    pl.col("code").map_elements(self.denormalize_code, return_dtype=pl.Utf8)
                )
            return df
        except Exception as e:
            logger.warning(f"加载限售解禁失败: {e}")
            return pl.DataFrame()

    def load_factor_wide(
        self,
        factor_names: list[str] | None = None,
        codes: list[Code] | None = None,
        start_date: DateLike | None = None,
        end_date: DateLike | None = None,
    ) -> pl.DataFrame:
        """加载因子宽表（260因子预计算）

        Args:
            factor_names: 因子名列表，None 则加载全部
            codes: 股票代码列表，None 则加载全部
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            长表格式: date, code, factor_name, factor_value
        """
        # 先获取所有列名
        try:
            cols_result = self.con.execute("SELECT * FROM factors_wide LIMIT 0").arrow()
            all_cols = cols_result.schema.names
        except Exception as e:
            logger.warning(f"获取因子宽表列名失败: {e}")
            return pl.DataFrame()

        # 筛选因子列
        meta_cols = {"date", "code", "year"}
        factor_cols = [c for c in all_cols if c not in meta_cols]
        if factor_names:
            factor_cols = [c for c in factor_cols if c in factor_names]

        if not factor_cols:
            return pl.DataFrame()

        # 构建SQL - 使用UNPIVOT将宽表转长表
        col_list = ", ".join(factor_cols)
        sql = f"SELECT date, code, {col_list} FROM factors_wide WHERE 1=1"
        if codes:
            codes_normalized = [self.normalize_code(c) for c in codes]
            codes_str = ", ".join(f"'{c}'" for c in codes_normalized)
            sql += f" AND code IN ({codes_str})"
        if start_date is not None:
            sql += f" AND date >= '{start_date}'"
        if end_date is not None:
            sql += f" AND date <= '{end_date}'"

        try:
            arrow_tbl = self.con.execute(sql).arrow()
            df = pl.from_arrow(arrow_tbl)
            return df.with_columns(
                pl.col("code").map_elements(self.denormalize_code, return_dtype=pl.Utf8)
            )
        except Exception as e:
            logger.warning(f"加载因子宽表失败: {e}")
            return pl.DataFrame()

    def load_index_constituents(
        self,
        index_code: Code,
        date: DateLike | None = None,
    ) -> list[Code]:
        """加载指数成分股（支持时点查询）

        Args:
            index_code: 指数代码
            date: 查询日期，None 则取最新

        Returns:
            成分股代码列表
        """
        code_normalized = self.normalize_code(index_code)
        sql = f"SELECT code FROM index_constituents WHERE index_code = '{code_normalized}'"
        if date is not None:
            sql += f" AND date <= '{date}'"
        sql += " ORDER BY date DESC LIMIT 10000"

        try:
            arrow_tbl = self.con.execute(sql).arrow()
            df = pl.from_arrow(arrow_tbl)
            # 取最新截面的成分股
            codes = df["code"].unique().to_list()
            return [self.denormalize_code(c) for c in codes]
        except Exception as e:
            logger.warning(f"加载指数成分股失败: {e}")
            return []

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_asset_type(code: str) -> str:
        """检测资产类型（stock/etf/index）"""
        if "." not in code:
            return "stock"
        prefix = code.split(".")[0]
        # ETF代码: 51/15/16/52/56/59 开头
        if prefix[:2] in ("51", "15", "16", "52", "56", "59"):
            return "etf"
        return "stock"

    def close(self):
        """关闭连接"""
        if self._con is not None:
            self._con.close()
            self._con = None


__all__ = ["DuckDBSource"]
