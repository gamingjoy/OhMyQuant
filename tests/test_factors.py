"""factors/builtin 因子计算单元测试

测试 7 大类因子的 compute() 方法:
  - momentum: mom_1m, mom_3m, mom_6m, mom_12m, mom_skip_1m
  - reversal: rev_5d, rev_10d, rev_20d
  - volatility: vol_20d, vol_60d, vol_120d, amihud_illiq
  - technical: rsi_14, ma_5_20_cross, bias_20, willr_14
  - valuation: pe_ttm, pb_ratio, ps_ratio, market_cap
  - volume_price: turnover_20d, volume_ratio, amount_20d, price_volume_corr, obv_slope
  - fundamental: ep_ratio, bp_ratio, sp_ratio, turnover_ratio, log_market_cap, dividend_yield
"""
from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from ohmyquant.core.plugin_system import PluginRegistry, PluginType
from ohmyquant.factors.base import Factor, FactorRegistry


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_wide_df(
    dates: list[str], codes: list[str], values: list[list[float]]
) -> pl.DataFrame:
    """构造 date × code 宽表"""
    data = {"date": dates}
    for i, code in enumerate(codes):
        data[code] = [row[i] for row in values]
    return pl.DataFrame(data)


@pytest.fixture
def close_df():
    """3 只股票 × 260 天的收盘价（递增趋势 + 波动）"""
    dates = [f"2020-01-{str(d).zfill(2)}" for d in range(1, 32)] + \
            [f"2020-02-{str(d).zfill(2)}" for d in range(1, 30)] + \
            [f"2020-03-{str(d).zfill(2)}" for d in range(1, 32)] + \
            [f"2020-04-{str(d).zfill(2)}" for d in range(1, 31)] + \
            [f"2020-05-{str(d).zfill(2)}" for d in range(1, 32)] + \
            [f"2020-06-{str(d).zfill(2)}" for d in range(1, 31)] + \
            [f"2020-07-{str(d).zfill(2)}" for d in range(1, 32)] + \
            [f"2020-08-{str(d).zfill(2)}" for d in range(1, 32)] + \
            [f"2020-09-{str(d).zfill(2)}" for d in range(1, 31)]
    codes = ["000001", "000002", "000003"]
    np.random.seed(42)
    values = []
    base = [10.0, 20.0, 30.0]
    for d in range(len(dates)):
        row = [base[i] * (1 + d * 0.001 + np.random.randn() * 0.01) for i in range(3)]
        values.append(row)
    return _make_wide_df(dates, codes, values)


@pytest.fixture
def volume_df():
    """成交量宽表"""
    close = pytest.importorskip("polars")
    dates = [f"2020-01-{str(d).zfill(2)}" for d in range(1, 32)] + \
            [f"2020-02-{str(d).zfill(2)}" for d in range(1, 30)] + \
            [f"2020-03-{str(d).zfill(2)}" for d in range(1, 32)] + \
            [f"2020-04-{str(d).zfill(2)}" for d in range(1, 31)] + \
            [f"2020-05-{str(d).zfill(2)}" for d in range(1, 32)] + \
            [f"2020-06-{str(d).zfill(2)}" for d in range(1, 31)] + \
            [f"2020-07-{str(d).zfill(2)}" for d in range(1, 32)] + \
            [f"2020-08-{str(d).zfill(2)}" for d in range(1, 32)] + \
            [f"2020-09-{str(d).zfill(2)}" for d in range(1, 31)]
    codes = ["000001", "000002", "000003"]
    np.random.seed(123)
    values = [[10000 + np.random.randn() * 1000 for _ in range(3)] for _ in range(len(dates))]
    return _make_wide_df(dates, codes, values)


