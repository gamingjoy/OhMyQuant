# 插件热插拔指南

## 核心原则

**零配置热插拔**：新增插件只需两步——把 `.py` 文件放进对应包 + 用 `@register_*` 装饰器标注。无需修改任何 `__init__.py`，重启即生效。

## 机制说明

1. `import ohmyquant` 触发 `PluginRegistry.discover_builtin()`
2. `discover_builtin()` 逐个导入 12 个内置插件包
3. 各包 `__init__.py` 调用 `discover_modules(__name__)`，用 `pkgutil.walk_packages` 扫描所有子模块
4. 导入子模块时触发 `@register_*` 装饰器，将类注册到 `PluginRegistry._registries`

详见 [discovery.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/core/discovery.py) 和 [plugin_system.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/core/plugin_system.py)。

## 新增插件示例

### 新增因子

在 [factors/builtin/](file:///d:/Work/Project/OhMyQuant/ohmyquant/factors/builtin/) 下新建 `my_factor.py`：

```python
"""自定义因子"""
from __future__ import annotations
import polars as pl
from ..base import Factor, register_factor


@register_factor("my_alpha", category="custom")
class MyAlpha(Factor):
    """我的自定义因子"""

    name = "my_alpha"
    category = "custom"
    description = "自定义 alpha 因子"
    direction = 1          # 1=正向, -1=反向
    required_fields = ["close", "volume"]

    def compute(self, data: dict[str, pl.DataFrame]) -> pl.DataFrame:
        close = data["close"]
        volume = data["volume"]
        # 返回 date × code 的因子值宽表
        date_col = close["date"]
        result = close.drop("date") * volume.drop("date")
        return result.insert_column(0, date_col)
```

### 新增选股器

在 [engine/selectors/](file:///d:/Work/Project/OhMyQuant/ohmyquant/engine/selectors/) 下新建 `my_selector.py`：

```python
"""自定义选股器"""
from __future__ import annotations
import polars as pl
from ..selector import BaseSelector
from ...core.plugin_system import register_selector


@register_selector("my_selector")
class MySelector(BaseSelector):
    """自定义选股器"""

    def select(self, factors, ic_df, stock_codes, current_idx, close, **kwargs):
        # 选股逻辑 → 返回 {code: weight}
        return {code: 1.0 / len(stock_codes) for code in stock_codes[:self.top_n]}

    def select_strong_factors(self, ic_df, train_end):
        return list(ic_df.columns[1:])
```

### 新增策略

在 [strategy/strategies/](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/strategies/) 下新建目录 `mytype/v1/`：

```
strategy/strategies/mytype/
└── v1/
    ├── __init__.py    (空文件)
    ├── config.yaml
    └── strategy.py
```

`strategy.py`：
```python
"""自定义策略 v1"""
from ohmyquant.strategy.base import BaseStrategy
from ohmyquant.strategy import register_strategy
from ohmyquant.engine.base import BacktestResult


@register_strategy("mytype", "v1")
class MytypeStrategyV1(BaseStrategy):

    def run(self) -> BacktestResult:
        from ...strategy.runner import StrategyRunner
        runner = StrategyRunner(self.config)
        result = runner.run()
        return result.backtest_result

    def get_latest_positions(self) -> dict[str, float]:
        return {}

    @classmethod
    def from_version(cls, strategy_type, version, config=None):
        base_config = {
            "strategy_type": "mytype",
            "strategy_version": "v1",
            "backtest": {"start_date": "2015-01-01", "end_date": "2024-12-31"},
            "factors": ["mom_1m"],
            "data": {"source": "duckdb", "data_root": "D:/Work/Project/download_a_share/data"},
        }
        if config:
            base_config.update(config)
        return cls(base_config)
```

### 新增成本模型 / 调仓器 / 调度器

这三个插件类型注册在单模块文件中（非包目录）。在对应文件中直接添加类即可：

- 成本模型 → [execution/cost_model.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/execution/cost_model.py)
- 调仓器 → [execution/rebalancer.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/execution/rebalancer.py)
- 调度器 → [execution/scheduler.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/execution/scheduler.py)

```python
@register_cost_model("my_cost")
class MyCostModel(BaseCostModel):
    def buy_cost(self, weight, code=None):
        return weight * 0.001
    def sell_cost(self, weight, hold_days=0, code=None):
        return weight * 0.001
```

## 验证

```bash
# 列出所有已注册插件
python -c "import ohmyquant; from ohmyquant.core.plugin_system import PluginRegistry; print(PluginRegistry.list_all())"

# 按类型列出
python -c "import ohmyquant; from ohmyquant.core.plugin_system import PluginRegistry, PluginType; print(PluginRegistry.list_plugins(PluginType.FACTOR))"
```

## 外部插件（可选）

通过 `pyproject.toml` 的 entry_points 注册外部包：

```toml
[project.entry-points."ohmyquant.plugins"]
my_plugin = "my_package.plugins"
```

调用 `PluginRegistry.discover()` 加载外部插件。
