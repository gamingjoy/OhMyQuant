# scripts/ 目录索引

本目录存放策略迭代过程中**可复用**的核心脚本与工具脚本,按子目录分组组织。
一次性探索/诊断脚本已归档至 `archive/scripts/`。

## 目录结构

```
scripts/
├── common/                 # 通用工具(跨策略复用)
│   ├── update_data.py
│   ├── regenerate_ths_files.py
│   └── verify_ths_trades.py
├── industry_rotation/      # 行业轮动策略
│   ├── industry_rotation_daily.py
│   ├── industry_rotation_is.py
│   ├── industry_rotation_oos.py
│   └── industry_rotation_nav_analysis.py
└── expertforest_v1/        # 专家集成策略
    ├── expertforest_v1_is_explore.py
    ├── expertforest_v1_oos_validate.py
    ├── expertforest_v1_position_analysis.py
    ├── expertforest_v1_compare_results.py
    ├── expertforest_v1_per_expert_analysis.py
    └── expertforest_v1_expert_correlation.py
```

## 框架规范

每个策略应在 `scripts/{strategy_name}/` 下提供以下核心脚本(命名格式 `{strategy_name}_{purpose}.py`):

| 用途 | 命名规范 | 说明 |
|------|----------|------|
| IS 回测 | `{strategy}_is.py` | 样本内回测,支持版本参数化 |
| OOS 验证 | `{strategy}_oos.py` | 样本外验证 |
| 日常调仓 | `{strategy}_daily.py` | T日早晨检查+生成同花顺交易文件 |
| 净值分析 | `{strategy}_nav_analysis.py` | 基于 THS 文件回放算净值 |
| 建仓调仓分析 | `{strategy}_position_analysis.py` | 建仓+调仓详细报告 |

通用工具(跨策略复用)放在 `scripts/common/`:

| 用途 | 命名规范 | 说明 |
|------|----------|------|
| 批量生成 THS | `regenerate_ths_files.py` | 批量重新生成全部 OOS THS 文件 |
| 验证 THS | `verify_ths_trades.py` | 验证 THS xlsx 一致性 |
| 数据更新 | `update_data.py` | 增量数据更新(T-1数据 + 当年全量 + 前一年) |

## 当前脚本清单

### 通用工具 (`scripts/common/`)

| 脚本 | 用途 |
|------|------|
| [update_data.py](common/update_data.py) | 增量数据更新(T-1数据 + 当年全量 + 前一年) |
| [regenerate_ths_files.py](common/regenerate_ths_files.py) | 批量重新生成全部 OOS THS 文件(复用 industry_rotation_daily 的 run_oos_backtest) |
| [verify_ths_trades.py](common/verify_ths_trades.py) | 验证 THS xlsx 一致性 |

### 行业轮动策略 (`scripts/industry_rotation/`, v66 final)

| 脚本 | 用途 |
|------|------|
| [industry_rotation_daily.py](industry_rotation/industry_rotation_daily.py) | T日早晨调仓检查 + 生成同花顺交易文件 |
| [industry_rotation_is.py](industry_rotation/industry_rotation_is.py) | IS 回测通用版(支持版本对比) |
| [industry_rotation_oos.py](industry_rotation/industry_rotation_oos.py) | OOS 回测通用版 |
| [industry_rotation_nav_analysis.py](industry_rotation/industry_rotation_nav_analysis.py) | 基于 THS 文件回放算净值 |

### 专家集成策略 (`scripts/expertforest_v1/`)

| 脚本 | 用途 |
|------|------|
| [expertforest_v1_is_explore.py](expertforest_v1/expertforest_v1_is_explore.py) | IS 验证(支持 pool/top_n/ensemble/feature_sets 参数) |
| [expertforest_v1_oos_validate.py](expertforest_v1/expertforest_v1_oos_validate.py) | OOS 验证(含 train_windows/model_types 维度) |
| [expertforest_v1_position_analysis.py](expertforest_v1/expertforest_v1_position_analysis.py) | 建仓+调仓+THS生成+专家投票报告 |
| [expertforest_v1_compare_results.py](expertforest_v1/expertforest_v1_compare_results.py) | 多维配置(pool×N×ensemble×fs)结果对比汇总 |
| [expertforest_v1_per_expert_analysis.py](expertforest_v1/expertforest_v1_per_expert_analysis.py) | 每专家 forward IC + 分组统计 + 月度 IC |
| [expertforest_v1_expert_correlation.py](expertforest_v1/expertforest_v1_expert_correlation.py) | 32×32 相关性 + Jaccard 重叠度 + 冗余识别 |

## 归档脚本

一次性探索/诊断脚本(结论已固化至 `docs/` 或 `project_memory.md`)归档至:

```
archive/scripts/
├── industry_rotation/       # 行业轮动一次性验证脚本
├── expertforest_v1/         # 专家集成一次性迭代/诊断脚本
└── data_explore/            # 通用数据探索脚本
```

## 新策略开发指引

新增策略(如 `momentum_v1`)应遵循以下步骤:

1. 在 `ohmyquant/strategy/strategies/{strategy_name}/v{version}/` 实现策略类
2. 在 `scripts/{strategy_name}/` 添加核心脚本(参照上表命名规范)
3. 通用工具放 `scripts/common/`,策略专属脚本放 `scripts/{strategy_name}/`
4. 日常调仓脚本应复用 `ohmyquant/execution/ths_utils.py` 框架层工具,避免跨策略 import
5. 一次性探索脚本开发完成后移动到 `archive/scripts/{strategy_name}/`
6. 在本 README 表格中登记新脚本

## sys.path 注意事项

脚本子目录化后,所有脚本的 `sys.path.insert` 需用 `parents[2]` 定位项目根:

```python
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # scripts/xxx/ -> scripts/ -> 项目根
```

跨策略 import(如 common/regenerate_ths_files.py 引用 industry_rotation/industry_rotation_daily.py)需额外加:

```python
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "industry_rotation"))
```