@pytest.fixture
def money_df():
    """成交额宽表"""
    dates = [f"2020-01-{str(d).zfill(2)}" for d in range(1, 32)] + \
            [f"2020-02-{str(d).zfill(2)}" for d in range(1, 30)] + \
            [f"2020-03-{str(d).zfill(2)}" for d in range(1, 32)] + \
            [f"2020-04-{str(d).zfill(2)}" for d in range(1, 31)] + \
            [f"2020-05-{str(d).zfill(2)}" for d in range(1, 32)] + \
            [f"2020-06-{str(d).zfill(2)}" for d in range(1, 31)] + \
            [f"2020-07-{str(d).zfill(2)}" for d in range(1, 32)] + \
            [f"2020-08-{str(d).zfill(2)}" for d in range(1, 32)] + \
            [f"2020-09-{str(d).zfill(2)}" for d in range(1, 31)]
    codes = ["000001", "000002", "000003"]
    np.random.seed(456)
    values = [[100000 + np.random.randn() * 10000 for _ in range(3)] for _ in range(len(dates))]
    return _make_wide_df(dates, codes, values)


@pytest.fixture(autouse=True)
def _discover_factors():
    """自动发现并注册所有内置因子"""
    PluginRegistry.discover_builtin()


def _compute_factor(name: str, data: dict) -> pl.DataFrame:
    """便捷函数: 创建因子实例并计算"""
    factor = FactorRegistry.create(name)
    return factor.compute(data)


# ── Momentum Factors ──────────────────────────────────────────────────────────

class TestMomentumFactors:
    """动量因子测试"""

    def test_mom_1m(self, close_df):
        result = _compute_factor("mom_1m", {"close": close_df})
        assert "date" in result.columns
        # 前 20 行为 NaN（shift(20)）
        assert result["000001"][20] is not None

    def test_mom_3m(self, close_df):
        result = _compute_factor("mom_3m", {"close": close_df})
        assert result.shape[0] == close_df.shape[0]

    def test_mom_12m(self, close_df):
        result = _compute_factor("mom_12m", {"close": close_df})
        assert result.shape[0] == close_df.shape[0]

    def test_mom_skip_1m(self, close_df):
        result = _compute_factor("mom_skip_1m", {"close": close_df})
        assert result.shape[0] == close_df.shape[0]

    def test_momentum_direction(self):
        """动量因子方向为正向"""
        for name in ["mom_1m", "mom_3m", "mom_6m", "mom_12m", "mom_skip_1m"]:
            factor = FactorRegistry.create(name)
            assert factor.direction == 1, f"{name} direction should be 1"


# ── Reversal Factors ──────────────────────────────────────────────────────────

class TestReversalFactors:
    """反转因子测试"""

    def test_rev_5d(self, close_df):
        result = _compute_factor("rev_5d", {"close": close_df})
        assert result.shape[0] == close_df.shape[0]

    def test_rev_20d(self, close_df):
        result = _compute_factor("rev_20d", {"close": close_df})
        assert result.shape[0] == close_df.shape[0]

    def test_reversal_direction(self):
        """反转因子方向为反向"""
        for name in ["rev_5d", "rev_10d", "rev_20d"]:
            factor = FactorRegistry.create(name)
            assert factor.direction == -1, f"{name} direction should be -1"


# ── Volatility Factors ────────────────────────────────────────────────────────

class TestVolatilityFactors:
    """波动率因子测试"""

    def test_vol_20d(self, close_df):
        result = _compute_factor("vol_20d", {"close": close_df})
        assert result.shape[0] == close_df.shape[0]

    def test_vol_120d(self, close_df):
        result = _compute_factor("vol_120d", {"close": close_df})
        assert result.shape[0] == close_df.shape[0]

    def test_amihud_illiq(self, close_df, money_df):
        result = _compute_factor("amihud_illiq", {"close": close_df, "money": money_df})
        assert result.shape[0] == close_df.shape[0]

    def test_volatility_direction(self):
        """波动率因子方向为反向"""
        for name in ["vol_20d", "vol_60d", "vol_120d", "amihud_illiq"]:
            factor = FactorRegistry.create(name)
            assert factor.direction == -1, f"{name} direction should be -1"


# ── Technical Factors ─────────────────────────────────────────────────────────

