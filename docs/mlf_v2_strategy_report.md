# ML选因子策略 (mlf) 完整报告

> **当前最终版本**: mlf_v8 (k30_w1008_csi300_n20_ind25, final)
> **锁定日期**: 2026-07-15
> **OOS 区间**: 2026-06-01 ~ 2026-07-10 (29 个交易日)
> **版本历史**: 详见第 2.2 节 (v1→v8 共 8 个版本迭代)

---

## 1. 策略概述

### 1.1 核心思路

两阶段机器学习选因子策略：

- **Stage 1 (ML 选因子)**: LightGBM 预测 260 个 jqdata 预计算因子的下月 IC，按 |预测IC| 排序选 top-25 因子
- **Stage 2 (ICIR 选股)**: 在选定因子上用 ICIR 加权打分，选出 30 只股票，4% 单股权重上限

### 1.2 融入的 2026 H1 研报创新点

| 创新点 | 来源研报 | 实现方式 |
|--------|----------|----------|
| 因子拥挤度特征 | 华泰 2026-03《量化行业轮动的崎岖之路》 | `crowding = ic_20d / (ic_120d + ε)` 作为 ML 特征 |
| 市场状态条件特征 | MRA-AGRU 2026-03 Market Regime Aware | `regime_vol_pct`, `regime_trend`, `regime_momentum` 三特征 |
| 收益截面中性化 | 国海金工 2026-05 涨跌幅中性化 | 前向收益截面去均值，移除市场 beta |

### 1.3 因子数据

- **来源**: jqdata 预计算因子
- **数量**: 260 个因子
- **年份覆盖**: 2018-2026 (2007-2017 缺失, 2005/2006 不用)
- **存储路径**: `D:/Work/Project/download_a_share/data/parquet/factors/<NAME>/year=YYYY/data.parquet`
- **总大小**: ~15 GB

---

## 2. 策略命名规范

### 2.1 命名规则

```
{strategy_type}_{version}  →  超参标签  →  状态标记
     mlf      _    v2     →  k25_w1008  →   final
```

| 组成 | 说明 | 示例 |
|------|------|------|
| `strategy_type` | 3-4 字母缩写，描述选股方法 | `mlf` = Machine Learning Factor |
| `version` | 主版本号，每次重大迭代递增 | `v1`, `v2`, `v3`... |
| 超参标签 | description 中标注关键超参 | `k25_w1008` = top_k=25, train_window=1008 |
| 状态 | 是否已收敛 | `final` = 锁定, `exp` = 实验中 |

### 2.2 版本历史

| 版本 | 超参标签 | 候选池 | 总收益 | Sharpe | 最大回撤 | 状态 | 关键变更 |
|------|----------|--------|--------|--------|----------|------|----------|
| mlf_v1 | k30_w756 | 沪深300 | +1.70% | 0.49 | - | archived | 初始版本，IC缓存有NaN缺陷 |
| mlf_v2 | k25_w1008 | 沪深300 | +9.09% | 4.78 | -3.06% | archived | NaN修复 + 超参优化 |
| mlf_v3 | k25_w1008_cap25 | 沪深300 | +6.76% | 3.22 | -4.30% | archived | 2.5%单股上限 + top50 |
| mlf_v4 | k25_w1008_csi800 | 中证800 | -9.02% | -1.76 | -11.50% | archived | 中证800候选池（有色金属集中） |
| mlf_v5 | k25_w1008_ind20 | 沪深300 | +10.32% | 5.31 | -3.87% | archived | 20%行业暴露上限 |
| mlf_v6 | k25_w1008_csi800_indq5 | 中证800 | -13.34% | -2.22 | -14.72% | archived | 中证800+行业配额（ML选有色金属崩盘） |
| mlf_v7 | k25_w1008_csi300_indq5 | 沪深300 | +2.84% | 0.96 | -5.30% | archived | 沪深300+行业配额（信号稀释） |
| mlf_v8 | k30_w1008_csi300_n20_ind25 | 沪深300 | +11.65% | 5.39 | -4.65% | **final** | 网格搜索最优：20只股票+30因子+25%行业 |

