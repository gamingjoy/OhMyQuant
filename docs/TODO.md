# OhMyQuant 代码库优化待办清单

> **生成时间**: 2026-08-03
> **背景**: 基于框架完整性分析,梳理代码库未来优化方向,按优先级排列,供后续迭代参考。
> **执行原则**: 优先做高收益低成本项,避免过度工程化,保持框架简洁。

---

## 目录

- [P0 — 高收益低成本(立即执行)](#p0--高收益低成本立即执行)
- [P1 — 中收益中成本(近期执行)](#p1--中收益中成本近期执行)
- [P2 — 长期收益高成本(计划执行)](#p2--长期收益高成本计划执行)
- [P3 — 可选优化(按需执行)](#p3--可选优化按需执行)
- [执行路线图](#执行路线图)
- [关键决策点](#关键决策点)

---

## P0 — 高收益低成本(立即执行)

### TODO-001: print → logger 统一

| 属性 | 内容 |
|------|------|
| **优先级** | P0 |
| **成本** | 低 (~50 处替换) |
| **收益** | 高 |
| **预估工作量** | 1-2 小时 |

**现状**:
- `ohmyquant/execution/rebalancer.py` 大量使用 `print` 输出调仓信息
- `ohmyquant/engine/backtest.py` 用 `print` 输出回测进度
- `ohmyquant/engine/selectors/industry_rotation_selector.py` 用 `print` 输出选股信息
- `ohmyquant/strategy/runner.py` 的 `run_oos_backtest` 用 `print` 输出回测结果
- 已有 `ohmyquant/core/logging.py` 基础设施,但未广泛使用

**优化方案**:
1. 全局搜索 `print(` 在 `ohmyquant/` 下的所有出现
2. 按语境替换:
   - 调仓/选股信息 → `logger.info()`
   - 警告信息 → `logger.warning()`
   - 错误信息 → `logger.error()`
   - 调试信息 → `logger.debug()`
3. 每个模块顶部添加 `from ohmyquant.core.logging import get_logger; logger = get_logger(__name__)`
4. 保留 `scripts/` 下的 `print`(面向用户的命令行输出)

**优劣分析**:
- **优势**: 统一日志级别控制,可按需关闭/开启;支持日志文件输出;统一格式(时间戳/模块名)
- **劣势**: 需逐个确认 print 语境,有些是用户提示非日志;首次替换可能遗漏

**涉及文件**:
- `ohmyquant/execution/rebalancer.py` (~15 处)
- `ohmyquant/engine/backtest.py` (~10 处)
- `ohmyquant/engine/selectors/industry_rotation_selector.py` (~20 处)
- `ohmyquant/strategy/runner.py` (~5 处)

**验证方式**:
```bash
# 确认 ohmyquant/ 下无 print 残留(除 __main__ 块)
grep -rn "print(" ohmyquant/ --include="*.py" | grep -v "__main__"
```

---

### TODO-002: pyproject.toml 完善

| 属性 | 内容 |
|------|------|
| **优先级** | P0 |
| **成本** | 低 (1 文件) |
| **收益** | 中 |
| **预估工作量** | 30 分钟 |

**现状**:
- 仅有 `setup.py` + `requirements.txt`
- 无 `pyproject.toml`(PEP 621 标准)
- 依赖版本未锁定

**优化方案**:
1. 创建 `pyproject.toml`,包含:
   - `[build-system]`: setuptools 后端
   - `[project]`: name/version/description/dependencies/optional-dependencies
   - `[project.scripts]`: `omq` CLI 入口点
   - `[tool.pytest]`: 测试配置
   - `[tool.mypy]`: 类型检查配置(可选)
2. 迁移 `setup.py` 的元数据到 `pyproject.toml`
3. 保留 `requirements.txt` 作为兼容(或删除)

**优劣分析**:
- **优势**: 现代标准(PEP 621),支持 `pip install -e .`;集中配置;便于发布 PyPI
- **劣势**: 需与 setup.py 共存或完全迁移;短距迁移可能引入兼容问题

**涉及文件**:
- 新建 `pyproject.toml`
- 可能删除 `setup.py`(或保留为兼容)

**配置示例**:
```toml
[build-system]
requires = ["setuptools>=64", "wheel"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "ohmyquant"
version = "0.1.0"
description = "一站式量化策略开发框架"
requires-python = ">=3.10"
dependencies = [
    "polars>=0.20",
    "duckdb>=0.9",
    "pydantic>=2.0",
    "loguru>=0.7",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
viz = ["plotly>=5.0"]
stats = ["scipy>=1.10"]
dev = ["pytest>=7.0", "pytest-cov", "mypy", "ruff"]

[project.scripts]
omq = "ohmyquant.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

---

## P1 — 中收益中成本(近期执行)

### TODO-003: execution 模块单元测试

| 属性 | 内容 |
|------|------|
| **优先级** | P1 |
| **成本** | 中 (~200 行测试代码) |
| **收益** | 高 |
| **预估工作量** | 3-4 小时 |

**现状**:
- `execution/rebalancer.py` 有 3 种调仓器(CostBenefit/Simple/NoOp)无测试
- `execution/scheduler.py` 有 2 种调度器(Calendar/Adaptive)无测试
- `execution/cost_model.py` 已有部分测试(`test_backtest.py`),但不完整
- `execution/executor.py` 的 SimulatedExecutor/LiveExecutor 无测试

**优化方案**:
1. 新增 `tests/test_rebalancer.py`:
   - `TestCostBenefitRebalancer`: 测试成本收益权衡调仓决策
   - `TestSimpleRebalancer`: 测试简单调仓(全量调仓)
   - `TestNoOpRebalancer`: 测试空操作
   - 边界测试: 空持仓/全卖出/零权重
2. 新增 `tests/test_scheduler.py`:
   - `TestCalendarScheduler`: 测试日历频率(周/月/季)
   - `TestAdaptiveScheduler`: 测试自适应频率
   - 边界测试: 非交易日/节假日
3. 补充 `tests/test_executor.py`(可选):
   - `TestSimulatedExecutor`: 模拟执行(成交/滑点/费用)

**优劣分析**:
- **优势**: 调仓/调度是回测核心,bug 影响全局;测试后可放心重构
- **劣势**: 需构造 mock 数据(持仓/权重/价格);调仓逻辑复杂,测试用例多

**涉及文件**:
- 新建 `tests/test_rebalancer.py`
- 新建 `tests/test_scheduler.py`
- 可选: 新建 `tests/test_executor.py`

**验证方式**:
```bash
python -m pytest tests/test_rebalancer.py tests/test_scheduler.py -v
```

---

### TODO-004: CI/CD 配置 (GitHub Actions)

| 属性 | 内容 |
|------|------|
| **优先级** | P1 |
| **成本** | 低 (1 文件) |
| **收益** | 中 |
| **预估工作量** | 1 小时 |

**现状**:
- 无 `.github/workflows/` 目录
- 无自动化测试/格式检查

**优化方案**:
1. 新建 `.github/workflows/test.yml`:
   - 触发: push/PR 到 main 分支
   - 矩阵: Python 3.10/3.11/3.12
   - 步骤: checkout → setup-python → install deps → pytest
2. 可选: 新增 `.github/workflows/lint.yml`:
   - ruff/black 格式检查
   - mypy 类型检查(可选,可能报错多)

**优劣分析**:
- **优势**: 自动化质量保障,PR 必须通过测试才能合并;早期发现兼容问题
- **劣势**: 依赖 github Actions 可用性;首次配置需调试;运行时间增加

**涉及文件**:
- 新建 `.github/workflows/test.yml`
- 可选: 新建 `.github/workflows/lint.yml`

**配置示例**:
```yaml
name: Tests
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install dependencies
        run: pip install -e ".[dev]"
      - name: Run tests
        run: pytest tests/ -v --cov=ohmyquant
```

---

### TODO-005: pre-commit hooks

| 属性 | 内容 |
|------|------|
| **优先级** | P1 |
| **成本** | 低 (1 文件) |
| **收益** | 中 |
| **预估工作量** | 30 分钟 |

**现状**:
- 无 `.pre-commit-config.yaml`
- 代码格式可能不统一

**优化方案**:
1. 新建 `.pre-commit-config.yaml`:
   - `black`: 代码格式化
   - `ruff`: lint 检查(替代 flake8/pylint)
   - `mypy`: 类型检查(可选,可设 `--ignore-missing-imports`)
   - 基础检查: trailing-whitespace, end-of-file-fixer
2. 首次运行 `pre-commit run --all-files` 统一格式

**优劣分析**:
- **优势**: 提交前自动格式化/检查,保证代码质量;与 CI/CD 配合形成双重保障
- **劣势**: 首次运行可能大量修改文件;需团队成员都安装 pre-commit

**涉及文件**:
- 新建 `.pre-commit-config.yaml`

**配置示例**:
```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
  - repo: https://github.com/psf/black
    rev: 24.1.0
    hooks:
      - id: black
  - repo: https://github.com/astral-sh/ruff
    rev: v0.2.0
    hooks:
      - id: ruff
        args: [--fix]
```

---

### TODO-006: engine/selectors 测试

| 属性 | 内容 |
|------|------|
| **优先级** | P1 |
| **成本** | 中 (~150 行测试代码) |
| **收益** | 中 |
| **预估工作量** | 2-3 小时 |

**现状**:
- `IndustryRotationSelector` 是唯一的选股器,无测试
- 选股逻辑复杂(因子评分 + 风控过滤 + 大盘趋势),bug 直接影响收益

**优化方案**:
1. 新增 `tests/test_selector.py`:
   - `TestIndustryRotationSelector`:
     - 测试因子评分排序
     - 测试大盘趋势过滤(bull/bear/sideways)
     - 测试风控规则(ST 过滤/涨跌停/最大权重)
     - 测试 Top-N 选股数量
   - 边界测试: 空候选池/全被过滤/单只股票

**优劣分析**:
- **优势**: 选股直接影响收益,测试保障正确性;便于后续重构
- **劣势**: 选股器依赖大量数据(行情/估值/因子),需完整 mock

**涉及文件**:
- 新建 `tests/test_selector.py`

---

## P2 — 长期收益高成本(计划执行)

### TODO-007: 类型注解完善

| 属性 | 内容 |
|------|------|
| **优先级** | P2 |
| **成本** | 高 (~300 处) |
| **收益** | 中 |
| **预估工作量** | 1-2 天 |

**现状**:
- `ohmyquant/engine/backtest.py` 大量函数缺返回值类型
- 大量使用 `dict` / `Any` 而非具体类型
- 部分函数参数无类型注解

**优化方案**:
1. 用 `mypy --strict` 检查全项目,输出错误列表
2. 按模块逐步补充:
   - `core/` → `data/` → `engine/` → `execution/` → `strategy/`
3. 定义具体类型别名(已有 `core/types.py` 的 `Code`/`WeightMap`)
4. 用 `TypedDict` 替代 `dict` 类型

**优劣分析**:
- **优势**: 提升可维护性,IDE 智能提示;早期发现类型错误
- **劣势**: 工作量大(~300 处);短期无直接功能收益;可能引入过度抽象

**涉及文件**:
- `ohmyquant/` 下所有 `.py` 文件

**验证方式**:
```bash
mypy ohmyquant/ --ignore-missing-imports
```

---

### TODO-008: API 文档 (Sphinx)

| 属性 | 内容 |
|------|------|
| **优先级** | P2 |
| **成本** | 高 (配置 + 调试) |
| **收益** | 中 |
| **预估工作量** | 1 天 |

**现状**:
- 无 API 文档,只有手写 `.md` 文档
- docstring 覆盖率中等(core/engine/strategy 较高,rebalancer/scheduler 较低)

**优化方案**:
1. 安装 sphinx + sphinx-autodoc-typehints + furo 主题
2. 新建 `docs/api/` 目录,配置 `conf.py`
3. 自动生成 API 文档:
   - `docs/api/modules.rst` → 模块索引
   - `docs/api/ohmyquant.core.rst` → core 模块
   - ...
4. 可选: 部署到 github pages / readthedocs

**优劣分析**:
- **优势**: 自动化文档,适合开源项目;降低新用户学习成本
- **劣势**: 维护成本(docstring 必须规范);小项目收益有限;构建配置复杂

**涉及文件**:
- 新建 `docs/api/conf.py`
- 新建 `docs/api/*.rst`

---

### TODO-009: 回测引擎性能优化

| 属性 | 内容 |
|------|------|
| **优先级** | P2 |
| **成本** | 高 (需分析 + 重构) |
| **收益** | 高 |
| **预估工作量** | 1-2 天 |

**现状**:
- `ohmyquant/engine/backtest.py` 日期循环为线性遍历
- 未确认是否有性能瓶颈
- 因子计算可能重复(同一因子被多次计算)

**优化方案**:
1. 用 `cProfile` 分析回测热点:
   ```bash
   python -m cProfile -o profile.out scripts/industry_rotation/industry_rotation_is.py
   python -m pstats profile.out
   ```
2. 识别 Top-10 热点函数
3. 针对性优化:
   - 因子计算缓存(同一因子不重复计算)
   - 数据加载缓存(DataCatalog 已有 LRU,确认是否生效)
   - 向量化(避免逐行循环,用 polars expr)
   - 并行化(多股票池并行)

**优劣分析**:
- **优势**: 回测速度提升显著(可能 2-5x);影响开发效率
- **劣势**: 需先分析瓶颈(可能发现不是引擎问题);重构风险;可能引入 bug

**涉及文件**:
- `ohmyquant/engine/backtest.py`
- 可能涉及 `ohmyquant/factors/library.py` (缓存)
- 可能涉及 `ohmyquant/data/base.py` (DataCatalog 缓存)

---

### TODO-010: 策略公共逻辑提取

| 属性 | 内容 |
|------|------|
| **优先级** | P2 |
| **成本** | 中 (~100 行) |
| **收益** | 中 |
| **预估工作量** | 4-6 小时 |

**现状**:
- `industry_rotation/v66/strategy.py` 和 `expertForest/v1/strategy.py` 有重复逻辑:
  - 数据源初始化
  - 因子数据加载
  - 回测引擎配置
  - 结果提取

**优化方案**:
1. 在 `BaseStrategy` 或 mixin 中提取通用方法:
   - `_init_data_source()` → 初始化数据源
   - `_load_factor_data()` → 加载因子数据
   - `_run_backtest()` → 运行回测引擎
   - `_extract_result()` → 提取回测结果
2. 策略子类只实现差异部分(选股/风控/调仓配置)

**优劣分析**:
- **优势**: 减少重复代码;新策略更易开发;统一行为
- **劣势**: 过度抽象可能降低灵活性;两个策略差异可能较大,抽象后反而复杂

**涉及文件**:
- `ohmyquant/strategy/base.py`
- `ohmyquant/strategy/strategies/industry_rotation/v66/strategy.py`
- `ohmyquant/strategy/strategies/expertForest/v1/strategy.py`

---

## P3 — 可选优化(按需执行)

### TODO-011: CHANGELOG.md

| 属性 | 内容 |
|------|------|
| **优先级** | P3 |
| **成本** | 低 (1 文件) |
| **收益** | 低 |

**现状**: 无版本日志

**方案**: 创建 `CHANGELOG.md`,记录本次会话的 8+ 次 commit,后续每次发布更新

**优劣**: 优势是版本追溯;劣势是需持续维护

---

### TODO-012: CLI 脚手架生成命令

| 属性 | 内容 |
|------|------|
| **优先级** | P3 |
| **成本** | 中 (~80 行) |
| **收益** | 低 |

**现状**: 有 `scripts/_template/` 模板,但无自动生成

**方案**: 新增 `omq init strategy <name>` 命令,自动创建策略目录结构

**优劣**: 优势是降低新策略开发门槛;劣势是使用频率低

---

### TODO-013: 依赖版本锁定

| 属性 | 内容 |
|------|------|
| **优先级** | P3 |
| **成本** | 低 |
| **收益** | 低 |

**现状**: `requirements.txt` 无版本约束

**方案**: 用 `pip-compile` 或 `poetry` 锁定版本

**优劣**: 优势是可复现环境;劣势是锁定后升级麻烦

---

### TODO-014: factors/builtin 测试

| 属性 | 内容 |
|------|------|
| **优先级** | P3 |
| **成本** | 中 (~200 行) |
| **收益** | 中 |

**现状**: 31 个因子无独立测试

**方案**: 新增 `tests/test_factors.py`,验证因子计算正确性(构造小样本数据 + 预期值)

**优劣**: 优势是因子正确性保障;劣势是需手工构造预期值

---

### TODO-015: walk_forward 测试

| 属性 | 内容 |
|------|------|
| **优先级** | P3 |
| **成本** | 中 (~100 行) |
| **收益** | 中 |

**现状**: `optimization/walk_forward.py` 无测试

**方案**: 新增 `tests/test_walk_forward.py`,测试滚动窗口切分逻辑

**优劣**: 优势是验证跨周期稳定性分析;劣势是需完整回测 mock

---

## 执行路线图

```
阶段 1 (P0): print→logger + pyproject.toml          → 1-2 小时
阶段 2 (P1): execution 测试 + CI/CD + pre-commit     → 3-4 小时
阶段 3 (P2): 类型注解 + 性能分析 + 策略公共逻辑      → 1-2 天
阶段 4 (P3): 按需补充                                → 随时
```

### 建议执行顺序

1. **TODO-001** (print→logger) — 成本最低,收益最高
2. **TODO-002** (pyproject.toml) — 现代化构建配置
3. **TODO-003** (execution 测试) — 保障核心模块正确性
4. **TODO-004** (CI/CD) — 自动化质量保障
5. **TODO-005** (pre-commit) — 提交前检查
6. **TODO-006** (selector 测试) — 保障选股正确性
7. **TODO-009** (性能分析) — 先分析再优化
8. **TODO-007** (类型注解) — 逐步补充
9. **TODO-010** (策略公共逻辑) — 减少重复
10. **TODO-008** (API 文档) — 适合开源时补充
11. **TODO-011~015** — 按需执行

---

## 关键决策点

| 决策 | 推荐方案 | 理由 |
|------|----------|------|
| 日志统一 | `print` → `logger` | 成本最低,收益最高,已有 `core/logging.py` 基础设施 |
| 测试优先级 | `rebalancer` > `scheduler` > `selector` > `factors` | 调仓器影响最大,selector 次之 |
| 工程化 | CI/CD > pre-commit > pyproject.toml | CI/CD 保障主分支质量,pre-commit 保障提交质量 |
| 性能优化 | 先 cProfile 分析再优化 | 避免盲目优化,需数据驱动 |
| 类型注解 | 逐步补充,不强制 strict | 平衡成本与收益 |
| API 文档 | 开源时再补充 | 小项目收益有限 |
| 策略抽象 | 谨慎提取公共逻辑 | 避免过度抽象,两个策略差异可能较大 |

---

## 附录: 当前测试覆盖状态

| 测试文件 | 覆盖模块 | 测试数 | 状态 |
|----------|----------|--------|------|
| `test_core.py` | 插件系统、配置加载 | 8 | ✓ |
| `test_strategy.py` | 策略注册、版本管理 | 5 | ✓ |
| `test_backtest.py` | 成本模型、执行器、引擎 | 6 | ✓ 部分 |
| `test_analysis.py` | 绩效指标、对比、显著性 | 11 | ✓ |
| `test_ths_utils.py` | THS 工具函数 | 20 | ✓ |
| `test_rebalancer.py` | 调仓器 | - | ✗ 待创建 |
| `test_scheduler.py` | 调度器 | - | ✗ 待创建 |
| `test_selector.py` | 选股器 | - | ✗ 待创建 |
| `test_factors.py` | 因子计算 | - | ✗ 待创建 |
| `test_walk_forward.py` | Walk-Forward 验证 | - | ✗ 待创建 |
| **合计** | | **50** | **5/10 覆盖** |
