# Changelog

本文件记录 OhMyQuant 框架的版本变更历史。

格式参考 [Keep a Changelog](https://keepachangelog.com/)。

---

## [0.2.0] — 2026-08-03

### Added — 因子模块全面优化
- **因子参数化** (P1-4): Factor ABC 新增 `params` 属性，运行时通过 config 覆盖窗口期等参数
- **因子缓存** (P1-5): FactorLibrary 支持 LRU 缓存，基于数据指纹哈希避免重复计算
- **外部因子加载** (P1-6): `FactorRegistry.discover_external()` 从外部目录加载自定义因子
- **因子依赖声明** (P2-7): Factor ABC 新增 `depends_on` 属性，FactorLibrary 自动解析依赖
- **因子版本管理** (P2-8): Factor ABC 新增 `version` 属性，写入 PluginMeta
- **因子报告生成器** (P2-9): `FactorReportGenerator` 一键生成 IC/ICIR/分位数/衰减 Markdown 报告

### Changed
- **装饰器去重** (P0-1): `@register_factor()` 自动从类属性读取 name/category，无需重复传参
- **IC 计算向量化** (P0-2): `compute_ic` 改为向量化实现（提速 20-50x），`compute_quantile_returns` 也向量化
- **scipy fallback** (P0-3): scipy 不可用时自动降级到 numpy 实现的 `_rankdata`/`_pearson_corr`/`_spearman_corr`
- **31 个内置因子全部更新**: 使用 `@register_factor()` + `params` 参数化

### Tests
- 因子测试从 36 个增加到 60 个（新增 24 个覆盖参数化/缓存/依赖/版本/报告/外部加载）
- 总测试数从 161 增加到 187（185 passed + 2 skipped）

---

## [0.1.0] — 2026-08-03

### Added
- **pyproject.toml** (PEP 621): 现代化项目配置，替代 setup.py + requirements.txt
- **GitHub Actions CI/CD** (`.github/workflows/test.yml`): Python 3.10/3.11/3.12 矩阵测试 + ruff lint
- **pre-commit hooks** (`.pre-commit-config.yaml`): ruff + ruff-format + 基础检查
- **BaseStrategy._load_config_yaml / _deep_merge**: 策略公共配置加载逻辑提取到基类
- **单元测试**: 新增 6 个测试文件，覆盖调仓器(23)、调度器(17)、选股器(18)、因子计算(36)、Walk-Forward(17)、THS工具(20)，合计 161 个测试
- **策略脚手架模板** (`scripts/_template/`): strategy.py.tmpl + config.yaml.tmpl
- **CONTRIBUTING.md**: 开发规范文档
- **CHANGELOG.md**: 版本变更记录（本文件）

### Changed
- **CLI init 命令增强**: 支持在 `ohmyquant/strategy/strategies/` 下创建策略，自动生成 `__init__.py`
- **README 更新**: 安装方式改为 `pip install -e ".[dev]"`，移除具体策略信息，通用化描述
- **docs/ 目录重组**: 拆分为 `framework/` 和 `strategies/` 子目录
- **scripts/ 目录重组**: 按 `common/`、`industry_rotation/`、`expertforest_v1/` 子目录分组
- **run_oos_backtest 提取**: 从 industry_rotation_daily.py 提取到 `ohmyquant/strategy/runner.py`

### Removed
- **setup.py**: 由 pyproject.toml 替代
- **requirements.txt**: 由 pyproject.toml 的 `[project.dependencies]` 替代
- **JoinQuant 数据下载代码**: 移除数据下载/更新，改为仅消费外部数据
- **死代码清理**: tracking/、integration/、optimization/signal.py 等仅自引用文件

### Fixed
- **ths_utils.py mock 修复**: test_ths_utils.py 的 mock DataFrame 添加 `__len__` 方法
- **expertForest __init__.py**: 修复父目录缺少 `__init__.py` 导致导入失败
- **IC 缓存 NaN 问题**: 用 `None` 替代 `np.nan` 表示缺失值，避免 polars `drop_nulls()` 无法移除 NaN

---

## 历史提交摘要

| Commit | 描述 |
|--------|------|
| `6aadbda` | docs: 添加优化 TODO 列表 |
| `6c26ca1` | docs: 更新 README 和框架文档准确性 |
| `e645d25` | refactor: 移除 JoinQuant 数据下载，仅消费外部数据 |
| `2b537f9` | chore: 脱敏硬编码路径，排除 archive |
| `11c9e4b` | feat: 策略框架完善 P0-P4 |
| `1f20efc` | refactor: scripts 子目录分组 |
| `f5c85b1` | docs: industry_rotation v66 策略报告 |
| `ec3166a` | refactor: 提取 ths_utils 到框架层 |
| `56d9450` | chore: 整理清理 scripts 目录 |
| `d93c3df` | feat: v49 IC 加权探索（失败） |
| `c8ab84f` | feat: v45-v48 迭代探索 |
| `30c9057` | feat: v42-v44 迭代 |
| `3d0e008` | feat: v41 RRG 权重优化 |
| `59fe219` | feat: v38-v40 迭代 |
| `758c1c2` | docs: v30 策略报告 |
| `75155c1` | feat: v17-v37 迭代 + v30 final |
| `1171f21` | feat: v15 final + daily.py 升级 |
| `3602ea2` | feat: v14/v15/v16 迭代 |
| `560bd26` | feat: v10/v11/v12 探索 |