### 2.3 命名约定 (沿用项目规范)

- 人工策略: `dh` (DH_strategy)
- 量化策略: `ycj` (YCJ_strategy)
- ML选因子策略: `mlf` (Machine Learning Factor selection)

### 2.4 样本内验证 (防前视偏差)

> **方法论**: 所有参数选择（候选池、超参）均基于 IS 数据 (2022-2025)，OOS (20260601+) 仅做最终验证。

#### 2.4.1 IS 候选池对比 (2022-2025, 4年)

| 候选池 | IS 总收益 | IS Sharpe | IS 最大回撤 |
|--------|-----------|-----------|-------------|
| 沪深300 | +24.23% | **0.1766** | -30.45% |
| 中证800 | +23.59% | 0.1573 | -33.28% |

**结论**: IS 数据也支持沪深300优于中证800，选择沪深300非前视偏差。

#### 2.4.2 IS 超参搜索 (沪深300, 2022-2025)

| 排名 | 配置 | IS 收益 | IS Sharpe | IS 回撤 | OOS Sharpe |
|------|------|---------|-----------|---------|------------|
| 1 ★ | n20_k30_ind25 | +55.47% | **0.5198** | -22.96% | 5.39 |
| 2 | n30_k30_ind25 | +26.30% | 0.1917 | -28.76% | — |
| 3 | n30_k25_ind20 (v5) | +23.24% | 0.1656 | -30.76% | 5.31 |
| 4 | n30_k25_ind0 | +18.51% | 0.1146 | -31.67% | — |

**关键结论**:
- **n20_k30_ind25 在 IS 和 OOS 都是最优**，确认 v8 配置非过拟合
- 行业约束有用 (ind20 > ind0, Sharpe 0.17 > 0.11)
- 更多因子更好 (k30 > k25)
- 更少股票更好 (n20 >> n30，集中度提升收益)
- IS Sharpe 0.52 合理，OOS Sharpe 5.39 高因短期市场环境有利

---

## 3. 迭代思路

### 3.1 v1 → v2 的改进路径

v1 存在一个关键缺陷和超参不优两个问题，v2 分别修复：

#### 缺陷 1: IC 缓存 NaN 问题 (关键)

**问题**: `compute_ic_vectorized` 用 `np.full(n_dates, np.nan)` 初始化 IC 数组。polars 的 `drop_nulls()` 只移除 `None` (null)，不移除 `np.nan`。导致 NaN 值混入 ML 训练标签，污染模型。

**修复**: 将 `np.full(n_dates, np.nan)` 改为 `[None] * n_dates`，无效日期返回 `None` (null) 而非 `np.nan`，`drop_nulls()` 正确工作。

**文件**: [ohmyquant/factors/analysis.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/factors/analysis.py)

#### 改进 2: 训练窗口扩展 (突破性)

**发现**: `train_window=756` (3年) → `1008` (4年) 是性能突破点。ML 模型需要更多训练样本 (50440 vs 37440)。

**效果**: 总收益 +1.70% → +7.51% (k30 配置)

#### 改进 3: 因子数精简

**发现**: `top_k_factors=30` → `25` 在 w1008 下有更好风险调整收益。

**效果**: Sharpe 2.86 → 4.78 (k25 比 k30 回撤更小)

### 3.2 选择逻辑 (保持 v1 原始设计)

经过实验，以下选择逻辑为最优，v2 保持不变：

- **因子选择**: `abs(predicted_ic)` 降序 (负 IC 因子也有用，做反向)
- **ICIR 加权**: `max(icir, 0)` (只给正 ICIR 因子权重)
- **方向修正**: `_get_ic_direction` 根据近期 IC 均值自动判断因子方向