class TestTechnicalFactors:
    """技术因子测试"""

    def test_rsi_14(self, close_df):
        result = _compute_factor("rsi_14", {"close": close_df})
        assert result.shape[0] == close_df.shape[0]
        # RSI 应在 0-100 之间（非 NaN 行）
        rsi_vals = result["000001"].drop_nulls()
        assert rsi_vals.min() >= 0
        assert rsi_vals.max() <= 100

    def test_ma_5_20_cross(self, close_df):
        result = _compute_factor("ma_5_20_cross", {"close": close_df})
        assert result.shape[0] == close_df.shape[0]
        # 交叉信号应为 0.0 或 1.0
        vals = result.drop("date").to_numpy().flatten()
        vals = vals[~np.isnan(vals)]
        assert set(np.unique(vals)).issubset({0.0, 1.0})

    def test_bias_20(self, close_df):
        result = _compute_factor("bias_20", {"close": close_df})
        assert result.shape[0] == close_df.shape[0]

    def test_willr_14(self, close_df):
        """威廉指标需要 high/low/close"""
        high_df = close_df.with_columns([
            (pl.col(c) * 1.02).alias(c) for c in close_df.columns if c != "date"
        ])
        low_df = close_df.with_columns([
            (pl.col(c) * 0.98).alias(c) for c in close_df.columns if c != "date"
        ])
        result = _compute_factor("willr_14", {"close": close_df, "high": high_df, "low": low_df})
        assert result.shape[0] == close_df.shape[0]


# ── Volume Price Factors ──────────────────────────────────────────────────────

class TestVolumePriceFactors:
    """量价因子测试"""

    def test_turnover_20d(self, volume_df):
        result = _compute_factor("turnover_20d", {"volume": volume_df})
        assert result.shape[0] == volume_df.shape[0]

    def test_volume_ratio(self, volume_df):
        result = _compute_factor("volume_ratio", {"volume": volume_df})
        assert result.shape[0] == volume_df.shape[0]

    def test_amount_20d(self, money_df):
        result = _compute_factor("amount_20d", {"money": money_df})
        assert result.shape[0] == money_df.shape[0]

    def test_price_volume_corr(self, close_df, volume_df):
        result = _compute_factor("price_volume_corr", {"close": close_df, "volume": volume_df})
        assert result.shape[0] == close_df.shape[0]

    def test_obv_slope(self, close_df, volume_df):
        result = _compute_factor("obv_slope", {"close": close_df, "volume": volume_df})
        assert result.shape[0] == close_df.shape[0]


# ── Valuation Factors ─────────────────────────────────────────────────────────

class TestValuationFactors:
    """估值因子测试"""

    def test_pe_ttm(self):
        """PE 因子从长表 valuation 数据中提取"""
        val_df = pl.DataFrame({
            "date": ["2020-01-01", "2020-01-01", "2020-01-02", "2020-01-02"],
            "code": ["000001", "000002", "000001", "000002"],
            "pe_ratio": [10.0, 20.0, 11.0, 21.0],
        })
        result = _compute_factor("pe_ttm", {"valuation": val_df})
        assert "000001" in result.columns
        assert "000002" in result.columns

    def test_pb_ratio(self):
        val_df = pl.DataFrame({
            "date": ["2020-01-01", "2020-01-01"],
            "code": ["000001", "000002"],
            "pb_ratio": [1.0, 2.0],
        })
        result = _compute_factor("pb_ratio", {"valuation": val_df})
        assert result["000001"][0] == 1.0
        assert result["000002"][0] == 2.0

    def test_market_cap_log_transform(self):
        """market_cap 因子取对数"""
        cap_df = pl.DataFrame({
            "date": ["2020-01-01"],
            "000001": [1e10],
            "000002": [1e8],
        })
        result = _compute_factor("market_cap", {"market_cap": cap_df})
        # log(1e10) ≈ 23.03, log(1e8) ≈ 18.42
        assert abs(result["000001"][0] - 23.03) < 0.1
        assert abs(result["000002"][0] - 18.42) < 0.1

    def test_valuation_missing_data(self):
        """缺少 valuation 数据时返回空 DataFrame"""
        result = _compute_factor("pe_ttm", {})
        assert result.shape[0] == 0


# ── Fundamental Factors ───────────────────────────────────────────────────────

