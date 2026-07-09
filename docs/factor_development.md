# 因子开发指南

## Factor ABC 契约

所有因子继承 [Factor](file:///d:/Work/Project/OhMyQuant/ohmyquant/factors/base.py) 抽象基类，实现 `compute()` 方法。

### 类属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `name` | str | 因子注册名（与 `@register_factor` 一致） |
| `category` | str | 因子类别（momentum/reversal/volatility/fundamental 等） |
| `description` | str | 因子描述 |
| `direction` | int | 1=正向（值大→预期收益高），-1=反向 |
| `required_fields` | list[str] | 依赖的数据字段（如 `["close"]`、`["close", "volume"]`） |

### compute() 方法

```python
def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """计算因子值

    Args:
        data: 数据字典 {"close": wide_df, "volume": wide_df, ...}
              wide_df 格式: date 列 + code 列（宽表）

    Returns:
        date × code 的因子值矩阵（与输入相同的宽表格式）
    """
```

**关键约束**：返回的 DataFrame 必须包含 `date` 列 + 各 code 列，与输入宽表格式一致。

## 注册因子

使用 `@register_factor` 装饰器：

```python
from ..base import Factor, register_factor

@register_factor("mom_1m", category="momentum")
class Momentum1M(Factor):
    name = "mom_1m"
    category = "momentum"
    direction = 1
    required_fields = ["close"]

    def compute(self, data):
        close = data["close"]
        date_col = close["date"]
        numeric = close.drop("date")
        shifted = numeric.shift(20)
        result = (numeric / shifted) - 1
        return result.insert_column(0, date_col)
```

文件放入 [factors/builtin/](file:///d:/Work/Project/OhMyQuant/ohmyquant/factors/builtin/) 即自动注册，无需修改 `__init__.py`。

## 完整开发示例

以「成交量加权动量因子」为例：

```python
"""成交量加权动量因子"""
from __future__ import annotations
import polars as pl
from ..base import Factor, register_factor


@register_factor("vol_weighted_mom", category="momentum")
class VolWeightedMomentum(Factor):
    """成交量加权的1月动量因子

    动量信号 × 成交量标准化权重，增强高流动性标的的信号强度。
    """

    name = "vol_weighted_mom"
    category = "momentum"
    description = "成交量加权1月动量"
    direction = 1
    required_fields = ["close", "volume"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        close = data["close"]
        volume = data["volume"]

        date_col = close["date"]
        close_num = close.drop("date")
        vol_num = volume.drop("date")

        # 1月动量
        mom = (close_num / close_num.shift(20)) - 1

        # 成交量20日均值的倒数作为权重（低换手加权）
        vol_ma = vol_num.rolling_mean(window_size=20)
        # 避免除零
        vol_weight = 1.0 / (vol_ma + 1e-8)

        # 标准化权重到 [0, 1]
        vol_weight = vol_weight / vol_weight.max()

        result = mom * vol_weight
        return result.insert_column(0, date_col)
```

## 因子分析

用 [FactorAnalyzer](file:///d:/Work/Project/OhMyQuant/ohmyquant/factors/analysis.py) 评估因子效果：

```python
import polars as pl
from ohmyquant.factors import FactorAnalyzer, compute_factor

# 1. 计算因子值
data = {"close": close_wide_df}  # date × code 宽表
factor_values = compute_factor("mom_1m", data)

# 2. 计算前向收益（如 20 日前向收益）
forward_returns = (close_wide_df.drop("date").shift(-20) / close_wide_df.drop("date") - 1)
forward_returns = forward_returns.insert_column(0, close_wide_df["date"])

# 3. IC 分析
analyzer = FactorAnalyzer()
ic_series = analyzer.compute_ic(factor_values, forward_returns, method="spearman")

# 4. ICIR 统计
stats = analyzer.compute_icir(ic_series)
print(f"IC均值: {stats.ic_mean:.4f}")
print(f"ICIR: {stats.icir:.4f}")
print(f"IC正比例: {stats.ic_positive_ratio:.2%}")

# 5. 分位数收益分析
quantile = analyzer.compute_quantile_returns(factor_values, forward_returns, n_groups=5)
print(f"多空收益: {quantile.long_short_return:.2%}")
```

### ICIR 评判标准

| ICIR | 评级 |
|------|------|
| > 1.0 | 优秀 |
| 0.5 - 1.0 | 良好 |
| 0.3 - 0.5 | 一般 |
| < 0.3 | 较弱 |

## 因子优化

用 [FactorOptimizer](file:///d:/Work/Project/OhMyQuant/ohmyquant/factors/optimizer.py) 筛选强因子组合：

```python
from ohmyquant.factors import FactorOptimizer

optimizer = FactorOptimizer()
strong_factors = optimizer.select_strong_factors(
    ic_df=ic_dataframe,
    train_end="2023-12-31",
    min_ic=0.02,
    min_icir=0.1,
)
# strong_factors = ["mom_3m", "rev_20d", "vol_60d"]
```

## 当前内置因子（31 个）

| 类别 | 因子 |
|------|------|
| momentum | mom_1m, mom_3m, mom_6m, mom_12m, mom_skip_1m |
| reversal | rev_5d, rev_20d |
| volatility | vol_20d, vol_60d |
| technical | rsi_14, bias_20 |
| fundamental | ep, bp, sp, turnover, log_market_cap, dividend_yield |

运行 `python -c "import ohmyquant; from ohmyquant.core.plugin_system import PluginRegistry, PluginType; print(PluginRegistry.list_plugins(PluginType.FACTOR))"` 查看完整列表。