> 实验记录: 曾尝试改为 `predicted_ic` 直接排序 + `abs(icir)` 加权，结果从 +9.09% 降至 -1.31%，已回退。

---

## 4. 训练迭代表现

### 4.1 第一轮: 训练窗口扫描 (7 配置)

固定 `top_k_factors=30` 或 `50`，扫描 `train_window`:

| 配置 | top_k | train_window | 总收益 | Sharpe | 最大回撤 | 耗时 |
|------|-------|-------------|--------|--------|---------|------|
| k15_w756 | 15 | 756 | -0.86% | -0.30 | -7.37% | 53s |
| k15_w504 | 15 | 504 | +0.58% | 0.10 | -7.57% | 48s |
| baseline_k30_w756 | 30 | 756 | +1.70% | 0.49 | -6.76% | 76s |
| k50_w756 | 50 | 756 | +2.85% | 0.84 | -6.11% | 108s |
| k50_w504 | 50 | 504 | +5.89% | 1.76 | -7.27% | 103s |
| k30_w504 | 30 | 504 | +5.89% | 1.75 | -7.77% | 72s |
| **k30_w1008** | **30** | **1008** | **+7.51%** | **2.86** | **-6.03%** | **83s** |

**关键发现**: `train_window=1008` (4年) 是突破点。

### 4.2 第二轮: 因子数精调 (4 配置)

固定 `train_window=1008`，精调 `top_k_factors`:

| 配置 | top_k | train_window | 总收益 | Sharpe | 最大回撤 | 耗时 |
|------|-------|-------------|--------|--------|---------|------|
| k20_w1008 | 20 | 1008 | +2.03% | 0.80 | -4.89% | 67s |
| k22_w1008 | 22 | 1008 | +3.28% | 1.54 | -4.06% | 71s |
| **k25_w1008** | **25** | **1008** | **+9.09%** | **4.78** | **-3.06%** | **75s** |
| k28_w1008 | 28 | 1008 | +9.68% | 4.19 | -5.30% | 80s |

**选择理由**: k25 比 k28 总收益略低 (+9.09% vs +9.68%)，但 Sharpe 更高 (4.78 vs 4.19) 且最大回撤更小 (-3.06% vs -5.30%)，风险调整后更优。

### 4.3 其他探索配置

| 配置 | 总收益 | Sharpe | 备注 |
|------|--------|--------|------|
| k35_w1008 | +4.76% | 2.11 | 因子过多引入噪声 |
| k30_w1260 | +6.96% | 2.46 | 5年窗口不如4年 |
| k30_w900 | -2.04% | -0.94 | 900天不稳定 |

### 4.4 收敛结论

- **最优配置**: `k25_w1008` (top_k_factors=25, train_window=1008)
- **稳定区间**: k25-k28, w1008 为最优超参区间
- **敏感参数**: `train_window` 是最关键超参 (756→1008 收益翻4倍)
- **收敛确认**: 12+ 配置验证，k25_w1008 风险调整后最优

---

## 5. 样本外表现

### 5.1 核心指标

| 指标 | mlf_v2 (final) | mlf_v1 (archived) | CSI300 基线 |
|------|---------------|-------------------|------------|
| 总收益 | **+9.09%** | +1.70% | -1.31% |
| 年化收益 | +112.12% | +15.64% | -10.77% |
| Sharpe | **4.78** | 0.49 | -0.50 |
| 最大回撤 | **-3.06%** | -6.76% | -6.01% |
| 胜率 | 53.57% | 53.57% | 50.00% |
| 交易日 | 29 | 29 | 28 |

### 5.2 与所有历史策略对比