class TestFundamentalFactors:
    """基本面因子测试"""

    def test_ep_ratio(self):
        """E/P = 1/PE"""
        pe_df = pl.DataFrame({
            "date": ["2020-01-01"],
            "000001": [10.0],
            "000002": [20.0],
        })
        result = _compute_factor("ep_ratio", {"pe_ratio": pe_df})
        assert abs(result["000001"][0] - 0.1) < 1e-6
        assert abs(result["000002"][0] - 0.05) < 1e-6

    def test_bp_ratio(self):
        """B/P = 1/PB"""
        pb_df = pl.DataFrame({
            "date": ["2020-01-01"],
            "000001": [2.0],
        })
        result = _compute_factor("bp_ratio", {"pb_ratio": pb_df})
        assert abs(result["000001"][0] - 0.5) < 1e-6

    def test_log_market_cap(self):
        cap_df = pl.DataFrame({
            "date": ["2020-01-01"],
            "000001": [1e10],
        })
        result = _compute_factor("log_market_cap", {"market_cap": cap_df})
        assert abs(result["000001"][0] - 23.03) < 0.1

    def test_dividend_yield(self):
        div_df = pl.DataFrame({
            "date": ["2020-01-01"],
            "000001": [0.05],
        })
        result = _compute_factor("dividend_yield", {"dividend_ratio": div_df})
        assert result["000001"][0] == 0.05

    def test_invert_zero(self):
        """PE 为 0 时 E/P 应返回 None"""
        pe_df = pl.DataFrame({
            "date": ["2020-01-01"],
            "000001": [0.0],
            "000002": [10.0],
        })
        result = _compute_factor("ep_ratio", {"pe_ratio": pe_df})
        assert result["000001"][0] is None
        assert result["000002"][0] is not None


# ── Factor Metadata ───────────────────────────────────────────────────────────

class TestFactorMetadata:
    """因子元数据测试"""

    def test_all_factors_registered(self):
        """所有 31 个因子都已注册"""
        factors = FactorRegistry.list_factors()
        assert len(factors) >= 31, f"Expected >= 31 factors, got {len(factors)}"

    def test_factor_categories(self):
        """7 大类因子都存在"""
        categories = FactorRegistry.list_categories()
        expected = {"momentum", "reversal", "volatility", "technical",
                     "valuation", "volume_price", "fundamental"}
        assert expected.issubset(set(categories)), \
            f"Missing categories: {expected - set(categories)}"

    def test_factor_required_fields(self):
        """因子 required_fields 不为空"""
        for name in FactorRegistry.list_factors():
            factor = FactorRegistry.create(name)
            assert len(factor.required_fields) > 0, f"{name} has no required_fields"

    def test_factor_get_info(self):
        """get_info 返回完整信息"""
        factor = FactorRegistry.create("mom_1m")
        info = factor.get_info()
        assert info["name"] == "mom_1m"
        assert info["category"] == "momentum"
        assert info["direction"] == 1
        assert "close" in info["required_fields"]
        # P2-8: version 属性
        assert "version" in info
        assert "params" in info
        assert "depends_on" in info


# ── P1-4: Factor Parameterization ────────────────────────────────────────────

class TestFactorParams:
    """因子参数化测试"""

    def test_default_window(self, close_df):
        """默认窗口期 20"""
        factor = FactorRegistry.create("mom_1m")
        assert factor.params["window"] == 20
        result = factor.compute({"close": close_df})
        assert result.shape[0] == close_df.shape[0]

    def test_custom_window_via_config(self, close_df):
        """通过 config 覆盖窗口期"""
        factor = FactorRegistry.create("mom_1m", config={"window": 15})
        assert factor.params["window"] == 15
        result = factor.compute({"close": close_df})
        assert result.shape[0] == close_df.shape[0]

    def test_params_not_shared_between_instances(self):
        """params 深拷贝，实例间不共享"""
        f1 = FactorRegistry.create("mom_1m", config={"window": 10})
        f2 = FactorRegistry.create("mom_1m")
        assert f1.params["window"] == 10
        assert f2.params["window"] == 20

    def test_mom_skip_1m_params(self, close_df):
        """mom_skip_1m 的 skip/lookback 参数可配置"""
        factor = FactorRegistry.create("mom_skip_1m", config={"skip": 10, "lookback": 120})
        assert factor.params["skip"] == 10
        assert factor.params["lookback"] == 120

    def test_get_param_method(self):
        """get_param 方法"""
        factor = FactorRegistry.create("vol_20d")
        assert factor.get_param("window") == 20
        assert factor.get_param("nonexistent", "default") == "default"


