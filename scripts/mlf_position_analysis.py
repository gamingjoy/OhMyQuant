"""mlf_v2 建仓/调仓持仓依赖包分析

分析 20260601 建仓 和 20260701 调仓的：
1. 持仓明细（股票、权重）
2. 仓位变化（换手率、新增/剔除）
3. 数据依赖（因子文件、IC缓存、股票数据）
4. 模型依赖（LightGBM、训练样本、超参）
5. 软件依赖（Python 包及版本）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

RESULTS_FILE = Path("output/oos_2026/mlf_v2/results.json")
DATA_ROOT = Path("D:/Work/Project/download_a_share/data")
IC_CACHE = Path("output/cache/ic_cache_csi300_2018-01-02_2026-07-10.parquet")
OUTPUT_FILE = Path("output/oos_2026/mlf_v2/position_dependency_analysis.json")


def load_results() -> dict:
    if not RESULTS_FILE.exists():
        print(f"错误: 结果文件不存在: {RESULTS_FILE}")
        sys.exit(1)
    with open(RESULTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def analyze_holdings(rebalance_log: list[dict]) -> dict:
    """分析建仓和调仓持仓"""
    analysis = {}

    for entry in rebalance_log:
        date = entry["date"]
        holdings = entry.get("holdings", {})
        sorted_holdings = sorted(
            holdings.items(), key=lambda x: x[1], reverse=True
        )

        analysis[date] = {
            "n_stocks": len(holdings),
            "total_weight": round(sum(holdings.values()), 4),
            "max_weight": round(sorted_holdings[0][1], 4) if sorted_holdings else 0,
            "min_weight": round(sorted_holdings[-1][1], 4) if sorted_holdings else 0,
            "top10": [
                {"code": c, "weight": round(w, 4)}
                for c, w in sorted_holdings[:10]
            ],
            "all_holdings": {c: round(w, 4) for c, w in sorted_holdings},
        }

    # 换手率分析
    dates = sorted(analysis.keys())
    if len(dates) >= 2:
        d1, d2 = dates[0], dates[1]
        h1 = set(analysis[d1]["all_holdings"].keys())
        h2 = set(analysis[d2]["all_holdings"].keys())

        added = h2 - h1
        removed = h1 - h2
        common = h1 & h2

        # 权重变化
        weight_changes = {}
        for code in common:
            w1 = analysis[d1]["all_holdings"][code]
            w2 = analysis[d2]["all_holdings"][code]
            weight_changes[code] = round(w2 - w1, 4)

        # 换手率（单向）
        turnover = sum(abs(wc) for wc in weight_changes.values()) / 2
        for code in added:
            turnover += analysis[d2]["all_holdings"][code]
        for code in removed:
            turnover += analysis[d1]["all_holdings"][code]
        turnover = round(turnover, 4)

        analysis["_turnover_analysis"] = {
            "from_date": d1,
            "to_date": d2,
            "stocks_added": sorted(added),
            "stocks_removed": sorted(removed),
            "n_common": len(common),
            "n_added": len(added),
            "n_removed": len(removed),
            "turnover_one_sided": turnover,
            "weight_changes_common": dict(
                sorted(
                    weight_changes.items(),
                    key=lambda x: abs(x[1]),
                    reverse=True,
                )[:10]
            ),
        }

    return analysis


def analyze_data_dependencies() -> dict:
    """分析数据依赖"""
    deps = {"factor_data": {}, "stock_data": {}, "ic_cache": {}, "index_data": {}}

    # 因子数据
    factors_dir = DATA_ROOT / "parquet" / "factors"
    if factors_dir.exists():
        factor_names = sorted(
            d.name for d in factors_dir.iterdir() if d.is_dir()
        )
        deps["factor_data"]["n_factors"] = len(factor_names)
        deps["factor_data"]["factor_names"] = factor_names

        # 检查年份覆盖
        year_coverage = {}
        for fname in factor_names[:5]:  # 抽样5个
            fdir = factors_dir / fname
            years = sorted(
                d.name.replace("year=", "")
                for d in fdir.iterdir()
                if d.is_dir()
            )
            year_coverage[fname] = years
        deps["factor_data"]["year_coverage_sample"] = year_coverage

        # 总大小估算
        total_size = sum(
            f.stat().st_size
            for f in factors_dir.rglob("*.parquet")
            if f.is_file()
        )
        deps["factor_data"]["total_size_mb"] = round(total_size / 1024 / 1024, 1)

    # 股票数据
    stock_dir = DATA_ROOT / "stock_daily_wide_partitioned"
    if stock_dir.exists():
        years = sorted(
            d.name for d in stock_dir.iterdir() if d.is_dir()
        )
        deps["stock_data"]["years"] = years

    # IC 缓存
    if IC_CACHE.exists():
        df = pl.read_parquet(IC_CACHE)
        deps["ic_cache"]["exists"] = True
        deps["ic_cache"]["shape"] = f"{df.shape[0]} 天 × {df.shape[1]} 列"
        deps["ic_cache"]["n_factors"] = df.shape[1] - 1
        deps["ic_cache"]["date_range"] = (
            f"{df['date'].min()} ~ {df['date'].max()}"
        )
        deps["ic_cache"]["size_mb"] = round(
            IC_CACHE.stat().st_size / 1024 / 1024, 1
        )
        # null 比例（验证 NaN 修复）
        total_cells = df.shape[0] * (df.shape[1] - 1)
        null_cells = sum(
            df[c].null_count() for c in df.columns if c != "date"
        )
        deps["ic_cache"]["null_ratio"] = round(null_cells / total_cells, 4)
    else:
        deps["ic_cache"]["exists"] = False

    # 指数成分数据
    ic_dir = DATA_ROOT / "parquet" / "index_constituents"
    if ic_dir.exists():
        files = list(ic_dir.rglob("*.parquet"))
        deps["index_data"]["n_files"] = len(files)

    return deps


def analyze_model_dependencies() -> dict:
    """分析模型依赖"""
    return {
        "model_type": "LightGBM Regressor (LGBMRegressor)",
        "hyperparameters": {
            "n_estimators": 200,
            "max_depth": 5,
            "learning_rate": 0.05,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "early_stopping_rounds": 20,
            "validation_split": 0.8,
        },
        "training_config": {
            "train_window": "1008 天 (约4年)",
            "retrain_freq": "21 天",
            "target_horizon": "20 天 (预测下月IC)",
            "sample_step": "5 (隔5天采样)",
            "min_samples": 200,
            "n_features": 10,
        },
        "feature_names": [
            "ic_20d", "ic_60d", "ic_120d", "ic_std", "icir",
            "ic_momentum", "crowding",
            "regime_vol_pct", "regime_trend", "regime_momentum",
        ],
        "training_samples_estimate": "~50440 (1008天 × 260因子 / 5步长)",
        "selection_config": {
            "top_k_factors": 25,
            "selection_criteria": "abs(predicted_ic) 降序",
            "stock_selection": "ICIR 加权 + 方向修正",
            "top_n_stocks": 30,
            "max_stock_weight": 0.04,
        },
    }


def analyze_software_dependencies() -> dict:
    """分析软件依赖"""
    import platform

    deps = {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
    }

    packages = ["polars", "numpy", "lightgbm", "scipy", "pydantic"]
    for pkg in packages:
        try:
            mod = __import__(pkg)
            deps[pkg] = getattr(mod, "__version__", "unknown")
        except ImportError:
            deps[pkg] = "NOT INSTALLED"

    # 项目内框架依赖
    deps["framework_modules"] = [
        "ohmyquant.strategy.base.BaseStrategy",
        "ohmyquant.strategy.registry.StrategyRegistry",
        "ohmyquant.strategy.runner.StrategyRunner",
        "ohmyquant.engine.selectors.mlf_selector.MLFSelector",
        "ohmyquant.factors.analysis.FactorAnalyzer",
        "ohmyquant.factors.optimizer.FactorOptimizer",
        "ohmyquant.engine.backtest.BacktestEngine",
    ]

    return deps


def analyze_reproduction_steps() -> list[str]:
    """复现步骤"""
    return [
        "1. 确保 D:/Work/Project/download_a_share/data 下有 260 个 jqdata 因子 (parquet/factors/<NAME>/year=YYYY/data.parquet)，覆盖 2018-2026",
        "2. 确保股票日线数据 (stock_daily_wide_partitioned/year=YYYY/data.parquet) 覆盖 2018-2026",
        "3. 确保沪深300指数成分数据 (parquet/index_constituents/) 存在",
        "4. 安装依赖: pip install polars numpy lightgbm scipy pydantic",
        "5. 首次运行会构建 IC 缓存 (~7分钟), 后续运行从缓存加载 (~1秒)",
        "6. 执行: python scripts/mlf_oos.py",
        "7. 结果输出到 output/oos_2026/mlf_v2/results.json",
        "8. 建仓日 2026-06-01 开盘价建仓, 调仓日 2026-07-01 月度调仓",
    ]


def main():
    print("=" * 70)
    print("mlf_v2 建仓/调仓 持仓依赖包分析")
    print("=" * 70)

    results = load_results()

    print("\n[1] 持仓分析...")
    holdings_analysis = analyze_holdings(results.get("rebalance_log", []))
    for date in sorted(k for k in holdings_analysis if not k.startswith("_")):
        h = holdings_analysis[date]
        print(f"\n  {date}: {h['n_stocks']} 只股票, 总权重 {h['total_weight']:.2%}")
        print(f"    权重范围: [{h['min_weight']:.2%}, {h['max_weight']:.2%}]")
        top5_str = ", ".join(f"{s['code']}:{s['weight']:.2%}" for s in h['top10'][:5])
        print(f"    前5: {top5_str}")

    if "_turnover_analysis" in holdings_analysis:
        ta = holdings_analysis["_turnover_analysis"]
        print(f"\n  换手分析 ({ta['from_date']} → {ta['to_date']}):")
        print(f"    新增: {ta['n_added']} 只, 剔除: {ta['n_removed']} 只")
        print(f"    保留: {ta['n_common']} 只")
        print(f"    单向换手率: {ta['turnover_one_sided']:.2%}")
        if ta["stocks_added"]:
            print(f"    新增股票: {ta['stocks_added']}")
        if ta["stocks_removed"]:
            print(f"    剔除股票: {ta['stocks_removed']}")

    print("\n[2] 数据依赖分析...")
    data_deps = analyze_data_dependencies()
    print(f"  因子数据: {data_deps['factor_data'].get('n_factors', 0)} 个因子")
    print(f"  因子总大小: {data_deps['factor_data'].get('total_size_mb', 0)} MB")
    print(f"  IC 缓存: {data_deps['ic_cache'].get('shape', 'N/A')}")
    print(f"  IC 缓存 null 比例: {data_deps['ic_cache'].get('null_ratio', 'N/A')}")
    print(f"  股票数据年份: {data_deps['stock_data'].get('years', [])}")

    print("\n[3] 模型依赖分析...")
    model_deps = analyze_model_dependencies()
    print(f"  模型: {model_deps['model_type']}")
    print(f"  训练样本: {model_deps['training_samples_estimate']}")
    print(f"  特征数: {len(model_deps['feature_names'])}")
    print(f"  选股: top-{model_deps['selection_config']['top_k_factors']} 因子 → top-{model_deps['selection_config']['top_n_stocks']} 股票")

    print("\n[4] 软件依赖分析...")
    software_deps = analyze_software_dependencies()
    print(f"  Python: {software_deps['python_version']}")
    for pkg in ["polars", "numpy", "lightgbm", "scipy", "pydantic"]:
        print(f"  {pkg}: {software_deps.get(pkg, 'N/A')}")

    print("\n[5] 复现步骤...")
    steps = analyze_reproduction_steps()
    for step in steps:
        print(f"  {step}")

    # 保存完整分析
    full_analysis = {
        "strategy": "mlf_v2",
        "analysis_date": "2026-07-14",
        "holdings": holdings_analysis,
        "data_dependencies": data_deps,
        "model_dependencies": model_deps,
        "software_dependencies": software_deps,
        "reproduction_steps": steps,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(full_analysis, f, indent=2, ensure_ascii=False)
    print(f"\n完整分析已保存: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
