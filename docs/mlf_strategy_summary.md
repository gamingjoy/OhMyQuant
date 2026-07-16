# ML选因子策略 (mlf) 迭代总结

> **一句话**: LightGBM 预测 260 因子下月 IC → 选 top-30 因子 → ICIR 加权选 20 只股票
> **当前最终版本**: mlf_v8 (k30_w1008_csi300_n20_ind25)
> **详细报告**: [mlf_strategy_report.md](./mlf_strategy_report.md)

---

## 迭代路线图

```
v1 (k30_w756)          IC缓存NaN缺陷, +1.70%
  ↓ 修复NaN + 训练窗口756→1008
v2 (k25_w1008)         +9.09%, Sharpe 4.78
  ↓ 加2.5%单股上限
v3 (cap25)             +6.76% (上限过严)
  ↓ 试中证800候选池
v4 (csi800)            -9.02% (有色金属集中)
  ↓ 回沪深300 + 20%行业上限
v5 (ind20)             +10.32%, Sharpe 5.31  ← 前一版final
  ↓ IS验证 + 超参搜索
v8 (n20_k30_ind25)     +11.65%, Sharpe 5.39  ← 当前final
```

## 核心指标对比

### OOS 表现 (2026-06-01 ~ 2026-07-10, 29天)

| 版本 | 配置 | 收益 | Sharpe | 回撤 |
|------|------|------|--------|------|
| v2 | k25, n30, 无约束 | +9.09% | 4.78 | -3.06% |
| v5 | k25, n30, ind20% | +10.32% | 5.31 | -3.87% |
| **v8** | **k30, n20, ind25%** | **+11.65%** | **5.39** | **-4.65%** |

### IS 验证 (2022-2025, 4年)

| 配置 | IS收益 | IS Sharpe | IS回撤 | OOS Sharpe |
|------|--------|-----------|--------|------------|
| **n20_k30_ind25 (v8)** | **+55.47%** | **0.52** | -22.96% | 5.39 |
| n30_k30_ind25 | +26.30% | 0.19 | -28.76% | — |
| n30_k25_ind20 (v5) | +23.24% | 0.17 | -30.76% | 5.31 |
| n30_k25_ind0 | +18.51% | 0.11 | -31.67% | — |

**v8 在 IS 和 OOS 都是最优，确认非过拟合。**

## v8 最终配置

| 参数 | 值 | 说明 |
|------|-----|------|
| 候选池 | 沪深300 | 大盘股，排除小微股 |
| top_k_factors | 30 | ML选30个因子 |
| top_n | 20 | 选20只股票 |
| train_window | 1008 | 4年训练窗口 |
| retrain_freq | 21 | 每21天重训练 |
| max_stock_weight | 4% | 单股权重上限 |
| max_industry_weight | 25% | 行业暴露上限 |
| 候选池对比 | 沪深300 > 中证800 | IS验证确认 |

## 文件结构

```
ohmyquant/strategy/strategies/mlf/
├── v5/                    # 前一版final (archived)
│   ├── __init__.py
│   ├── config.yaml
│   └── strategy.py
└── v8/                    # 当前final ★
    ├── __init__.py
    ├── config.yaml
    └── strategy.py

scripts/
├── mlf_v8_oos.py          # v8 OOS验证
├── mlf_is_pool_compare.py # IS候选池对比
├── mlf_is_gridsearch.py   # IS超参搜索
└── mlf_position_analysis.py # 持仓分析

archive/strategies/mlf/    # 归档的旧版本
├── v1/ ~ v4/, v6/, v7/

docs/
├── mlf_strategy_report.md     # 详细报告
└── mlf_strategy_summary.md    # 本文档
```

## 关键经验

1. **训练窗口 756→1008 是突破点**: 4年训练数据显著提升ML模型质量
2. **沪深300优于中证800**: IS/OOS双验证，中证800让ML选到周期股崩盘
3. **少股票+多因子更好**: n20+k30 > n30+k25，集中度提升收益
4. **行业约束有用但不宜过严**: 25% > 20% > 15% > 无约束
5. **IS验证防过拟合**: OOS上搜索参数会过拟合，必须用IS数据做决策
