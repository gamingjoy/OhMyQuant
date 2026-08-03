# 贡献指南

本指南描述如何在 OhMyQuant 框架中新增策略、因子、执行器等组件。

## 目录结构概览

```
ohmyquant/
├── core/           # 核心基础设施(config/plugin/logging/types/exceptions)
├── data/           # 数据层(sources/storage/downloaders)
├── engine/         # 回测引擎(backtest/selector/allocator/risk)
├── execution/      # 执行层(cost_model/rebalancer/scheduler/executor/ths_utils)
├── factors/        # 因子库(builtin)
├── analysis/       # 绩效分析
├── optimization/   # 参数优化(optuna)
├── visualization/  # 可视化
├── strategy/       # 策略层(base/registry/runner/version_manager)
│   └── strategies/ # 策略实现
├── config/         # 默认配置
└── cli/            # 命令行工具

scripts/            # 可执行脚本(按策略分子目录)
├── common/         # 通用工具
├── industry_rotation/
└── expertforest_v1/

docs/               # 文档
├── framework/      # 框架文档
└── strategies/     # 策略报告

tests/              # 测试
```

## 新增策略

### 1. 创建策略类

在 `ohmyquant/strategy/strategies/{strategy_name}/v{version}/` 下创建:

```
ohmyquant/strategy/strategies/your_strategy/
├── __init__.py          # 必须存在(空文件即可)
└── v1/
    ├── __init__.py      # 必须存在
    ├── strategy.py      # 策略实现
    └── config.yaml      # 策略配置
```

**strategy.py** 必须继承 `BaseStrategy` 并实现 `from_version` 工厂方法:

```python
from __future__ import annotations

from ohmyquant.strategy.base import BaseStrategy
from ohmyquant.strategy import register_strategy

@register_strategy("your_strategy", "v1")
class YourStrategyV1(BaseStrategy):
    """策略描述"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "YourStrategyV1":
        """工厂方法: 校验 + 加载 config.yaml + 深度合并运行时覆盖"""
        if strategy_type != "your_strategy" or version != "v1":
            raise ValueError(f"不支持: {strategy_type} {version}")

        # BaseStrategy._load_config_yaml 自动加载同目录 config.yaml 并深度合并
        base_config = cls._load_config_yaml(config)
        return cls(base_config)
```

> `run()` 和 `get_latest_positions()` 有默认实现（通过 `StrategyRunner` 运行回测），如需自定义回测流程再重写。

**config.yaml** 参考现有策略格式。

### 2. 创建脚本

在 `scripts/your_strategy/` 下创建核心脚本:

| 脚本 | 用途 | 必需 |
|------|------|------|
| `your_strategy_daily.py` | T日早晨调仓检查+THS生成 | ✓ |
| `your_strategy_is.py` | IS回测 | ✓ |
| `your_strategy_oos.py` | OOS回测 | ✓ |
| `your_strategy_nav_analysis.py` | 净值分析 | 推荐 |

**sys.path 设置**(子目录化后需用 `parents[2]`):
```python
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # scripts/xxx/ -> 项目根
```

**THS 工具复用**(从框架层引用,不要跨策略 import):
```python
from ohmyquant.execution.ths_utils import (
    generate_trades, get_open_prices, replay_history, write_xlsx,
    CAPITAL, TRANSACTION_COST_RATE,
)
from ohmyquant.strategy.runner import run_oos_backtest
```

### 3. 更新文档

- 在 `docs/strategies/` 创建策略报告 `your_strategy_strategy_report.md`
- 在 `scripts/README.md` 登记新脚本
- 一次性探索脚本完成后移动到 `archive/scripts/your_strategy/`

## 新增因子

1. 在 `ohmyquant/factors/builtin/` 下创建因子模块
2. 实现 `compute` 方法,返回 polars DataFrame
3. 在 `factors/__init__.py` 注册因子
4. 在策略 `config.yaml` 的 `factors` 段引用

## 新增执行器

1. 在 `ohmyquant/execution/` 下创建模块
2. 继承 `BaseCostModel` / `BaseRebalancer` / `BaseScheduler` / `BaseExecutor`
3. 通过 `create_*` 工厂方法注册
4. 在 `config.yaml` 的 `execution` 段引用

## 测试规范

- 新增框架层函数必须有单元测试
- 测试文件放 `tests/`,命名 `test_{module}.py`
- THS 工具测试参考 `tests/test_ths_utils.py`
- 用 `pytest tests/` 运行全部测试

## Git 提交规范

```
<type>(<scope>): <subject>

<body>
```

- type: feat/fix/refactor/docs/chore/test
- scope: strategy/execution/engine/data/scripts/docs
- subject: 简洁描述

示例:
```
feat(strategy): 新增 momentum_v1 策略
fix(execution): 修复 ths_utils 建仓现金计算
refactor(scripts): 子目录分组 common/industry_rotation/expertforest_v1
docs(strategies): 新增 industry_rotation v66 策略报告
```

## 框架层引用原则

- ✅ 脚本 → `ohmyquant.execution.ths_utils` (框架层)
- ✅ 脚本 → `ohmyquant.strategy.runner.run_oos_backtest` (框架层)
- ✅ 策略 → `ohmyquant.engine.*` (引擎层)
- ❌ 脚本A → 脚本B (跨脚本 import,破坏分层)
- ❌ 框架层 → 策略层 (反向依赖)
