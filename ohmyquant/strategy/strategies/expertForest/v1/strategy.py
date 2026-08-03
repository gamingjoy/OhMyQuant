"""expertForest_v1 多专家树集成学习策略 —— [FINAL]

策略类型: 量化策略(expertForest), 多专家树集成(Multi-Expert Tree Ensemble)
状态: final (IS+OOS双验证, 抗过拟合迭代完成)

核心架构:
  32个差异化专家(RF×ET×LGB×XGB, 无aggressive深树) × Walk Forward周频滚动训练 → rank_average集成 → Top-N选股

抗过拟合改造:
  1. IC计算改80/20 holdout OOF (仅IC-based集成方法, 避免样本内IC泄漏)
  2. 去掉aggressive超参档(深树max_depth=10过拟合), 保留conservative+moderate
  3. 集成方法从ic_rank_weighted改为rank_average (无IC加权, 更鲁棒)

数据: factors_wide(260因子) + stock_daily_wide(衍生因子) + stock_hk_hold(北向资金)
回测: 2023-2025 IS, 20260601+ OOS, 每周调仓, T+1开盘价成交
IS:  Sharpe=1.7552, 超额=+207.48%, 回撤=-32.65%, Calmar=1.4790
OOS: Sharpe=-0.0933, 超额=-0.53%, 回撤=-37.19% (抗过拟合后接近零)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ohmyquant.strategy import register_strategy
from ohmyquant.strategy.base import BaseStrategy


@register_strategy("expertForest", "v1")
class ExpertForestStrategyV1(BaseStrategy):
    """量化策略 expertForest_v1 (meTree32, final)"""

    @classmethod
    def from_version(
        cls, strategy_type: str, version: str, config: dict | None = None
    ) -> "ExpertForestStrategyV1":
        if strategy_type != "expertForest" or version != "v1":
            raise ValueError(f"不支持的策略版本: {strategy_type} {version}")

        config_path = Path(__file__).parent / "config.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            base_config = yaml.safe_load(f)

        if config:
            # 深度合并
            base_config = _deep_merge(base_config, config)

        return cls(base_config)

    def run(self):
        """执行完整回测流程

        Returns:
            dict: {nav, dates, daily_returns, metrics, holdings_log, wf_results}
        """
        import time
        from ohmyquant.data.sources.duckdb_source import DuckDBSource
        from .factor_engine import FactorEngine
        from .expert_pool import build_expert_pool
        from .walk_forward import WalkForwardTrainer
        from .backtest import run_backtest, print_metrics

        t_start = time.time()

        # 1. 初始化数据源
        data_root = self.config.data.data_root
        source = DuckDBSource({"data_root": data_root})

        # 2. 配置
        cfg = self.config.model_dump() if hasattr(self.config, "model_dump") else self.config
        bt_cfg = cfg.get("backtest", {})
        start_date = bt_cfg.get("start_date", "2023-01-01")
        end_date = bt_cfg.get("end_date", "2025-12-31")
        data_start = bt_cfg.get("data_start_date", "2022-01-01")
        pool_index = cfg.get("pools", {}).get("stocks", {}).get("index", "000300.XSHG")

        def _print(*args, **kwargs):
            kwargs.setdefault("flush", True)
            print(*args, **kwargs)

        _print(f"\n{'='*70}")
        _print(f"  expertForest_v1 多专家树集成策略 启动")
        _print(f"{'='*70}")
        _print(f"  回测区间: {start_date} → {end_date}")
        _print(f"  数据起始: {data_start}")
        _print(f"  股票池:   {pool_index}")
        _print(f"  Top-N:    {cfg.get('selection', {}).get('top_n', 10)}")

        # 3. 加载股票池成分股
        _print(f"\n[1/5] 加载股票池 {pool_index}...")
        pool_codes = _load_pool_codes(source, pool_index)
        _print(f"  成分股: {len(pool_codes)} 只")

        # 4. 因子引擎
        _print(f"\n[2/5] 准备因子数据...")
        fe = FactorEngine(source, cfg)
        # 数据需要覆盖训练窗口+回测区间
        fetch_start = min(data_start, start_date)
        fetch_end = end_date
        data = fe.prepare_data(fetch_start, fetch_end, pool_codes)
        _print(f"  因子数: {len(data['factor_names'])}")
        _print(f"  因子数据: {len(data['factor_df'])} 行")
        _print(f"  标签数据: {len(data['label_df'])} 行 (非空)")

        # 5. 构建专家池
        _print(f"\n[3/5] 构建专家池...")
        expert_cfg = cfg.get("expert", {})
        experts = build_expert_pool(
            model_types=expert_cfg.get("model_types"),
            hyper_sets=expert_cfg.get("hyper_sets"),
            feature_sets=expert_cfg.get("feature_sets"),
            train_windows=expert_cfg.get("train_windows"),
        )
        _print(f"  专家数: {len(experts)}")
        for mt in ["rf", "et", "lgb", "xgb"]:
            count = sum(1 for e in experts if e.model_type == mt)
            _print(f"    {mt}: {count} 个")

        # 6. Walk Forward训练
        _print(f"\n[4/5] Walk Forward 滚动训练...")
        trade_cal = source.get_trade_calendar(fetch_start, fetch_end)
        trainer = WalkForwardTrainer(fe, experts, cfg)
        wf_results = trainer.run(data, start_date, end_date, trade_cal)
        _print(f"  完成: {len(wf_results)} 个调仓日")

        # 7. 回测（仅从策略start_date开始，避免数据加载期flat拖累基准对比）
        _print(f"\n[5/5] 回测...")
        bt_trade_cal = [d for d in trade_cal if d >= start_date]
        bench_df = source.load_index_data(
            cfg.get("walk_forward", {}).get("benchmark", "000300.XSHG"),
            start_date, fetch_end
        )
        bt_result = run_backtest(
            wf_results, data["price_df"], bench_df, bt_trade_cal, cfg
        )
        print_metrics(bt_result["metrics"], "expertForest_v1 (meTree32, final)")

        elapsed = time.time() - t_start
        _print(f"\n  总耗时: {elapsed:.0f}s ({elapsed/60:.1f}min)")

        bt_result["wf_results"] = wf_results
        return bt_result


def _load_pool_codes(source, index: str) -> list[str]:
    """加载股票池成分股"""
    if "+" in index:
        # 中证800 = 沪深300 + 中证500
        codes = set()
        for idx in index.split("+"):
            idx = idx.strip()
            constituents = source.load_index_constituents(idx)
            codes.update(constituents)
        return sorted(codes)
    else:
        constituents = source.load_index_constituents(index)
        return sorted(constituents)


def _deep_merge(base: dict, override: dict) -> dict:
    """深度合并两个字典"""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result