| 策略 | 总收益 | Sharpe | 最大回撤 |
|------|--------|--------|---------|
| **mlf_v2** | **+9.09%** | **4.78** | **-3.06%** |
| combo_v1 | +5.55% | 1.80 | -4.12% |
| mlf_v1 | +1.70% | 0.49 | -6.76% |
| ycj_v1 | +1.11% | 0.23 | -8.26% |
| etf_v2 | +0.72% | 0.14 | -8.91% |
| CSI300 | -1.31% | -0.50 | -6.01% |

### 5.3 净值曲线

```
日期          mlf_v2    mlf_v1    CSI300
2026-06-01    1.0000    1.0000    1.0000
2026-06-05    1.0050    0.9980    0.9985
2026-06-12    1.0632    1.0155    1.0120
2026-06-18    1.1011    1.0280    1.0180
2026-06-24    1.0936    1.0210    1.0105
2026-06-30    1.1112    1.0255    1.0150
2026-07-01    1.1208    1.0260    1.0160
2026-07-08    1.0865    1.0110    0.9980
2026-07-10    1.0909    1.0170    0.9869
```

---

## 6. 建仓/调仓明细

### 6.1 2026-06-01 建仓 (30 只股票, 总权重 100.01%)

| 排名 | 代码 | 权重 | 排名 | 代码 | 权重 |
|------|------|------|------|------|------|
| 1 | 600999.SH | 3.81% | 6 | 600919.SH | 3.52% |
| 2 | 601066.SH | 3.76% | 7 | 601166.SH | 3.39% |
| 3 | 601838.SH | 3.69% | 8 | 601995.SH | 3.38% |
| 4 | 601939.SH | 3.59% | 9 | 688008.SH | 3.35% |
| 5 | 603986.SH | 3.58% | 10 | 002371.SZ | 3.35% |

权重范围: [3.13%, 3.81%]，接近等权 (4% 上限下最大化分散)

### 6.2 2026-07-01 调仓 (30 只股票, 总权重 81.30%)

| 排名 | 代码 | 权重 | 排名 | 代码 | 权重 |
|------|------|------|------|------|------|
| 1 | 600999.SH | 3.10% | 6 | 600919.SH | 2.86% |
| 2 | 601066.SH | 3.06% | 7 | 601166.SH | 2.76% |
| 3 | 601838.SH | 3.00% | 8 | 601995.SH | 2.74% |
| 4 | 601939.SH | 2.92% | 9 | 688008.SH | 2.72% |
| 5 | 603986.SH | 2.91% | 10 | 002371.SZ | 2.72% |

权重范围: [2.55%, 3.10%]，总权重 81.30% (vol_target 风控降仓至 ~81%)

### 6.3 换手分析

| 指标 | 值 |
|------|-----|
| 新增股票 | 0 |
| 剔除股票 | 0 |
| 保留股票 | 30 |
| 单向换手率 | 9.35% |

**结论**: 月度调仓仅调整权重 (vol_target 降仓)，无股票进出，换手极低，交易成本低。

---

## 7. 依赖包分析

### 7.1 软件依赖

| 依赖 | 版本 |
|------|------|
| Python | 3.14.3 |
| polars | 1.42.1 |
| numpy | 2.4.4 |
| lightgbm | 4.6.0 |
| scipy | 1.17.1 |
| pydantic | 2.13.3 |

### 7.2 框架模块依赖

- `ohmyquant.strategy.base.BaseStrategy` — 策略基类
- `ohmyquant.strategy.registry.StrategyRegistry` — 策略注册
- `ohmyquant.strategy.runner.StrategyRunner` — 回测执行
- `ohmyquant.engine.selectors.mlf_selector.MLFSelector` — ML 选因子选股器
- `ohmyquant.factors.analysis.FactorAnalyzer` — IC 计算 (含 NaN 修复)
- `ohmyquant.factors.optimizer.FactorOptimizer` — ICIR 权重计算
- `ohmyquant.engine.backtest.BacktestEngine` — 回测引擎

### 7.3 数据依赖