# ── P1-5: Factor Cache ────────────────────────────────────────────────────────

class TestFactorCache:
    """因子缓存测试"""

    def test_cache_hit(self, close_df):
        """相同数据第二次计算命中缓存"""
        from ohmyquant.factors.library import FactorLibrary

        lib = FactorLibrary(config={"use_cache": True, "cache_size": 8})
        # 第一次计算（未命中）
        r1 = lib.compute_factor("mom_1m", {"close": close_df})
        # 第二次计算（应命中缓存）
        r2 = lib.compute_factor("mom_1m", {"close": close_df})
        assert r1.shape == r2.shape

    def test_cache_miss_on_different_data(self, close_df):
        """不同数据不命中缓存"""
        from ohmyquant.factors.library import FactorLibrary

        lib = FactorLibrary(config={"use_cache": True})
        r1 = lib.compute_factor("mom_1m", {"close": close_df})

        # 修改数据：反转价格序列（会产生不同的 pct_change）
        close2 = close_df.select(
            ["date"] + [pl.col(c).reverse() for c in close_df.columns if c != "date"]
        )
        r2 = lib.compute_factor("mom_1m", {"close": close2})
        assert not r1.equals(r2)

    def test_cache_disabled(self, close_df):
        """禁用缓存时每次重新计算"""
        from ohmyquant.factors.library import FactorLibrary

        lib = FactorLibrary(config={"use_cache": False})
        r1 = lib.compute_factor("mom_1m", {"close": close_df})
        r2 = lib.compute_factor("mom_1m", {"close": close_df})
        assert r1.equals(r2)  # 结果相同但无缓存

    def test_clear_cache(self, close_df):
        """清空缓存"""
        from ohmyquant.factors.library import FactorLibrary

        lib = FactorLibrary(config={"use_cache": True})
        lib.compute_factor("mom_1m", {"close": close_df})
        lib.clear_cache()
        # 清空后应重新计算
        r = lib.compute_factor("mom_1m", {"close": close_df})
        assert r.shape[0] == close_df.shape[0]


# ── P0-1: Decorator Dedup ────────────────────────────────────────────────────

class TestDecoratorDedup:
    """装饰器去重测试"""

    def test_register_factor_no_args(self):
        """@register_factor() 无参数时从类属性读取 name"""
        from ohmyquant.factors.base import Factor, register_factor

        @register_factor()
        class _TestFactor(Factor):
            name = "_test_factor_dedup"
            category = "test"
            description = "test"
            direction = 1
            required_fields = ["close"]

            def compute(self, data):
                return data["close"]

        factor = FactorRegistry.create("_test_factor_dedup")
        assert factor.name == "_test_factor_dedup"
        assert factor.category == "test"

    def test_register_factor_override_name(self):
        """@register_factor("custom") 覆盖类属性 name"""
        from ohmyquant.factors.base import Factor, register_factor

        @register_factor("_test_override_name")
        class _TestFactor2(Factor):
            name = "_test_original"
            category = "test"
            direction = 1
            required_fields = ["close"]

            def compute(self, data):
                return data["close"]

        factor = FactorRegistry.create("_test_override_name")
        assert factor.name == "_test_original"  # 类属性不变
        # 但注册名是 _test_override_name
        assert "_test_override_name" in FactorRegistry.list_factors()


# ── P0-2: Vectorized IC ──────────────────────────────────────────────────────

