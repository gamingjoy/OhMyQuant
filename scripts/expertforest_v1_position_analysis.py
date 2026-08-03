"""expertForest_v1 建仓+调仓分析与同花顺交易文件生成

从20260601建仓起, 每周一调仓(T+0当天开盘价成交), 生成:
1. 同花顺交易流水xlsx (建仓/调仓, 每次独立文件)
2. 每次调仓详细分析报告 (股票只数/总权重/权重范围/换手率/专家投票详情)
3. 汇总报告

参考: scripts/industry_rotation_daily.py (复用 get_open_prices/generate_trades/write_xlsx/replay_history)
适配: expertForest 的回测输出 wf_results 含 expert_predictions, 用于专家投票分析

注意: 回测引擎 backtest.py 用 T+1 执行(选股日次日开盘价成交); 本脚本按用户要求
      用 T+0 执行(选仓日=周一当天开盘价成交)生成实际交易文件。

用法:
    python scripts/expertforest_v1_position_analysis.py
    python scripts/expertforest_v1_position_analysis.py --end-date 2026-07-20
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np

from ohmyquant.data.sources.duckdb_source import DuckDBSource
from ohmyquant.strategy import StrategyRegistry
from industry_rotation_daily import (
    generate_trades,
    get_open_prices,
    write_xlsx,
    replay_history,
    CAPITAL,
    TRANSACTION_COST_RATE,
)

STRATEGY_NAME = "expertforest_v1"
DATA_ROOT = "D:/Work/Project/download_a_share/data"
OOS_START = "2026-06-01"
DATA_START = "2024-01-01"  # 504日窗口需回溯到2024
OUTPUT_DIR = Path(f"output/ths/{STRATEGY_NAME}")
POOL_INDEX = "000905.XSHG"
TOP_N = 30
MODEL_TYPES = ["rf", "et", "lgb", "xgb"]


# ====================================================================
# 1. 回测
# ====================================================================

def run_oos_backtest(end_date: str) -> dict:
    """运行OOS回测, 返回 wf_results + holdings_log + metrics"""
    print(f"\n运行 expertForest_v1 OOS回测: {OOS_START} -> {end_date}")

    config_override = {
        "pools": {"stocks": {"index": POOL_INDEX}},
        "selection": {"top_n": TOP_N},
        "backtest": {
            "start_date": OOS_START,
            "end_date": end_date,
            "data_start_date": DATA_START,
        },
        "ensemble": {"method": "rank_average"},
    }

    strategy = StrategyRegistry.create("expertForest", "v1", config_override)
    result = strategy.run()

    return {
        "wf_results": result.get("wf_results", []),
        "holdings_log": result.get("holdings_log", []),
        "metrics": result.get("metrics", {}),
    }


# ====================================================================
# 2. 调仓日志构建
# ====================================================================

def build_rebalance_log(wf_results: list[dict]) -> list[dict]:
    """从 wf_results 构建调仓日志

    每个调仓日:
        {date, holdings:{code:1/N}, selected_codes, predictions, expert_predictions}
    holdings 字段兼容 industry_rotation_daily.replay_history 的格式
    """
    rebalance_log = []
    for r in wf_results:
        codes = r.get("selected_codes", [])
        if not codes:
            continue
        weight = 1.0 / len(codes)
        rebalance_log.append({
            "date": r["date"],
            "holdings": {c: weight for c in codes},
            "selected_codes": codes,
            "predictions": r.get("predictions", {}),
            "expert_predictions": r.get("expert_predictions", []),
        })
    return rebalance_log


# ====================================================================
# 3. 专家投票分析
# ====================================================================

def analyze_expert_voting(
    expert_predictions: list[dict], selected_codes: list[str], top_n: int
) -> dict:
    """分析专家投票情况

    对每只选中的股票, 计算:
    - vote_count: 多少专家将其排入个人 top-N
    - vote_pct: vote_count / 专家总数
    - avg_rank: 跨所有专家的归一化平均rank (0-1, 越高越好)
    - model_breakdown: 按模型类型(rf/et/lgb/xgb)的投票统计

    rank 归一化方式与 walk_forward._ensemble_rank_average 一致:
        rankdata(predictions) / N, 越高=预测越好
    """
    from scipy.stats import rankdata

    n_experts = len(expert_predictions)
    if n_experts == 0:
        return {}

    expert_info = []
    for exp in expert_predictions:
        mt = exp.get("model_type", "?")
        preds = exp.get("predictions", {})

        valid = [(c, v) for c, v in preds.items()
                 if v is not None and not (isinstance(v, float) and np.isnan(v))]
        if len(valid) < 2:
            expert_info.append({"type": mt, "top_set": set(), "ranks": {}})
            continue

        values = [v for _, v in valid]
        ranks = rankdata(values) / len(values)  # [1/N, 1.0], 越高=预测越好
        rank_map = {c: r for (c, _), r in zip(valid, ranks)}

        # 按预测值降序取 top-N
        valid.sort(key=lambda x: x[1], reverse=True)
        top_set = set(c for c, _ in valid[:top_n])

        expert_info.append({"type": mt, "top_set": top_set, "ranks": rank_map})

    stock_analysis = {}
    for code in selected_codes:
        vote_count = sum(1 for e in expert_info if code in e["top_set"])
        all_ranks = [e["ranks"][code] for e in expert_info if code in e["ranks"]]

        model_bd = {}
        for mt in MODEL_TYPES:
            mt_experts = [e for e in expert_info if e["type"] == mt]
            mt_vote = sum(1 for e in mt_experts if code in e["top_set"])
            mt_ranks = [e["ranks"][code] for e in mt_experts if code in e["ranks"]]
            model_bd[mt] = {
                "n": len(mt_experts),
                "vote": mt_vote,
                "avg_rank": float(np.mean(mt_ranks)) if mt_ranks else 0.0,
            }

        stock_analysis[code] = {
            "vote_count": vote_count,
            "vote_pct": vote_count / n_experts if n_experts > 0 else 0.0,
            "avg_rank": float(np.mean(all_ranks)) if all_ranks else 0.0,
            "model_breakdown": model_bd,
        }

    return stock_analysis


def compute_turnover(prev_codes: set, new_codes: set) -> float:
    """计算换手率 (与 backtest.py 一致)"""
    bought = new_codes - prev_codes
    sold = prev_codes - new_codes
    return (len(bought) + len(sold)) / max(len(new_codes | prev_codes), 1)


# ====================================================================
# 4. 报告生成
# ====================================================================

def generate_report(
    date_str: str,
    is_build: bool,
    trades: list[dict],
    new_shares: dict[str, int],
    new_cash: float,
    prev_shares: dict[str, int],
    target_holdings: dict[str, float],
    open_prices: dict[str, float],
    predictions: dict[str, float],
    expert_analysis: dict,
    expert_predictions: list[dict],
    industry_map: dict[str, str],
) -> str:
    """生成单次调仓的详细分析报告 (markdown)"""

    dt = datetime.strptime(date_str, "%Y-%m-%d")
    weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][dt.weekday()]
    label = "建仓" if is_build else "调仓"

    n_stocks = len(new_shares)
    weights = list(target_holdings.values())
    total_weight = sum(weights) if weights else 0
    w_min = min(weights) if weights else 0
    w_max = max(weights) if weights else 0
    w_avg = total_weight / len(weights) if weights else 0

    prev_codes = set(prev_shares.keys())
    new_codes = set(new_shares.keys())
    turnover = compute_turnover(prev_codes, new_codes)

    n_experts = len(expert_predictions)

    # 模型类型专家数
    mt_counts = {}
    for exp in expert_predictions:
        mt = exp.get("model_type", "?")
        mt_counts[mt] = mt_counts.get(mt, 0) + 1

    # 持仓市值
    position_value = sum(new_shares.get(c, 0) * open_prices.get(c, 0) for c in new_codes)
    total_assets = position_value + new_cash

    # 缺失价格的股票
    missing = [c for c in target_holdings if c not in open_prices or open_prices.get(c, 0) <= 0]

    lines = []
    lines.append(f"# expertForest_v1 {label}分析报告 - {date_str} ({weekday})")
    lines.append("")
    lines.append(f"> 策略: expertForest_v1 (meTree48, rank_average) | "
                 f"股票池: {POOL_INDEX} (中证500) | Top-{TOP_N}")
    lines.append("")

    # 基本信息
    lines.append("## 基本信息")
    lines.append("")
    lines.append("| 项目 | 值 |")
    lines.append("|------|------|")
    lines.append(f"| 调仓日期 | {date_str} ({weekday}) |")
    lines.append(f"| 调仓类型 | **{label}** |")
    lines.append(f"| 目标股票数 | {len(target_holdings)} |")
    lines.append(f"| 实际持仓数 | {n_stocks} |")
    lines.append(f"| 总权重 | {total_weight:.2%} |")
    lines.append(f"| 权重范围 | {w_min:.2%} ~ {w_max:.2%} (等权 {w_avg:.2%}) |")
    lines.append(f"| 换手率 | {turnover:.2%} |")
    lines.append(f"| 持仓市值 | {position_value:,.0f} |")
    lines.append(f"| 现金余额 | {new_cash:,.0f} |")
    lines.append(f"| 总资产 | {total_assets:,.0f} (初始 {CAPITAL:,}) |")
    lines.append(f"| 参与专家数 | {n_experts} "
                 f"(RF={mt_counts.get('rf',0)} ET={mt_counts.get('et',0)} "
                 f"LGB={mt_counts.get('lgb',0)} XGB={mt_counts.get('xgb',0)}) |")
    if missing:
        lines.append(f"| 开盘价缺失 | {', '.join(missing)} (已跳过) |")
    lines.append("")

    # 交易摘要
    buy_trades = [t for t in trades if t["业务类型"] == "买入"]
    sell_trades = [t for t in trades if t["业务类型"] == "卖出"]
    total_buy = sum(t["成交金额"] for t in buy_trades)
    total_sell = sum(t["成交金额"] for t in sell_trades)
    total_cost = sum(t["费用"] for t in trades)

    lines.append("## 交易摘要")
    lines.append("")
    lines.append("| 项目 | 值 |")
    lines.append("|------|------|")
    lines.append(f"| 买入笔数 | {len(buy_trades)} |")
    lines.append(f"| 卖出笔数 | {len(sell_trades)} |")
    lines.append(f"| 买入金额 | {total_buy:,.0f} |")
    lines.append(f"| 卖出金额 | {total_sell:,.0f} |")
    lines.append(f"| 交易费用 | {total_cost:,.0f} (费率 {TRANSACTION_COST_RATE:.2%}) |")
    lines.append("")

    # 持仓明细
    lines.append("## 持仓明细")
    lines.append("")
    lines.append("| # | 证券代码 | 行业 | 权重 | rank得分 | 开盘价 | 持仓股数 | 市值 | 专家投票 | 投票率 |")
    lines.append("|---|----------|------|------|----------|--------|----------|------|----------|--------|")

    sorted_codes = sorted(new_shares.keys(), key=lambda c: predictions.get(c, 0), reverse=True)
    for i, code in enumerate(sorted_codes, 1):
        weight = target_holdings.get(code, 0)
        score = predictions.get(code, 0)
        price = open_prices.get(code, 0)
        shares = new_shares.get(code, 0)
        value = shares * price
        ind = industry_map.get(code, "-")
        va = expert_analysis.get(code, {})
        vote = va.get("vote_count", 0)
        vote_pct = va.get("vote_pct", 0)
        lines.append(
            f"| {i} | {code} | {ind} | {weight:.2%} | {score:.4f} | "
            f"{price:.2f} | {shares} | {value:,.0f} | {vote}/{n_experts} | {vote_pct:.1%} |"
        )
    lines.append("")

    # 专家投票详情
    lines.append("## 专家投票详情")
    lines.append("")
    lines.append(f"> 集成方法: rank_average — 48专家各自对全池~500只股票排名, "
                 f"取归一化rank[0-1]平均, 选top-{TOP_N}")
    lines.append(f"> \"投票\" = 该专家将此股排入其个人top-{TOP_N}; "
                 f"投票率 = 投票专家数 / {n_experts}")
    lines.append("")

    # 按模型类型汇总
    lines.append("### 按模型类型汇总 (选中股票的平均投票情况)")
    lines.append("")
    lines.append("| 模型类型 | 专家数 | 平均投票率 | 平均rank |")
    lines.append("|----------|--------|------------|----------|")

    for mt in MODEL_TYPES:
        mt_label = mt.upper()
        n_mt = mt_counts.get(mt, 0)
        mt_vote_pcts = []
        mt_ranks = []
        for code in new_codes:
            bd = expert_analysis.get(code, {}).get("model_breakdown", {}).get(mt, {})
            if bd.get("n", 0) > 0:
                mt_vote_pcts.append(bd.get("vote", 0) / bd["n"])
                mt_ranks.append(bd.get("avg_rank", 0))
        avg_vote = float(np.mean(mt_vote_pcts)) if mt_vote_pcts else 0
        avg_rank = float(np.mean(mt_ranks)) if mt_ranks else 0
        lines.append(f"| {mt_label} | {n_mt} | {avg_vote:.1%} | {avg_rank:.4f} |")
    lines.append("")

    # 每只股票的专家投票
    lines.append("### 每只股票的专家投票 (按rank得分降序)")
    lines.append("")
    lines.append("| # | 证券代码 | 投票 | 投票率 | 平均rank | RF | ET | LGB | XGB |")
    lines.append("|---|----------|------|--------|----------|----|----|-----|-----|")

    for i, code in enumerate(sorted_codes, 1):
        va = expert_analysis.get(code, {})
        vote = va.get("vote_count", 0)
        vote_pct = va.get("vote_pct", 0)
        avg_rank = va.get("avg_rank", 0)
        bd = va.get("model_breakdown", {})

        def _fmt(mt_key):
            d = bd.get(mt_key, {})
            return f"{d.get('vote', 0)}/{d.get('n', 0)}"

        lines.append(
            f"| {i} | {code} | {vote}/{n_experts} | {vote_pct:.1%} | {avg_rank:.4f} | "
            f"{_fmt('rf')} | {_fmt('et')} | {_fmt('lgb')} | {_fmt('xgb')} |"
        )
    lines.append("")

    # 选股逻辑
    lines.append("## 选股逻辑")
    lines.append("")
    lines.append(
        f"expertForest_v1 使用 **48个差异化专家树** "
        f"(RF x ET x LGB x XGB, 每类各12个: conservative/moderate超参 x "
        f"momentum/fundamental/sentiment特征 x 252/504日窗口) "
        f"对中证500成分股进行5日前向超额收益预测。"
    )
    lines.append("")
    lines.append(
        f"**集成方法**: rank_average — 每个专家对全池~500只股票输出预测值, "
        f"转为归一化rank[0-1]后简单平均, 选top-{TOP_N}等权配置。"
    )
    lines.append("")
    lines.append(
        f"**选股标准**: rank平均得分最高的{TOP_N}只股票。"
        f"高投票率表示专家共识强(多数专家都看好); "
        f"低投票率但高rank得分表示部分专家强烈看好(集中度高)。"
    )
    lines.append("")

    # 交易明细
    lines.append("## 交易明细")
    lines.append("")
    lines.append("| 业务类型 | 证券代码 | 数量 | 价格 | 成交金额 | 费用 | 说明 |")
    lines.append("|----------|----------|------|------|----------|------|------|")
    for t in trades:
        lines.append(
            f"| {t['业务类型']} | {t['证券代码']} | {t['数量']} | "
            f"{t['价格']:.2f} | {t['成交金额']:,.0f} | {t['费用']:.2f} | {t['说明']} |"
        )
    lines.append("")

    return "\n".join(lines)


def generate_summary_report(
    summaries: list[dict], metrics: dict, end_date: str, elapsed: float
) -> str:
    """生成汇总报告"""
    lines = []
    lines.append("# expertForest_v1 建仓调仓汇总报告")
    lines.append("")
    lines.append(f"> 策略: expertForest_v1 (meTree48, rank_average, final v2)")
    lines.append(f"> 股票池: {POOL_INDEX} (中证500) | Top-{TOP_N} | 每周周一调仓")
    lines.append(f"> OOS区间: {OOS_START} -> {end_date}")
    lines.append(f"> 初始资金: {CAPITAL:,} | 交易费率: {TRANSACTION_COST_RATE:.2%}")
    lines.append("")

    # OOS绩效
    lines.append("## OOS 绩效")
    lines.append("")
    lines.append("| 指标 | 值 |")
    lines.append("|------|------|")
    lines.append(f"| 交易日数 | {metrics.get('n_days', 0)} |")
    lines.append(f"| 最终净值 | {metrics.get('final_nav', 0):.4f} |")
    lines.append(f"| 累计收益 | {metrics.get('total_return', 0):+.2%} |")
    lines.append(f"| 超额收益 | {metrics.get('excess_return', 0):+.2%} |")
    lines.append(f"| Sharpe | {metrics.get('sharpe', 0):.4f} |")
    lines.append(f"| 最大回撤 | {metrics.get('max_drawdown', 0):+.2%} |")
    lines.append(f"| 超额IR | {metrics.get('information_ratio', 0):.4f} |")
    lines.append("")

    # 调仓记录
    lines.append("## 调仓记录")
    lines.append("")
    lines.append("| # | 日期 | 类型 | 持仓 | 买 | 卖 | 换手率 | 平均投票率 | 现金 |")
    lines.append("|---|------|------|------|----|----|--------|-----------|------|")
    for i, s in enumerate(summaries, 1):
        lines.append(
            f"| {i} | {s['date']} | {s['type']} | {s['n_stocks']} | "
            f"{s['buy']} | {s['sell']} | {s['turnover']:.1%} | "
            f"{s['avg_vote_pct']:.1%} | {s['cash']:,.0f} |"
        )
    lines.append("")

    # 统计
    if summaries:
        non_build = [s for s in summaries if s["type"] != "建仓"]
        avg_turnover = float(np.mean([s["turnover"] for s in non_build])) if non_build else 0
        avg_vote = float(np.mean([s["avg_vote_pct"] for s in summaries]))
        lines.append("## 统计")
        lines.append("")
        lines.append("| 项目 | 值 |")
        lines.append("|------|------|")
        lines.append(f"| 调仓总次数 | {len(summaries)} |")
        lines.append(f"| 建仓次数 | {sum(1 for s in summaries if s['type'] == '建仓')} |")
        lines.append(f"| 调仓次数(非建仓) | {len(non_build)} |")
        lines.append(f"| 平均换手率(非建仓) | {avg_turnover:.1%} |")
        lines.append(f"| 平均专家投票率 | {avg_vote:.1%} |")
        lines.append(f"| 回测耗时 | {elapsed:.0f}s ({elapsed/60:.1f}min) |")
        lines.append("")

    lines.append("## 文件说明")
    lines.append("")
    lines.append("- `{YYYYMMDD}_build.xlsx` / `{YYYYMMDD}_rebalance.xlsx`: 同花顺交易流水")
    lines.append("- `{YYYYMMDD}_build_report.md` / `{YYYYMMDD}_rebalance_report.md`: 单次调仓详细分析")
    lines.append("- `summary.md`: 本汇总报告")
    lines.append("")

    return "\n".join(lines)


# ====================================================================
# 5. 主流程
# ====================================================================

def main():
    parser = argparse.ArgumentParser(description="expertForest_v1 建仓+调仓分析")
    parser.add_argument("--end-date", default=None,
                        help="回测结束日期(YYYY-MM-DD), 默认用最新数据日")
    args = parser.parse_args()

    source = DuckDBSource({"data_root": DATA_ROOT})

    # 1. 确定回测结束日期
    if args.end_date:
        end_date = args.end_date
    else:
        end_date = source.get_latest_date()
    print(f"策略: {STRATEGY_NAME}")
    print(f"OOS区间: {OOS_START} -> {end_date}")
    print("=" * 60)

    # 2. 运行OOS回测
    t0 = time.time()
    result = run_oos_backtest(end_date)
    elapsed = time.time() - t0
    print(f"\n回测耗时: {elapsed:.0f}s ({elapsed/60:.1f}min)")

    wf_results = result["wf_results"]
    metrics = result["metrics"]
    rebalance_log = build_rebalance_log(wf_results)

    print(f"调仓日数: {len(rebalance_log)}")
    print(f"OOS Sharpe: {metrics.get('sharpe', 0):.4f}")
    print(f"OOS超额收益: {metrics.get('excess_return', 0):+.2%}")

    if not rebalance_log:
        print("无调仓记录, 退出")
        return

    # 3. 加载行业映射 (可选, 失败不影响主流程)
    try:
        industry_map = source.load_industry_map()
    except Exception:
        industry_map = {}

    # 4. 准备输出目录
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 5. 遍历每个调仓日, 生成xlsx + 报告
    print(f"\n{'日期':<12} {'类型':<6} {'买':<4} {'卖':<4} {'持仓':<4} {'换手率':>8} {'现金':>14}")
    print("-" * 65)

    all_summaries = []

    for i, entry in enumerate(rebalance_log):
        date_str = entry["date"]
        holdings = entry["holdings"]
        selected_codes = entry["selected_codes"]
        predictions = entry["predictions"]
        expert_predictions = entry["expert_predictions"]

        # 回放历史重建持仓
        prev_shares, prev_cash = replay_history(
            source, rebalance_log, date_str, strategy_name=STRATEGY_NAME
        )
        is_build = (len(prev_shares) == 0)

        # 获取开盘价 (当前持仓 + 目标持仓)
        all_codes = list(set(list(prev_shares.keys()) + list(holdings.keys())))
        open_prices = get_open_prices(source, all_codes, date_str) if all_codes else {}

        # 生成交易
        trades, new_shares, new_cash = generate_trades(
            date_str, prev_shares, holdings, open_prices, prev_cash, is_build,
            strategy_name=STRATEGY_NAME,
        )

        # 专家投票分析
        expert_analysis = analyze_expert_voting(expert_predictions, selected_codes, TOP_N)

        # 换手率
        prev_codes = set(prev_shares.keys())
        new_codes = set(new_shares.keys())
        turnover = compute_turnover(prev_codes, new_codes)

        # 写xlsx
        date_tag = date_str.replace("-", "")
        xlsx_name = (f"{date_tag}_build.xlsx" if is_build
                     else f"{date_tag}_rebalance.xlsx")
        xlsx_path = OUTPUT_DIR / xlsx_name
        if trades:
            write_xlsx(trades, xlsx_path)

        # 生成报告
        report = generate_report(
            date_str, is_build, trades, new_shares, new_cash, prev_shares,
            holdings, open_prices, predictions, expert_analysis,
            expert_predictions, industry_map,
        )
        report_path = OUTPUT_DIR / xlsx_name.replace(".xlsx", "_report.md")
        report_path.write_text(report, encoding="utf-8")

        # 打印摘要
        buy_count = sum(1 for t in trades if t["业务类型"] == "买入")
        sell_count = sum(1 for t in trades if t["业务类型"] == "卖出")
        label = "建仓" if is_build else "调仓"
        avg_vote = (float(np.mean([v["vote_pct"] for v in expert_analysis.values()]))
                    if expert_analysis else 0)
        print(f"{date_str:<12} {label:<6} {buy_count:<4} {sell_count:<4} "
              f"{len(new_shares):<4} {turnover:>7.1%} {new_cash:>14,.0f}")

        all_summaries.append({
            "date": date_str,
            "type": label,
            "n_stocks": len(new_shares),
            "buy": buy_count,
            "sell": sell_count,
            "turnover": turnover,
            "cash": new_cash,
            "n_experts": len(expert_predictions),
            "avg_vote_pct": avg_vote,
        })

    # 6. 生成汇总报告
    summary = generate_summary_report(all_summaries, metrics, end_date, elapsed)
    summary_path = OUTPUT_DIR / "summary.md"
    summary_path.write_text(summary, encoding="utf-8")

    print(f"\n文件已生成到: {OUTPUT_DIR}")
    print(f"汇总报告: {summary_path}")
    n_xlsx = len(list(OUTPUT_DIR.glob("*.xlsx")))
    n_reports = len(list(OUTPUT_DIR.glob("*_report.md")))
    print(f"共 {n_xlsx} 个xlsx + {n_reports} 个调仓报告 + 1 个汇总")


if __name__ == "__main__":
    main()
