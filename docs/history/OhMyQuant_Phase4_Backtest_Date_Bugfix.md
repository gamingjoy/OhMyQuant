# Phase 4 收尾：修复回测引擎日期比较 Bug

## 摘要

`BacktestEngine._run_backtest_loop()` 中存在日期类型不一致 Bug：`_get_common_dates()` 返回 `datetime.date` 对象，但下游代码（`_run_backtest_loop`）将日期转为 `str` 后与 `datetime.date` 集合比较，导致调仓永不触发、交易成本永不计算、甚至抛出 `TypeError`。本计划在 `_get_common_dates()` 单点修复，将所有日期统一归一化为 `"YYYY-MM-DD"` 字符串，使全链路类型一致。

## 当前状态分析

### Bug 根因

`DataCatalog.get_ohlcv()` → `pivot_to_wide()` 使用 polars `df.pivot().sort("date")`，date 列 dtype 为 `pl.Date`，因此 `close["date"].to_list()` 返回 Python `datetime.date` 对象。

`BacktestEngine._get_common_dates()`（[backtest.py:456-480](file:///d:/Work/Project/OhMyQuant/ohmyquant/engine/backtest.py#L456-L480)）直接返回这些 `datetime.date` 对象，但下游使用方式不一致：

| 位置 | 变量 | 实际类型 | 期望类型 | 问题 |
|------|------|----------|----------|------|
| `_run_selection` L371 | `date_str` (来自 `all_dates`) | `datetime.date` | `str` | 变量名误导，作为 dict key |
| `_run_selection` L411 | `stock_weights_by_date[date_str]` | key 为 `datetime.date` | key 为 `str` | 与下游不一致 |
| `_run_backtest_loop` L552 | `date_str = str(date)` | `str` | `str` | 显式转换 |
| `_run_backtest_loop` L558 | `stock_rebal_dates_sorted[...] <= date_str` | `datetime.date <= str` | `str <= str` | **TypeError** |
| `_run_backtest_loop` L565 | `date_str in rebalance_dates` | `str in set[date]` | `str in set[str]` | **恒 False，调仓永不触发** |
| `_run_backtest_loop` L619 | `date_str in rebalance_dates` | `str in set[date]` | `str in set[str]` | **恒 False，交易成本永不计算** |

### 次要 Bug：vol 因子 rolling_std

[volatility.py:34](file:///d:/Work/Project/OhMyQuant/ohmyquant/factors/builtin/volatility.py#L34) 使用 `numeric.rolling_std(window_size=20)`，但 polars `DataFrame` 没有 `rolling_std` 方法（只有 `Series` 有）。需改为 `numeric.select(pl.all().rolling_std(window_size=20))`。同样问题影响 `vol_60d`、`vol_120d`、`amihud_illiq`。

## 修复方案

### 修复 1：`_get_common_dates()` 归一化日期为字符串（核心修复）

**文件**: [ohmyquant/engine/backtest.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/engine/backtest.py#L456-L480)

**改动**: 在 `_get_common_dates()` 中将所有 `datetime.date` 对象转为 `"YYYY-MM-DD"` 字符串。

**修改前** (L456-480):
```python
@staticmethod
def _get_common_dates(pool_data):
    date_sets = []
    for ohlcv in pool_data.values():
        close = ohlcv.get("close")
        if close is not None and "date" in close.columns:
            dates = close["date"].to_list()
            date_sets.append(set(dates))
    if not date_sets:
        return []
    common = date_sets[0]
    for ds in date_sets[1:]:
        common &= ds
    first_close = next(iter(pool_data.values())).get("close")
    if first_close is not None:
        all_dates = first_close["date"].to_list()
        return [d for d in all_dates if d in common]
    return sorted(common)
```

**修改后**:
```python
@staticmethod
def _get_common_dates(pool_data):
    def _to_str(d):
        """统一日期为 YYYY-MM-DD 字符串"""
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
    first_close = next(iter(pool_data.values())).get("close")
    if first_close is not None:
        all_dates = [_to_str(d) for d in first_close["date"].to_list()]
        return [d for d in all_dates if d in common]
    return sorted(common)
```

**为什么是单点修复**:
- `all_dates` 全部为 `str` → `get_rebalance_dates(all_dates, ...)` 收到 `str` 列表 → 返回 `set[str]` ✓
- `_run_selection`: `date_str` 变量名与实际类型一致 ✓；`stock_weights_by_date` keys 为 `str` ✓
- `_run_backtest_loop` L552: `str(date)` 是 no-op（已是 str）✓
- L558: `str <= str` ✓（ISO 格式字符串字典序与日期序一致）
- L565: `str in set[str]` ✓
- L619: `str in set[str]` ✓
- L501: `str(d) >= backtest_start` → `str >= str` ✓
- L675: `str(d) for d in all_dates[...]` → no-op ✓
- `_precompute_regimes`: `date_str` 作为 key 和 lookup 一致 ✓

### 修复 2：vol 因子 rolling_std/rolling_mean（次要修复）

**文件**: [ohmyquant/factors/builtin/volatility.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/factors/builtin/volatility.py)

4 处改动，将 `numeric.rolling_std(...)` / `illiq.rolling_mean(...)` 改为表达式 API：

- L34: `result = numeric.rolling_std(window_size=20)` → `result = numeric.select(pl.all().rolling_std(window_size=20))`
- L52: `result = numeric.rolling_std(window_size=60)` → `result = numeric.select(pl.all().rolling_std(window_size=60))`
- L70: `result = numeric.rolling_std(window_size=120)` → `result = numeric.select(pl.all().rolling_std(window_size=120))`
- L97: `result = illiq.rolling_mean(window_size=20)` → `result = illiq.select(pl.all().rolling_mean(window_size=20))`

## 假设与决策

1. **选择在 `_get_common_dates()` 单点修复而非多处修复**：减少改动面，降低引入新 Bug 的风险，且与代码中 `date_str` 命名约定一致。
2. **ISO 格式字符串比较等价于日期比较**：`"2024-06-03" >= "2024-01-01"` 的字典序与日期序一致，无需转回 `date` 对象比较。
3. **vol 因子修复纳入本计划**：虽属 Phase 3，但它是阻塞完整端到端验证的实际障碍，且修复极简（每处一行）。
4. **不修复多池日期对齐问题**：当各池股票上市时间不同时，`close.row(current_idx)` 可能索引错位。这是预存在的架构问题，不在本次范围，留待后续迭代。

## 验证步骤

### 步骤 1：单元验证日期归一化

```python
import polars as pl
from datetime import date
from ohmyquant.engine.backtest import BacktestEngine

# 构造含 datetime.date 的模拟数据
close_a = pl.DataFrame({"date": [date(2024,6,3), date(2024,6,4), date(2024,6,5)], "000001.SZ": [10.0, 10.5, 11.0]})
close_b = pl.DataFrame({"date": [date(2024,6,3), date(2024,6,4), date(2024,6,5)], "600000.SH": [5.0, 5.1, 5.2]})
pool_data = {"a": {"close": close_a}, "b": {"close": close_b}}

dates = BacktestEngine._get_common_dates(pool_data)
assert all(isinstance(d, str) for d in dates), f"期望 str，实际: {set(type(d) for d in dates)}"
assert dates == ["2024-06-03", "2024-06-04", "2024-06-05"], dates
print("✓ 日期归一化验证通过")
```

### 步骤 2：验证 vol 因子修复

```python
import polars as pl
from datetime import date
from ohmyquant.factors.builtin.volatility import Volatility20D

close = pl.DataFrame({
    "date": [date(2024,1,1) + pl.duration(days=i) for i in range(30)],
    "000001.SZ": [10.0 + i*0.1 for i in range(30)],
})
f = Volatility20D()
result = f.compute({"close": close})
assert "000001.SZ" in result.columns
assert len(result) == 30
print("✓ vol_20d 因子验证通过")
```

### 步骤 3：端到端冒烟测试

```python
from ohmyquant.data.sources.duckdb_source import DuckDBSource
from ohmyquant.data.base import DataCatalog
from ohmyquant.core.config_models import StrategyConfig
from ohmyquant.engine.backtest import BacktestEngine

catalog = DataCatalog(DuckDBSource({"data_root": "D:/Work/Project/download_a_share/data"}))
config = StrategyConfig()
config.factors = ["mom_1m", "vol_20d"]  # 同时测试动量和波动率因子
config.backtest.start_date = "2024-06-01"
config.backtest.end_date = "2024-12-31"
config.rebalance.frequency = "monthly"

engine = BacktestEngine(catalog, config)
result = engine.run(
    pools={"test_pool": ["000001.SZ", "600000.SH", "000002.SZ", "600036.SH"]},
    start_date="2024-06-01",
    end_date="2024-12-31",
)
print(f"最终净值: {result.final_nav:.4f}, 天数: {result.n_days}")
assert result.n_days > 0, "回测天数应 > 0"
assert len(result.pool_weight_log) > 0, "应有调仓记录"
assert len(result.exposure_log) > 0, "应有风控日志"
print("✓ 端到端冒烟测试通过")
```

### 步骤 4：验证调仓实际触发

```python
# 确认调仓日志非空（修复前为空，因 date_str in rebalance_dates 恒 False）
assert len(result.pool_weight_log) >= 1, f"调仓日志为空，调仓未触发！"
# 确认交易成本被计算（修复前 cost 恒为 0）
costs = [e["transaction_cost"] for e in result.exposure_log]
assert any(c > 0 for c in costs), "交易成本全为 0，调仓日未正确识别"
print("✓ 调仓触发验证通过")
```

## 实施顺序

1. 修复 [backtest.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/engine/backtest.py) 的 `_get_common_dates()` 方法
2. 修复 [volatility.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/factors/builtin/volatility.py) 的 4 处 rolling 调用
3. 运行验证步骤 1（日期归一化单元验证）
4. 运行验证步骤 2（vol 因子验证）
5. 运行验证步骤 3（端到端冒烟测试）
6. 运行验证步骤 4（调仓触发验证）
7. 标记 Task #17 完成，Phase 4 收尾