class TestVectorizedIC:
    """向量化 IC 计算测试"""

    def test_compute_ic_returns_dataframe(self):
        """compute_ic 返回正确格式"""
        from ohmyquant.factors.analysis import FactorAnalyzer

        dates = [f"2020-01-{str(d).zfill(2)}" for d in range(1, 21)]
        codes = [f"00000{i}" for i in range(1, 6)]
        np.random.seed(42)
        fv = _make_wide_df(dates, codes, np.random.randn(20, 5).tolist())
        fr = _make_wide_df(dates, codes, np.random.randn(20, 5).tolist())

        ic_df = FactorAnalyzer.compute_ic(fv, fr)
        assert "date" in ic_df.columns
        assert "ic" in ic_df.columns
        assert ic_df.shape[0] == 20

    def test_compute_ic_perfect_correlation(self):
        """完全正相关时 IC ≈ 1"""
        from ohmyquant.factors.analysis import FactorAnalyzer

        dates = [f"2020-01-{str(d).zfill(2)}" for d in range(1, 21)]
        codes = [f"00000{i}" for i in range(1, 11)]
        values = np.arange(1, 11).tolist()
        fv = _make_wide_df(dates, codes, [values] * 20)
        fr = _make_wide_df(dates, codes, [values] * 20)

        ic_df = FactorAnalyzer.compute_ic(fv, fr, method="pearson")
        ic_valid = ic_df["ic"].drop_nulls()
        assert ic_valid.len() > 0
        assert abs(ic_valid[0] - 1.0) < 1e-6

    def test_compute_quantile_returns(self):
        """分位数收益计算"""
        from ohmyquant.factors.analysis import FactorAnalyzer

        dates = [f"2020-01-{str(d).zfill(2)}" for d in range(1, 21)]
        codes = [f"00000{i}" for i in range(1, 26)]
        np.random.seed(42)
        fv = _make_wide_df(dates, codes, np.random.randn(20, 25).tolist())
        fr = _make_wide_df(dates, codes, np.random.randn(20, 25).tolist())

        result = FactorAnalyzer.compute_quantile_returns(fv, fr, n_groups=5)
        assert result.n_groups == 5
        assert len(result.group_returns) > 0


# ── P0-3: scipy Fallback ─────────────────────────────────────────────────────

class TestScipyFallback:
    """scipy fallback 测试"""

    def test_rankdata_numpy(self):
        """numpy rankdata 实现正确"""
        from ohmyquant.factors.analysis import _rankdata

        arr = np.array([3.0, 1.0, 2.0, 1.0])
        ranks = _rankdata(arr)
        # 1.0 出现两次，rank 应为 (1+2)/2 = 1.5
        assert abs(ranks[1] - 1.5) < 1e-6
        assert abs(ranks[3] - 1.5) < 1e-6
        assert abs(ranks[2] - 3.0) < 1e-6
        assert abs(ranks[0] - 4.0) < 1e-6

    def test_pearson_corr_numpy(self):
        """numpy Pearson 相关实现正确"""
        from ohmyquant.factors.analysis import _pearson_corr

        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        y = np.array([2.0, 4.0, 6.0, 8.0, 10.0])
        corr = _pearson_corr(x, y)
        assert abs(corr - 1.0) < 1e-6

    def test_spearman_corr(self):
        """Spearman 相关计算"""
        from ohmyquant.factors.analysis import _spearman_corr

        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        y = np.array([5.0, 4.0, 3.0, 2.0, 1.0])
        corr = _spearman_corr(x, y)
        assert abs(corr - (-1.0)) < 1e-6


# ── P2-7: Factor Dependencies ────────────────────────────────────────────────

class TestFactorDependency:
    """因子依赖测试"""

    def test_depends_on_default_empty(self):
        """默认 depends_on 为空"""
        factor = FactorRegistry.create("mom_1m")
        assert factor.depends_on == []

    def test_dependency_resolution(self, close_df):
        """FactorLibrary 自动解析依赖"""
        from ohmyquant.factors.base import Factor, FactorRegistry, register_factor
        from ohmyquant.factors.library import FactorLibrary

        # 注册一个依赖 mom_1m 的测试因子
        @register_factor()
        class _DependentFactor(Factor):
            name = "_test_dependent"
            category = "test"
            direction = 1
            required_fields = ["close"]
            depends_on = ["mom_1m"]

            def compute(self, data):
                # 使用 mom_1m 的结果
                mom = data["mom_1m"]
                date_col = mom["date"]
                numeric = mom.drop("date")
                return (numeric * 2).insert_column(0, date_col)

        lib = FactorLibrary(config={"use_cache": False})
        result = lib.compute_factor("_test_dependent", {"close": close_df})
        # 验证依赖因子被自动计算
        assert result.shape[0] == close_df.shape[0]


