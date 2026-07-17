"""行业轮动策略 IS 网格搜索

系统搜索大盘过滤参数和波动率目标的最优组合。
基于 v4 配置（60+120日动量，Top5行业×2股），搜索：
  - market_ma_short: [5, 10, 15]
  - market_ma_long: [10, 20, 30]
  - target_vol: [0.10, 0.12, 0.15]

共 27 个组合，选取 IS Sharpe 最高的作为 v5 配置。

运行:
    python archive/scripts/industry_rotation_v4_gridsearch.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from ohmyquant.strategy import StrategyRegistry, StrategyRunner


# 网格搜索组合
GRID = {
    "market_ma_short": [5, 10, 15],
    "market_ma_long": [10, 20, 30],
    "target_vol": [0.10, 0.12, 0.15],
}


def run_combo(ma_short: int, ma_long: int, target_vol: float) -> dict:
    """运行单个组合"""
    label = f"ma{ma_short}_{ma_long}_vol{target_vol:.2f}"
    config_override = {
        "selection": {
            "industry_rotation": {
                "market_ma_short": ma_short,
                "market_ma_long": ma_long,
            }
        },
        "risk": {
            "target_vol": target_vol,
        },
    }

    strategy = StrategyRegistry.create("industry_rotation", "v4", config_override)
    runner = StrategyRunner(strategy.config)
    result = runner.run()

    bt = result.backtest_result
    nav = bt.nav
    daily_returns = bt.daily_returns

    n_days = len(nav)
    final_nav = float(nav[-1]) if n_days > 0 else 1.0
    total_return = final_nav - 1.0
    annualized_return = (final_nav ** (242.0 / max(n_days, 1))) - 1.0

    rets = daily_returns.to_numpy()
    rets = rets[~np.isnan(rets)]
    sharpe = (
        float(np.mean(rets) / np.std(rets, ddof=1) * np.sqrt(242))
        if len(rets) > 1 and np.std(rets, ddof=1) > 0
        else 0.0
    )

    nav_arr = nav.to_numpy()
    peak = np.maximum.accumulate(nav_arr)
    drawdown = (nav_arr - peak) / peak
    max_drawdown = float(np.min(drawdown))
    win_rate = float(np.mean(rets > 0)) if len(rets) > 0 else 0.0

    # Calmar 比率（年化收益/最大回撤）
    calmar = (
        abs(annualized_return / max_drawdown) if max_drawdown < 0 else 0.0
    )

    return {
        "label": label,
        "market_ma_short": ma_short,
        "market_ma_long": ma_long,
        "target_vol": target_vol,
        "final_nav": final_nav,
        "total_return": total_return,
        "annualized_return": annualized_return,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "calmar": calmar,
    }


def main():
    print("=" * 80)
    print("行业轮动策略 IS 网格搜索")
    print("=" * 80)
    print(f"基础配置: v4 (60+120日动量, Top5行业×2股, 沪深300)")
    print(f"搜索维度: market_ma_short, market_ma_long, target_vol")
    print()

    results = []
    total = (
        len(GRID["market_ma_short"])
        * len(GRID["market_ma_long"])
        * len(GRID["target_vol"])
    )
    idx = 0

    for ma_short in GRID["market_ma_short"]:
        for ma_long in GRID["market_ma_long"]:
            if ma_long <= ma_short:
                continue  # 跳过无效组合
            for target_vol in GRID["target_vol"]:
                idx += 1
                print(f"[{idx}/{total}] ma_short={ma_short}, ma_long={ma_long}, vol={target_vol}")
                try:
                    r = run_combo(ma_short, ma_long, target_vol)
                    results.append(r)
                    print(
                        f"  → 收益={r['total_return']*100:+.2f}%, "
                        f"Sharpe={r['sharpe_ratio']:.4f}, "
                        f"回撤={r['max_drawdown']*100:.2f}%, "
                        f"Calmar={r['calmar']:.4f}"
                    )
                except Exception as e:
                    print(f"  → 失败: {e}")
                print()

    # 按 Sharpe 排序
    results.sort(key=lambda x: x["sharpe_ratio"], reverse=True)

    print("=" * 80)
    print("网格搜索结果（按 Sharpe 降序）:")
    print("=" * 80)
    print(
        f"{'组合':<20} {'总收益':>10} {'年化':>10} {'Sharpe':>8} "
        f"{'最大回撤':>10} {'Calmar':>8} {'胜率':>8}"
    )
    print("-" * 80)
    for r in results:
        print(
            f"{r['label']:<20} "
            f"{r['total_return']*100:>+9.2f}% "
            f"{r['annualized_return']*100:>+9.2f}% "
            f"{r['sharpe_ratio']:>8.4f} "
            f"{r['max_drawdown']*100:>+9.2f}% "
            f"{r['calmar']:>8.4f} "
            f"{r['win_rate']*100:>7.2f}%"
        )

    # 按 Calmar 排序（兼顾收益和回撤）
    results_calmar = sorted(results, key=lambda x: x["calmar"], reverse=True)
    print()
    print("=" * 80)
    print("网格搜索结果（按 Calmar 降序，兼顾收益与回撤）:")
    print("=" * 80)
    for r in results_calmar[:5]:
        print(
            f"{r['label']:<20} "
            f"Sharpe={r['sharpe_ratio']:.4f} "
            f"回撤={r['max_drawdown']*100:.2f}% "
            f"Calmar={r['calmar']:.4f} "
            f"收益={r['total_return']*100:+.2f}%"
        )

    # 保存结果
    output_dir = Path("output/is_compare/ind")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "gridsearch.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n结果已保存: {output_file}")


if __name__ == "__main__":
    main()