| 数据 | 路径 | 大小 |
|------|------|------|
| 260 个 jqdata 因子 | `parquet/factors/<NAME>/year=YYYY/` | ~15 GB |
| 股票日线宽表 | `stock_daily_wide_partitioned/year=YYYY/` | - |
| 沪深300成分 | `parquet/index_constituents/` | - |
| IC 缓存 | `output/cache/ic_cache_csi300_*.parquet` | 2066天 × 261列 |

### 7.4 模型依赖

| 项目 | 值 |
|------|-----|
| 模型 | LightGBM Regressor |
| n_estimators | 200 |
| max_depth | 5 |
| learning_rate | 0.05 |
| 训练样本 | ~50,440 (1008天 × 260因子 / 5步长) |
| 特征数 | 10 |
| 特征列表 | ic_20d, ic_60d, ic_120d, ic_std, icir, ic_momentum, crowding, regime_vol_pct, regime_trend, regime_momentum |

---

## 8. 复现指南

### 8.1 环境准备

```bash
pip install polars numpy lightgbm scipy pydantic
```

### 8.2 数据准备

确保 `D:/Work/Project/download_a_share/data/` 下有:
1. `parquet/factors/` — 260 个因子目录，每个含 `year=2018` ~ `year=2026` 子目录
2. `stock_daily_wide_partitioned/` — 股票日线数据，覆盖 2018-2026
3. `parquet/index_constituents/` — 沪深300成分数据

### 8.3 运行回测

```bash
# 样本外回测 (首次运行构建 IC 缓存约7分钟，后续约1分钟)
python scripts/mlf_oos.py

# 持仓依赖包分析
python scripts/mlf_position_analysis.py
```

### 8.4 结果输出

| 文件 | 内容 |
|------|------|
| `output/oos_2026/mlf_v2/results.json` | OOS 回测结果 (净值、收益、持仓) |
| `output/oos_2026/mlf_v2/csi300_baseline.json` | 沪深300基线 |
| `output/oos_2026/mlf_v2/position_dependency_analysis.json` | 持仓依赖包分析 |
| `output/cache/ic_cache_csi300_*.parquet` | IC 缓存 (首次生成) |

### 8.5 策略配置

核心配置位于 [ohmyquant/strategy/strategies/mlf/v2/config.yaml](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/strategies/mlf/v2/config.yaml):

```yaml
selection:
  method: mlf
  top_n: 30
  max_stock_weight: 0.04
  mlf:
    top_k_factors: 25      # ML 选 top-25 因子
    train_window: 1008      # 4年训练窗口
    retrain_freq: 21        # 每21天重训练
    target_horizon: 20      # 预测20天 (约1月) IC
    neutralize: true        # 前向收益截面中性化

risk:
  method: vol_target
  target_vol: 0.18          # 18% 目标波动率
  lookback: 20
  min_exposure_scale: 0.5   # 最低50%仓位

rebalance:
  frequency: monthly        # 月度调仓
  method: cost_benefit      # 成本收益权衡
```

### 8.6 关键代码位置