# ── P2-8: Factor Version ─────────────────────────────────────────────────────

class TestFactorVersion:
    """因子版本管理测试"""

    def test_default_version(self):
        """默认版本为 v1"""
        factor = FactorRegistry.create("mom_1m")
        assert factor.version == "v1"

    def test_version_in_get_info(self):
        """version 出现在 get_info 中"""
        info = FactorRegistry.get_info("vol_20d")
        assert "version" in info
        assert info["version"] == "v1"

    def test_version_in_plugin_meta(self):
        """version 写入 PluginMeta"""
        from ohmyquant.core.plugin_system import PluginRegistry, PluginType

        meta = PluginRegistry.get_meta(PluginType.FACTOR, "mom_1m")
        assert meta.version == "v1"


# ── P2-9: Factor Report ──────────────────────────────────────────────────────

class TestFactorReport:
    """因子报告生成测试"""

    def test_report_generation(self):
        """生成因子报告"""
        from ohmyquant.factors.report import FactorReportGenerator

        dates = [f"2020-01-{str(d).zfill(2)}" for d in range(1, 31)]
        codes = [f"00000{i}" for i in range(1, 11)]
        np.random.seed(42)
        fv = _make_wide_df(dates, codes, np.random.randn(30, 10).tolist())
        fr = _make_wide_df(dates, codes, np.random.randn(30, 10).tolist())

        gen = FactorReportGenerator()
        report = gen.generate("mom_1m", fv, fr)
        assert "# 因子报告: mom_1m" in report
        assert "## IC / ICIR 分析" in report
        assert "## 分位数组合收益" in report

    def test_report_with_decay(self):
        """带 IC 衰减的报告"""
        from ohmyquant.factors.report import FactorReportGenerator

        dates = [f"2020-01-{str(d).zfill(2)}" for d in range(1, 61)]
        codes = [f"00000{i}" for i in range(1, 11)]
        np.random.seed(42)
        fv = _make_wide_df(dates, codes, np.random.randn(60, 10).tolist())
        close = _make_wide_df(dates, codes, np.cumsum(np.random.randn(60, 10), axis=0).tolist())

        gen = FactorReportGenerator(decay_horizons=[5, 10, 20])
        report = gen.generate("mom_1m", fv, close, close=close)
        assert "## IC 衰减分析" in report

    def test_report_save(self, tmp_path):
        """保存报告到文件"""
        from ohmyquant.factors.report import FactorReportGenerator
        from pathlib import Path

        dates = [f"2020-01-{str(d).zfill(2)}" for d in range(1, 31)]
        codes = [f"00000{i}" for i in range(1, 11)]
        np.random.seed(42)
        fv = _make_wide_df(dates, codes, np.random.randn(30, 10).tolist())
        fr = _make_wide_df(dates, codes, np.random.randn(30, 10).tolist())

        gen = FactorReportGenerator()
        report = gen.generate("mom_1m", fv, fr)
        path = tmp_path / "test_report.md"
        gen.save(report, path)
        assert path.exists()
        assert path.read_text(encoding="utf-8") == report


# ── P1-6: External Factor Loading ────────────────────────────────────────────

class TestExternalFactor:
    """外部因子加载测试"""

    def test_discover_external(self, tmp_path):
        """从外部目录加载因子"""
        # 创建临时因子文件
        factor_code = '''
from ohmyquant.factors.base import Factor, register_factor
import polars as pl

@register_factor()
class _ExternalTestFactor(Factor):
    name = "_external_test_factor"
    category = "test"
    description = "external test"
    direction = 1
    required_fields = ["close"]

    def compute(self, data):
        return data["close"]
'''
        factor_file = tmp_path / "external_factor.py"
        factor_file.write_text(factor_code, encoding="utf-8")

        count = FactorRegistry.discover_external([tmp_path])
        assert count == 1
        assert "_external_test_factor" in FactorRegistry.list_factors()

        factor = FactorRegistry.create("_external_test_factor")
        assert factor.name == "_external_test_factor"
