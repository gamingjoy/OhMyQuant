"""快速 Walk-Forward 分析：从已保存的 daily_returns 切分年度窗口评估跨周期稳定性

比 StrategyWalkForward 快 10x+（无需重跑回测），适合快速验证策略稳健性。
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from ohmyquant.analysis.metrics import compute_metrics

strategies = {
    "dl_v1": "output/dl_v1/results.json",
    "ycj_v1": "output/ycj_v1/results.json",
    "rl_v1": "output/rl_v1/results.json",
    "etf_v3": "output/etf_v3/results.json",
}

for name, path in strategies.items():
    if not os.path.exists(path):
        print(f"跳过 {name}: 文件不存在 {path}")
        continue

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    returns = np.array(data.get("daily_returns", []))
    if len(returns) == 0:
        print(f"跳过 {name}: 无 daily_returns")
        continue

    n_days = len(returns)
    window_size = 242  # ~1 trading year
    step = 242

    print("=" * 80)
    print(f"Walk-Forward 分析: {name} ({n_days} 天)")
    print("=" * 80)

    sharpes = []
    ann_rets = []
    max_dds = []

    win_idx = 0
    idx = 0
    while idx < n_days:
        end_idx = min(idx + window_size, n_days)
        if end_idx - idx < 42:
            break

        window_returns = returns[idx:end_idx]
        m = compute_metrics(window_returns)

        start_year = 2015 + idx // 242
        end_year = 2015 + end_idx // 242
        period = f"{start_year}~{end_year}" if start_year != end_year else f"{start_year}"

        print(
            f"  [{win_idx}] {period:>10s} ({end_idx-idx:>3d}d) "
            f"sharpe={m.sharpe_ratio:>7.4f} "
            f"ann_ret={m.annualized_return:>7.2%} "
            f"max_dd={m.max_drawdown:>8.2%} "
            f"win_rate={m.win_rate:>6.2%}"
        )

        sharpes.append(m.sharpe_ratio)
        ann_rets.append(m.annualized_return)
        max_dds.append(m.max_drawdown)
        win_idx += 1
        idx += step

    sharpes = np.array(sharpes)
    ann_rets = np.array(ann_rets)

    print("-" * 80)
    print(
        f"  平均 Sharpe:     {sharpes.mean():>7.4f}  (std={sharpes.std(ddof=1) if len(sharpes) > 1 else 0:.4f})\n"
        f"  平均年化收益:    {ann_rets.mean():>7.2%}  (std={ann_rets.std(ddof=1) if len(ann_rets) > 1 else 0:.2%})\n"
        f"  正 Sharpe 窗口:  {(sharpes > 0).sum()}/{len(sharpes)}  "
        f"(consistency={(sharpes > 0).sum() / len(sharpes):.1%})\n"
        f"  最差窗口 Sharpe: {sharpes.min():>7.4f}\n"
        f"  最大回撤范围:    {min(max_dds):.2%} ~ {max(max_dds):.2%}"
    )
    print()