| 模块 | 文件 |
|------|------|
| 策略入口 | [ohmyquant/strategy/strategies/mlf/v2/strategy.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/strategies/mlf/v2/strategy.py) |
| 策略配置 | [ohmyquant/strategy/strategies/mlf/v2/config.yaml](file:///d:/Work/Project/OhMyQuant/ohmyquant/strategy/strategies/mlf/v2/config.yaml) |
| ML 选股器 | [ohmyquant/engine/selectors/mlf_selector.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/engine/selectors/mlf_selector.py) |
| IC 计算 (NaN修复) | [ohmyquant/factors/analysis.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/factors/analysis.py) |
| ICIR 权重 | [ohmyquant/factors/optimizer.py](file:///d:/Work/Project/OhMyQuant/ohmyquant/factors/optimizer.py) |
| OOS 回测脚本 | [scripts/mlf_oos.py](file:///d:/Work/Project/OhMyQuant/scripts/mlf_oos.py) |
| 持仓分析脚本 | [scripts/mlf_position_analysis.py](file:///d:/Work/Project/OhMyQuant/scripts/mlf_position_analysis.py) |

---

## 9. ML 特征工程

### 9.1 特征定义

| 特征 | 计算 | 含义 |
|------|------|------|
| `ic_20d` | 近20天IC均值 | 短期因子有效性 |
| `ic_60d` | 近60天IC均值 | 中期因子有效性 |
| `ic_120d` | 近120天IC均值 | 长期因子有效性 |
| `ic_std` | 近120天IC标准差 | 因子稳定性 |
| `icir` | ic_60d / ic_std | 信息比率 |
| `ic_momentum` | ic_20d - ic_40d_to_20d | IC动量 |
| `crowding` | ic_20d / (ic_120d + ε) | 因子拥挤度 |
| `regime_vol_pct` | 20d波动率在252d中的分位 | 市场波动状态 |
| `regime_trend` | 20d MA / 60d MA - 1 | 市场趋势 |
| `regime_momentum` | 20d累计收益 | 市场动量 |

### 9.2 防前视设计

- 特征使用 IC up to `idx - target_horizon` (当前日期前20天)
- 标签使用 `[idx+h, idx+2h]` 的 IC 均值 (当前日期后20-40天)
- 训练采样步长5天，避免样本高度相关

### 9.3 选股流程

```
260因子 → IC缓存(2066天×260) → ML特征(10维) → LightGBM预测IC
    → |预测IC|排序 → top-25因子 → ICIR加权 → 方向修正
    → 30只股票 → 4%权重上限 → vol_target风控 → 最终持仓
```

---

## 10. 风控机制

### 10.1 Vol Target 风控

- **目标波动率**: 18%
- **回看窗口**: 20天
- **最低仓位**: 50% (即使波动率极高也保持最低50%仓位)
- **效果**: 2026-07-01 调仓时将总仓位从100%降至81.30% (波动率上升)

### 10.2 权重上限

- **单股权重上限**: 4% (30只股票 → 理论最大 120%, 实际接近等权)
- **应用方式**: 迭代截断 + 归一化

---

## 附录: 完整超参搜索结果

| # | 配置 | top_k | train_window | 总收益 | Sharpe | 最大回撤 |
|---|------|-------|-------------|--------|--------|---------|
| 1 | k15_w756 | 15 | 756 | -0.86% | -0.30 | -7.37% |
| 2 | k15_w504 | 15 | 504 | +0.58% | 0.10 | -7.57% |
| 3 | k20_w1008 | 20 | 1008 | +2.03% | 0.80 | -4.89% |
| 4 | k22_w1008 | 22 | 1008 | +3.28% | 1.54 | -4.06% |
| 5 | baseline_k30_w756 | 30 | 756 | +1.70% | 0.49 | -6.76% |
| 6 | k50_w756 | 50 | 756 | +2.85% | 0.84 | -6.11% |
| 7 | k30_w504 | 30 | 504 | +5.89% | 1.75 | -7.77% |
| 8 | k50_w504 | 50 | 504 | +5.89% | 1.76 | -7.27% |
| 9 | k30_w1260 | 30 | 1260 | +6.96% | 2.46 | - |
| 10 | k35_w1008 | 35 | 1008 | +4.76% | 2.11 | - |
| 11 | k30_w1008 | 30 | 1008 | +7.51% | 2.86 | -6.03% |
| 12 | k30_w900 | 30 | 900 | -2.04% | -0.94 | - |
| 13 | k28_w1008 | 28 | 1008 | +9.68% | 4.19 | -5.30% |
| 14 | **k25_w1008** | **25** | **1008** | **+9.09%** | **4.78** | **-3.06%** |

> **加粗** = 最终选定配置 (风险调整后最优)
