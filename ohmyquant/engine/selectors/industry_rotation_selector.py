"""行业轮动选股器

基于行业动量进行行业轮动，在强势行业中选强势个股。
适用于沪深300等大盘股池的行业轮动策略。

selection:
  method: industry_rotation    # 使用此选股器
  top_n: 10                  # 最终选股数量
  max_stock_weight: 0.10     # 单股上限
  ind:
    data_root: "..."         # 数据根目录(加载行业映射)
    top_industries: 5        # 选 Top-N 行业
    stocks_per_industry: 2   # 每行业选 M 只
    momentum_short: 20       # 短期动量窗口（行业排名用）
    momentum_long: 60        # 长期动量窗口（行业排名用）
    weight_short: 0.6        # 短期动量权重
    weight_long: 0.4         # 长期动量权重
    max_industry_weight: 0.30  # 单行业权重上限
    market_filter: true      # 大盘趋势过滤
    market_index: "000300.XSHG"  # 大盘指数
    market_ma_short: 20      # 短期均线
    market_ma_long: 60       # 长期均线
    # 多因子选股（可选，启用后个股层用因子评分替代动量）
    use_factors: false       # 是否启用多因子选股
    factor_names: [...]      # 因子名列表
    factor_weights: {...}    # 因子权重（按因子名）
    # ML选股（可选，启用后个股层用LightGBM预测收益替代因子评分）
    use_ml: false            # 是否启用ML选股
    ml_train_window: 252     # 训练窗口（天）
    ml_retrain_freq: 21      # 重训练频率（天）
    ml_target_horizon: 20    # 预测目标horizon（天）
    ml_n_estimators: 150     # LightGBM 树数
    ml_max_depth: 3          # 最大深度
    ml_learning_rate: 0.05   # 学习率
"""
from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl

from ...core.logging import get_logger
from ...core.plugin_system import register_selector
from ..selector import BaseSelector
import os

logger = get_logger(__name__)


@register_selector("industry_rotation")
class IndustryRotationSelector(BaseSelector):
    """行业轮动选股器

    流程:
      1. 惰性加载行业映射 {code: sw_l1_name}
      2. 用 close 计算短期/长期动量 → 行业综合动量排名
      3. 选 Top-N 行业
      4. 每个选中行业内选 Top-M 只股票:
         - use_factors=false: 按个股动量排序
         - use_factors=true: 按多因子复合评分排序（预计算260因子）
      5. 等权配置，应用个股权重上限
      6. (可选)大盘趋势过滤：跌破短期均线降仓50%，跌破长期均线空仓
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        ir_cfg = self.config.get("industry_rotation", {})
        self.data_root = ir_cfg.get(
            "data_root", os.getenv("DATA_ROOT", "data")
        )
        self.top_industries: int = ir_cfg.get("top_industries", 5)
        self.stocks_per_industry: int = ir_cfg.get("stocks_per_industry", 2)
        self.momentum_short: int = ir_cfg.get("momentum_short", 20)
        self.momentum_long: int = ir_cfg.get("momentum_long", 60)
        self.weight_short: float = ir_cfg.get("weight_short", 0.6)
        self.weight_long: float = ir_cfg.get("weight_long", 0.4)
        self.max_industry_weight: float = ir_cfg.get("max_industry_weight", 0.30)
        # 行业短期风险过滤：剔除近期下跌的行业（规避高风险板块）
        self.industry_risk_filter: bool = ir_cfg.get("industry_risk_filter", False)
        self.risk_filter_window: int = ir_cfg.get("risk_filter_window", 20)
        self.risk_filter_min_industries: int = ir_cfg.get(
            "risk_filter_min_industries", 3
        )
        # 大盘趋势过滤
        self.market_filter: bool = ir_cfg.get("market_filter", False)
        self.market_index: str = ir_cfg.get("market_index", "000300.XSHG")
        self.market_ma_short: int = ir_cfg.get("market_ma_short", 20)
        self.market_ma_long: int = ir_cfg.get("market_ma_long", 60)
        # 选股层二值化（v62+）：market_scale 只返回 0.0（空仓）或 1.0（不空仓）
        # 仓位幅度交给风控层统一管理，避免选股层与风控层双重减仓
        self.market_filter_binary: bool = ir_cfg.get("market_filter_binary", False)
        # 绝对动量（Dual Momentum）：近期收益为负时降仓，参考 Antonacci 双动量
        self.absolute_momentum: bool = ir_cfg.get("absolute_momentum", False)
        self.absolute_momentum_window: int = ir_cfg.get(
            "absolute_momentum_window", 20
        )
        self.absolute_momentum_threshold: float = ir_cfg.get(
            "absolute_momentum_threshold", 0.0
        )
        self.absolute_momentum_scale: float = ir_cfg.get(
            "absolute_momentum_scale", 0.3
        )
        # 逆波动率加权（风险平价）：替代等权，降低高波动股权重
        self.use_inv_vol_weight: bool = ir_cfg.get("use_inv_vol_weight", False)
        self.inv_vol_window: int = ir_cfg.get("inv_vol_window", 20)
        # RRG 框架（Relative Rotation Graph）：用相对强度替代绝对动量选行业
        # RS-Ratio = RS / SMA(RS, N) × 100，>100 表示行业长期跑赢大盘
        # RS-Momentum = RS-Ratio 的 M 日动量 × 100，>100 表示相对强度在加速
        # 研报参考：2026 量化轮动策略报告（RRG 框架下行业轮动），年化18.34%, Sharpe 0.72
        # 核心价值：RS-Momentum 是先行指标，能在行业还领先时发出转弱预警
        self.use_rrg: bool = ir_cfg.get("use_rrg", False)
        self.rs_ratio_window: int = ir_cfg.get("rs_ratio_window", 220)
        self.rs_momentum_window: int = ir_cfg.get("rs_momentum_window", 60)
        self.rrg_momentum_threshold: float = ir_cfg.get(
            "rrg_momentum_threshold", 100.0
        )  # RS-Momentum >= 100 表示相对强度在加速
        self.rrg_min_industries: int = ir_cfg.get("rrg_min_industries", 3)
        # 多周期 RRG 投票（NEW in v14, 降低单周期过拟合）
        # 研报参考：v9稳健性分析建议多周期RRG组合(10/30/60日投票)
        # 当 rs_momentum_windows 设置多个值时，启用多周期投票模式：
        #   - 计算每个窗口的 RS-Mom
        #   - 行业入选需 >= vote_threshold 个窗口的 RS-Mom >= 阈值
        # 当 rs_momentum_windows 为空或单值时，回退到单周期模式（向后兼容）
        self.rs_momentum_windows: list[int] = ir_cfg.get(
            "rs_momentum_windows", []
        )  # 多周期RS-Mom窗口列表，如 [10, 30, 60]
        self.rs_momentum_vote_threshold: int = ir_cfg.get(
            "rs_momentum_vote_threshold", 2
        )  # 多周期投票阈值，>=threshold个窗口领先才算领先
        # 多周期RRG加权投票（NEW v40: 权重优化）
        # v30等权投票：vote_count = (RS-Mom_10≥100) + (RS-Mom_30≥100) + (RS-Mom_60≥100)
        # v40加权投票：weighted_vote = sum(w_i * (RS-Mom_i≥100))，阈值改为0.5
        # 当 rs_momentum_vote_weights 为空时，保持等权投票（向后兼容）
        # 当 rs_momentum_vote_weights 非空时，启用加权投票
        # 典型权重：[0.5, 0.3, 0.2]（短期权重更高，反映动量时效性）
        self.rs_momentum_vote_weights: list[float] = ir_cfg.get(
            "rs_momentum_vote_weights", []
        )  # 多周期投票权重，如 [0.5, 0.3, 0.2]
        # 残差动量（Residual Momentum, 华泰金工）
        # 核心：剔除市场Beta暴露后的特异性动量
        # residual_return_N = stock_return_N - raw_beta * market_return_N
        # 研报参考：华泰金工《残差动量行业轮动》年化超额12.90%
        # 优点：剔除市场Beta后，更能反映股票/行业自身的强势，避免高Beta股虚假动量
        # 实现要点：用预计算的 raw_beta 因子做正交化
        self.use_residual_momentum: bool = ir_cfg.get("use_residual_momentum", False)
        self.residual_beta_factor: str = ir_cfg.get(
            "residual_beta_factor", "raw_beta"
        )  # 用作Beta的因子名
        self.residual_beta_default: float = ir_cfg.get(
            "residual_beta_default", 1.0
        )  # Beta缺失时的默认值
        # 拥挤度过滤（Crowding Filter, 华泰金工+西南证券）
        # 核心：高拥挤行业（量价极度活跃）容易发生动量崩盘，应剔除或切换到反转
        # 研报参考：
        #   - 华泰金工《行业拥挤度4指标模型》：4个量价指标95%分位触发，3-4个触发=高拥挤
        #   - 西南证券《拥挤度动态分域》：非拥挤用动量、高拥挤用反转
        # 实现：3个指标（VOL20/turnover_volatility/Skewness20）取近250日95%分位
        #       >=2个触发=高拥挤，剔除该行业
        self.use_crowding_filter: bool = ir_cfg.get("use_crowding_filter", False)
        self.crowding_window: int = ir_cfg.get(
            "crowding_window", 250
        )  # 拥挤度分位回看窗口
        self.crowding_threshold: float = ir_cfg.get(
            "crowding_threshold", 0.95
        )  # 95%分位触发
        self.crowding_min_triggers: int = ir_cfg.get(
            "crowding_min_triggers", 2
        )  # 至少2个指标触发=高拥挤
        self.crowding_min_industries: int = ir_cfg.get(
            "crowding_min_industries", 3
        )  # 至少保留N个行业
        self.crowding_factors: list[str] = ir_cfg.get(
            "crowding_factors",
            ["VOL20", "turnover_volatility", "Skewness20"],
        )  # 拥挤度指标因子名
        # 拥挤度动态分域（NEW v16: 西南证券思路）
        # 核心：高拥挤行业用反转(均值回归)，非拥挤行业用动量(趋势跟踪)
        # 研报参考：西南证券《拥挤度动态分域》
        #   - 非拥挤行业：动量效应显著 → 用动量策略
        #   - 高拥挤行业：反转效应显著 → 用反转策略
        # 实现：对高拥挤行业的股票，反转其评分符号（-score），选"输家"期望反弹
        # 与 use_crowding_filter 互斥：filter剔除高拥挤，reversal保留并用反转
        self.use_crowding_reversal: bool = ir_cfg.get(
            "use_crowding_reversal", False
        )
        # 拥挤度动态分域反转因子（NEW v38: 修正v16失败实现）
        # v16失败根因：对高拥挤行业股票评分取负号(-score)，原评分基于12因子(含质量/价值)，
        #             取负号相当于选"质量差+估值贵"股票，与原框架冲突。
        # v38正确实现：对高拥挤行业的股票，使用独立反转因子(如BIAS20)单独评分替换原评分。
        #             BIAS20 = (close - MA20) / MA20 × 100，低BIAS20=价格远低于均线=反弹潜力大。
        # 与 use_crowding_reversal 互斥：v16是符号反转(失败)，v38是独立因子替换(正确)
        self.use_crowding_reversal_factor: bool = ir_cfg.get(
            "use_crowding_reversal_factor", False
        )
        self.crowding_reversal_factor: str = ir_cfg.get(
            "crowding_reversal_factor", "BIAS20"
        )  # 用作反转代理的因子（低值=超跌=反弹潜力大）
        self.crowding_reversal_direction: int = ir_cfg.get(
            "crowding_reversal_direction", -1
        )  # -1=反向(低BIAS20得高分), 1=正向
        # 行业估值过滤（PE Filter, 华商基金估值安全边际思路）
        # 核心：剔除历史估值分位极高（最贵）的行业，规避估值泡沫
        # 实现：用 earnings_to_price_ratio(=1/PE) 因子，取近 pe_lookback 日分位
        #       E/P 分位 < pe_expensive_percentile（即估值最贵的N%）的行业被剔除
        # 研报参考：华商基金 - 行业轮动重视估值安全边际
        self.use_pe_filter: bool = ir_cfg.get("use_pe_filter", False)
        self.pe_factor: str = ir_cfg.get(
            "pe_factor", "earnings_to_price_ratio"
        )  # 用作估值代理的因子（高E/P=便宜）
        self.pe_lookback: int = ir_cfg.get(
            "pe_lookback", 250
        )  # 估值分位回看窗口（约1年）
        self.pe_expensive_percentile: float = ir_cfg.get(
            "pe_expensive_percentile", 0.10
        )  # E/P 分位 < 10% 视为过贵（即PE分位 > 90%）
        self.pe_min_industries: int = ir_cfg.get(
            "pe_min_industries", 3
        )  # 至少保留N个行业
        # PE调节RRG投票（NEW v43: PE分位作为RRG投票权重调节因子）
        # 核心：在RRG加权投票得分上叠加PE调节项，便宜行业加分、昂贵行业减分
        # 实现：adjusted_vote = weighted_vote + pe_vote_adjust_alpha * (ep_percentile - 0.5)
        #   - ep_percentile=1（最便宜）：vote + 0.5*alpha（加分，更易入选）
        #   - ep_percentile=0.5（中位）：vote + 0（不变）
        #   - ep_percentile=0（最贵）：vote - 0.5*alpha（减分，更难入选）
        # 与 use_pe_filter 互补：pe_filter 是硬性剔除，pe_adjusted_rrg_vote 是软性调节
        # 研报参考：华商基金估值安全边际 + 西南证券动态分域思路
        self.use_pe_adjusted_rrg_vote: bool = ir_cfg.get(
            "use_pe_adjusted_rrg_vote", False
        )
        self.pe_vote_adjust_alpha: float = ir_cfg.get(
            "pe_vote_adjust_alpha", 0.2
        )  # PE调节强度，0.2表示最大±0.1的调节
        # v45: 震荡市PE调节强度（regime-aware PE adjustment）
        # 当 market_scale < 1.0（震荡市）时使用此alpha，默认None=向后兼容（始终用pe_vote_adjust_alpha）
        # 设计动机：v43在2024(震荡市)Sharpe 0.1053 < v41 0.1826，PE调节在震荡市反而有害（value trap）
        #           v43在2025(趋势市)Sharpe 2.0319 > v41 1.6716，PE调节在趋势市有效
        # 实现：market_scale>=1.0时用pe_vote_adjust_alpha，<1.0时用pe_vote_adjust_alpha_choppy
        self.pe_vote_adjust_alpha_choppy: float | None = ir_cfg.get(
            "pe_vote_adjust_alpha_choppy", None
        )
        # v47: PB分位作为RRG投票权重调节因子（双估值调节）
        # 核心：在PE调节基础上叠加PB调节，提供资产估值维度
        # 动机：PE只反映盈利估值，PB反映资产估值，两者互补
        #       2024年PE调节失效可能因盈利估值信号噪声大，PB提供更稳定的资产估值信号
        # 实现：adjusted_vote = weighted_vote + alpha_ep*(ep_pct-0.5) + alpha_bp*(bp_pct-0.5)
        # 默认alpha_bp=0.0（向后兼容），v47设alpha_ep=0.1+alpha_bp=0.1（总强度0.2同v43）
        self.pe_vote_adjust_alpha_pb: float = ir_cfg.get(
            "pe_vote_adjust_alpha_pb", 0.0
        )
        self.pb_factor: str = ir_cfg.get(
            "pb_factor", "book_to_price_ratio"
        )
        # 行业RS-Ratio加权（NEW in v19: 结构性改进）
        # 核心：用 RS-Ratio 作为行业权重（替代等权），让长期跑赢大盘的行业权重大
        # 研究假设：RS-Ratio>100 表示行业长期跑赢大盘，应给予更高权重
        # 实现：行业权重 ∝ max(rs_ratio, 0)，归一化后应用 max_industry_weight 上限
        #       行业内股票等权分配行业权重
        # 与等权相比：能聚焦强势行业，但避免单一行业过度集中
        self.use_industry_weight_by_rs: bool = ir_cfg.get(
            "use_industry_weight_by_rs", False
        )
        # 多因子选股
        self.use_factors: bool = ir_cfg.get("use_factors", False)
        self.factor_names: list[str] = ir_cfg.get("factor_names", [])
        self.factor_weights: dict[str, float] = ir_cfg.get("factor_weights", {})
        # v49: IC加权替代等权因子（结构性改进，缓解因子时变问题）
        # 核心：用滚动rank IC作为因子权重幅度，保留静态权重方向
        # 动机：v45-v48参数调整均无法解决因子时变问题，IC加权让因子权重自适应近期表现
        # 实现：w_final = sign(w_static) * |mean(rank_IC)| / sum(|w_final|) 归一化
        # 优势：近期有效因子权重大，失效因子权重小，自动适应市场环境变化
        # v49失败：IC值过小(0.02-0.05)导致所有因子趋近等权，静态权重信息丢失
        #
        # v50: IC乘数模式（保留v49 IC计算逻辑，改进使用方式）
        # 核心：IC作为静态权重的乘数，保留静态权重结构信息
        # 实现：w_final = w_static * (1 + scale * norm_ic)
        #   - norm_ic = |IC| / max(|IC|_all_factors) ∈ [0, 1]
        #   - scale=0.5时，最强因子权重×1.5，最弱因子权重×1.0（保持静态）
        # 优势：静态权重结构(raw_beta=-2.0仍是强负权重)不丢失，仅按近期IC幅度调节
        self.use_ic_weighting: bool = ir_cfg.get("use_ic_weighting", False)
        self.ic_lookback: int = ir_cfg.get(
            "ic_lookback", 60
        )  # IC回看窗口（约3个月）
        self.ic_horizon: int = ir_cfg.get(
            "ic_horizon", 5
        )  # 前向收益horizon（约1周）
        # v50: IC加权模式（"replacement"=v49直接替代, "multiplier"=v50乘数模式）
        self.ic_weighting_mode: str = ir_cfg.get(
            "ic_weighting_mode", "replacement"
        )
        # v50: IC乘数缩放因子（仅multiplier模式生效）
        # w_final = w_static * (1 + scale * norm_ic)，scale=0.5表示最强因子×1.5
        self.ic_weight_scale: float = ir_cfg.get("ic_weight_scale", 0.5)
        # v51: IC符号确认机制（仅multiplier模式生效）
        # True: 仅当IC符号与静态权重符号一致时boost，否则保持静态
        # 动机：2024震荡市IC符号频繁翻转，反向IC会错误boost失效因子
        # 实现：effective_ic = |IC| if sign(IC)==sign(w_static) else 0
        #       norm_ic = effective_ic / max(effective_ic_all)
        self.ic_sign_confirm: bool = ir_cfg.get("ic_sign_confirm", False)
        # v52: Regime-aware IC（仅multiplier模式生效）
        # True: 趋势市(market_scale==1.0)启用IC boost，震荡市(market_scale<1.0)禁用IC boost
        # 动机：v50 IC乘数在2024(震荡市)退化-0.1870，在2022/2023/2025(趋势市)均改善
        #       震荡市IC信号噪声大，禁用IC boost回到静态权重更稳定
        # 实现：market_scale<1.0时 norm_ic_map清空，相当于所有因子w_final=w_static
        self.ic_regime_aware: bool = ir_cfg.get("ic_regime_aware", False)
        self._current_market_scale: float = 1.0  # 由select()方法更新
        # v53: 因子正交化（Gram-Schmidt残差化）
        # 核心：对相关因子对做正交化，提取独立信号
        # 动机：v47 PE+PB双估值改善2024(+0.1041)但跨周期恶化(-0.2157)
        #       假设B/P中与E/P共线的部分是恶化源，正交化后B/P独立信号可能更稳定
        # 实现：对每个(base, target)对，target_orth = target_z - corr * base_z
        #       然后重新标准化target_orth（std=1）
        # 配置格式：orthogonalize_pairs: [["earnings_to_price_ratio", "book_to_price_ratio"]]
        #   - base因子保持原样
        #   - target因子替换为残差（与base正交的部分）
        self.use_factor_orthogonalization: bool = ir_cfg.get(
            "use_factor_orthogonalization", False
        )
        self.orthogonalize_pairs: list[list[str]] = ir_cfg.get(
            "orthogonalize_pairs", []
        )  # [[base, target], ...]
        # v64: 北向资金因子（从stock_hk_hold表加载，IC=+0.0234, ICIR=+0.3270, 5日horizon）
        # 因子：hk_hold_ratio_change_5d = share_ratio(t) - share_ratio(t-5)
        # 动机：北向资金是A股"聪明钱"，5日增仓变化对短期收益有预测力
        self.use_hk_hold_factor: bool = ir_cfg.get("use_hk_hold_factor", False)
        self.hk_hold_change_window: int = ir_cfg.get("hk_hold_change_window", 5)
        # v66: 北向因子regime-aware（熊市market_scale<1.0时禁用，避免熊市噪声）
        self.hk_hold_regime_aware: bool = ir_cfg.get("hk_hold_regime_aware", False)
        self._ic_weights_cache: dict[str, dict[str, float]] | None = None
        self._ic_weights_cache_date: Any = None
        # ML选股（LightGBM预测未来收益）
        self.use_ml: bool = ir_cfg.get("use_ml", False)
        self.ml_train_window: int = ir_cfg.get("ml_train_window", 252)
        self.ml_retrain_freq: int = ir_cfg.get("ml_retrain_freq", 21)
        self.ml_target_horizon: int = ir_cfg.get("ml_target_horizon", 20)
        self.ml_n_estimators: int = ir_cfg.get("ml_n_estimators", 150)
        self.ml_max_depth: int = ir_cfg.get("ml_max_depth", 3)
        self.ml_learning_rate: float = ir_cfg.get("ml_learning_rate", 0.05)
        self._industry_map: dict[str, str] | None = None
        self._market_close: pl.DataFrame | None = None
        self._factor_data: pl.DataFrame | None = None
        self._ml_model: Any = None
        self._ml_last_train_idx: int = -999
        self._rrg_table: pl.DataFrame | None = None  # RRG 缓存

    def _load_industry_map(self) -> dict[str, str]:
        """惰性加载行业映射（申万一级行业）"""
        if self._industry_map is not None:
            return self._industry_map
        try:
            from ...data.sources.duckdb_source import DuckDBSource

            source = DuckDBSource({"data_root": self.data_root})
            self._industry_map = source.load_industry_map()
            logger.info(f"行业映射加载: {len(self._industry_map)} 只股票")
        except Exception as e:
            logger.warning(f"行业映射加载失败: {e}")
            self._industry_map = {}
        return self._industry_map

    def _load_market_close(self) -> pl.DataFrame | None:
        """惰性加载大盘指数收盘价（过滤 null 值）"""
        if self._market_close is not None:
            return self._market_close
        if not self.market_filter:
            return None
        try:
            from ...data.sources.duckdb_source import DuckDBSource

            source = DuckDBSource({"data_root": self.data_root})
            df = source.load_index_data(self.market_index)
            if df is not None and len(df) > 0:
                # 过滤 null close 值（早期数据可能缺失）
                self._market_close = (
                    df.select(["date", "close"])
                    .drop_nulls("close")
                    .sort("date")
                )
                logger.info(
                    f"大盘指数加载: {self.market_index}, "
                    f"{len(self._market_close)} 天（已过滤null）"
                )
        except Exception as e:
            logger.warning(f"大盘指数加载失败: {e}")
            self._market_close = None
        return self._market_close

    def _compute_rrg_table(
        self, close: pl.DataFrame
    ) -> pl.DataFrame | None:
        """计算所有日期所有行业的 RS-Ratio 和 RS-Momentum（RRG 框架）

        RRG（Relative Rotation Graph）核心公式：
            RS = 行业均价 / 大盘指数 close（相对强度比值）
            RS-Ratio = RS / SMA(RS, N) × 100  （>100 表示行业长期跑赢大盘）
            RS-Momentum = RS-Ratio / RS-Ratio.shift(M) × 100  （>100 表示相对强度在加速）

        研报参考: 2026 量化轮动策略报告（RRG 框架下行业轮动）
            - RS-Ratio 回看 220 日，RS-Momentum 回看 60 日为最优参数
            - 第一象限（领先）策略年化 18.34%, Sharpe 0.72
            - RS-Momentum 是先行指标，能在行业还领先时发出转弱预警

        Args:
            close: 候选池收盘价宽表（date, code1, code2, ...）

        Returns:
            DataFrame: date, industry, rs_ratio, rs_momentum（缓存）
        """
        if self._rrg_table is not None:
            return self._rrg_table

        market_close = self._load_market_close()
        if market_close is None:
            return None

        industry_map = self._load_industry_map()
        if not industry_map:
            return None

        try:
            # 1. close 宽表转长表 + 行业映射
            close_long = close.melt(
                id_vars="date", variable_name="code", value_name="close"
            ).filter(
                pl.col("close").is_not_null()
                & pl.col("code").is_in(list(industry_map.keys()))
            )

            ind_df = pl.DataFrame({
                "code": list(industry_map.keys()),
                "industry": list(industry_map.values()),
            })
            close_long = close_long.join(ind_df, on="code", how="inner")

            # 2. 按日期+行业聚合，计算行业均价
            industry_daily = close_long.group_by(["date", "industry"]).agg(
                pl.col("close").mean().alias("industry_close")
            )

            # 3. 统一日期类型，join 大盘 close
            industry_daily = industry_daily.with_columns(
                pl.col("date").cast(pl.Date).alias("date_d")
            )
            market_df = market_close.with_columns(
                pl.col("date").cast(pl.Date).alias("date_d")
            ).select(["date_d", "close"]).rename({"close": "market_close"})

            industry_daily = industry_daily.join(
                market_df, on="date_d", how="inner"
            )

            # 4. 计算 RS = industry_close / market_close
            industry_daily = industry_daily.with_columns(
                (pl.col("industry_close") / pl.col("market_close")).alias("rs")
            ).sort(["industry", "date"])

            # 5. 计算 RS-Ratio = RS / SMA(RS, N) × 100
            industry_daily = industry_daily.with_columns(
                pl.col("rs")
                .rolling_mean(window_size=self.rs_ratio_window)
                .over("industry")
                .alias("rs_sma")
            ).with_columns(
                (pl.col("rs") / pl.col("rs_sma") * 100.0).alias("rs_ratio")
            )

            # 6. 计算 RS-Momentum = RS-Ratio / RS-Ratio.shift(M) × 100
            # 多周期模式：计算每个窗口的 RS-Mom 列（rs_momentum_10, rs_momentum_30, ...）
            # 单周期模式：保持向后兼容，仅计算 rs_momentum 一列
            windows_to_compute = (
                self.rs_momentum_windows
                if len(self.rs_momentum_windows) > 1
                else [self.rs_momentum_window]
            )
            rrg_cols = ["date", "industry", "rs_ratio"]
            for w in windows_to_compute:
                col_name = (
                    f"rs_momentum_{w}"
                    if len(windows_to_compute) > 1
                    else "rs_momentum"
                )
                industry_daily = industry_daily.with_columns(
                    (
                        pl.col("rs_ratio")
                        / pl.col("rs_ratio").shift(w)
                        * 100.0
                    ).alias(col_name)
                )
                rrg_cols.append(col_name)

            self._rrg_table = industry_daily.select(rrg_cols)

            logger.info(
                f"RRG 计算完成: {len(self._rrg_table)} 行, "
                f"{self._rrg_table['industry'].n_unique()} 行业, "
                f"rs_ratio_window={self.rs_ratio_window}, "
                f"rs_momentum_windows={windows_to_compute}"
            )
        except Exception as e:
            logger.warning(f"RRG 计算失败: {e}")
            self._rrg_table = None

        return self._rrg_table

    def _load_factor_data(self) -> pl.DataFrame | None:
        """惰性加载预计算因子宽表数据"""
        if self._factor_data is not None:
            return self._factor_data
        # use_factors 或 use_ml 任一启用时都需要加载因子数据
        # （ML 用因子作为特征，不应依赖 use_factors 标志）
        # 拥挤度过滤也需要加载 crowding_factors
        # 估值过滤需要加载 pe_factor
        # 拥挤度反转需要加载 crowding_factors
        # 拥挤度反转因子需要加载 crowding_reversal_factor
        # PE调节RRG投票需要加载 pe_factor
        need_load = (
            (self.use_factors or self.use_ml) and self.factor_names
        ) or (self.use_crowding_filter and self.crowding_factors) or (
            self.use_pe_filter and self.pe_factor
        ) or (self.use_crowding_reversal and self.crowding_factors) or (
            self.use_crowding_reversal_factor and self.crowding_reversal_factor
        ) or (
            self.use_pe_adjusted_rrg_vote and self.pe_factor
        )
        if not need_load:
            return None
        try:
            from ...data.sources.duckdb_source import DuckDBSource

            source = DuckDBSource({"data_root": self.data_root})
            # 加载 factor_names + crowding_factors + pe_factor + 反转因子的并集（去重）
            extra_factors = list(self.crowding_factors) if (
                self.use_crowding_filter or self.use_crowding_reversal
            ) else []
            if self.use_pe_filter and self.pe_factor:
                extra_factors.append(self.pe_factor)
            if (
                self.use_pe_adjusted_rrg_vote
                and self.pe_factor
                and self.pe_factor not in extra_factors
            ):
                extra_factors.append(self.pe_factor)
            if (
                self.use_crowding_reversal_factor
                and self.crowding_reversal_factor
                and self.crowding_reversal_factor not in self.factor_names
            ):
                extra_factors.append(self.crowding_reversal_factor)
            all_factors = list(
                dict.fromkeys(self.factor_names + extra_factors)
            )
            df = source.load_factor_wide(factor_names=all_factors)
            if df is not None and len(df) > 0:
                # v64: 合并北向资金因子
                if self.use_hk_hold_factor:
                    hk_factor_name = f"hk_hold_ratio_change_{self.hk_hold_change_window}d"
                    try:
                        hk_df = source.con.execute(f"""
                            SELECT date, code, share_ratio
                            FROM stock_hk_hold
                            ORDER BY code, date
                        """).pl()
                        if len(hk_df) > 0:
                            # 统一date类型为DATE，统一code为denormalized格式（与load_factor_wide对齐）
                            hk_df = hk_df.with_columns(
                                pl.col("date").cast(pl.Date),
                                pl.col("code").map_elements(source.denormalize_code, return_dtype=pl.Utf8),
                            )
                            df = df.with_columns(pl.col("date").cast(pl.Date))
                            # 每只股票每日取所有link_id的share_ratio之和
                            hk_df = hk_df.group_by(["date", "code"]).agg(
                                pl.col("share_ratio").sum().alias("hk_hold_ratio")
                            )
                            hk_df = hk_df.sort(["code", "date"])
                            # 计算N日变化
                            w = self.hk_hold_change_window
                            hk_df = hk_df.with_columns(
                                (pl.col("hk_hold_ratio") - pl.col("hk_hold_ratio").shift(w).over("code")).alias(hk_factor_name)
                            )
                            hk_df = hk_df.select(["date", "code", hk_factor_name])
                            # 合并到因子数据
                            before_rows = len(df)
                            df = df.join(hk_df, on=["date", "code"], how="left")
                            non_null = df.select(pl.col(hk_factor_name).is_not_null().sum()).item()
                            logger.info(f"北向资金因子合并: {hk_factor_name}, {len(hk_df)} 行, "
                                       f"join后{len(df)}行, 非空{non_null}行")
                    except Exception as e:
                        logger.warning(f"北向资金因子加载失败: {e}")

                self._factor_data = df.sort("date")
                n_extra_hk = 1 if self.use_hk_hold_factor else 0
                logger.info(
                    f"因子数据加载: {len(df)} 行, {len(all_factors) + n_extra_hk} 个因子 "
                    f"(选股{len(self.factor_names)}+拥挤度{len(self.crowding_factors) if (self.use_crowding_filter or self.use_crowding_reversal) else 0}"
                    f"+估值{1 if self.use_pe_filter or self.use_pe_adjusted_rrg_vote else 0}"
                    f"+反转{1 if self.use_crowding_reversal_factor else 0}"
                    f"+北向{n_extra_hk})"
                )
        except Exception as e:
            logger.warning(f"因子数据加载失败: {e}")
            self._factor_data = None
        return self._factor_data

    def _compute_factor_ic_weights(
        self,
        select_date: Any,
        stock_codes: list[str],
        close: pl.DataFrame,
    ) -> dict[str, float]:
        """计算因子滚动rank IC权重（v49新增）

        对每个因子在 ic_lookback 窗口内计算 rank IC（Spearman相关），
        返回 mean(rank_IC) 作为因子权重幅度。

        IC计算流程：
          1. 将close转为长格式，计算前向收益 forward_return[T] = close[T+h]/close[T]-1
          2. 与factor_data按(date, code)关联
          3. 对每个日期T，计算因子值排名与收益排名的Pearson相关（=Spearman）
          4. 对lookback窗口内所有有效日期的IC取均值

        Args:
            select_date: 选股日期
            stock_codes: 候选股票列表（用于过滤）
            close: 收盘价宽表（date + 各code列）

        Returns:
            {factor_name: mean_rank_ic}  IC值范围[-1, 1]
        """
        # 缓存：同一select_date不重复计算
        if (
            self._ic_weights_cache is not None
            and self._ic_weights_cache_date == select_date
        ):
            return self._ic_weights_cache

        factor_data = self._load_factor_data()
        if factor_data is None:
            return {}

        if hasattr(select_date, "date"):
            select_date_obj = select_date.date()
        else:
            select_date_obj = select_date

        from datetime import timedelta

        lookback_start = select_date_obj - timedelta(days=self.ic_lookback)
        # 前向收益需要select_date - ic_horizon 之前的数据（避免前视偏差）
        forward_end = select_date_obj - timedelta(days=self.ic_horizon)

        # 1. close转长格式并计算前向收益
        close_cols = [c for c in close.columns if c != "date"]
        close_long = close.melt(
            id_vars="date", variable_name="code", value_name="close"
        )
        # 统一date类型为date（close可能是datetime，factor_data是date）
        close_long = close_long.with_columns(pl.col("date").dt.date().alias("date"))
        close_long = close_long.filter(pl.col("code").is_in(stock_codes))
        close_long = close_long.sort(["code", "date"])
        close_long = close_long.with_columns(
            pl.col("close").shift(-self.ic_horizon).over("code").alias("close_fwd")
        )
        close_long = close_long.with_columns(
            ((pl.col("close_fwd") / pl.col("close")) - 1.0).alias("fwd_return")
        )
        close_long = close_long.drop_nulls("fwd_return")

        # 2. 过滤到lookback窗口
        close_long = close_long.filter(
            (pl.col("date") >= lookback_start)
            & (pl.col("date") <= forward_end)
        )
        if len(close_long) == 0:
            return {}

        # 3. 关联factor_data（确保date类型一致）
        factor_cols = [
            c for c in factor_data.columns if c in self.factor_names
        ]
        if not factor_cols:
            return {}

        # 确保factor_data的date也是date类型（可能为datetime）
        factor_subset = factor_data.select(["date", "code"] + factor_cols)
        if factor_subset["date"].dtype != pl.Date:
            factor_subset = factor_subset.with_columns(
                pl.col("date").dt.date().alias("date")
            )

        joined = factor_subset.join(
            close_long.select(["date", "code", "fwd_return"]),
            on=["date", "code"],
            how="inner",
        )
        if len(joined) == 0:
            return {}

        # 4. 对每个因子计算滚动rank IC
        ic_weights: dict[str, float] = {}
        for factor_name in factor_cols:
            col_data = joined.select(
                ["date", "code", factor_name, "fwd_return"]
            ).drop_nulls()
            if len(col_data) < 20:  # 数据不足
                continue

            # 计算每日rank IC（Pearson on ranks = Spearman）
            ranked = col_data.with_columns(
                [
                    pl.col(factor_name).rank().over("date").alias("factor_rank"),
                    pl.col("fwd_return").rank().over("date").alias("return_rank"),
                ]
            )
            ic_per_date = (
                ranked.group_by("date")
                .agg(
                    pl.corr("factor_rank", "return_rank").alias("ic")
                )
                .drop_nulls("ic")
            )
            if len(ic_per_date) < 5:  # 有效日期不足
                continue

            mean_ic = float(ic_per_date["ic"].mean())
            ic_weights[factor_name] = mean_ic

        # 缓存
        self._ic_weights_cache = ic_weights
        self._ic_weights_cache_date = select_date

        logger.info(
            f"IC权重计算完成: {len(ic_weights)}/{len(factor_cols)} 个因子, "
            f"lookback={self.ic_lookback}d, horizon={self.ic_horizon}d"
        )
        return ic_weights

    def _compute_factor_scores(
        self, select_date: Any, stock_codes: list[str],
        close: pl.DataFrame | None = None,
    ) -> dict[str, float]:
        """计算多因子复合评分

        对给定日期的截面因子值做 z-score 标准化后加权求和。

        Args:
            select_date: 选股日期
            stock_codes: 候选股票列表

        Returns:
            {code: composite_score}
        """
        factor_data = self._load_factor_data()
        if factor_data is None:
            return {}

        # 日期对齐：取 select_date 当天或之前最近的因子数据
        if hasattr(select_date, "date"):
            select_date_obj = select_date.date()
        else:
            select_date_obj = select_date

        # 过滤到选股日及之前的因子数据，取每个code最新的一条
        factor_before = factor_data.filter(
            pl.col("date").dt.date() <= select_date_obj
        )
        if len(factor_before) == 0:
            return {}

        # 取每个code最新截面（因子数据可能不是每天更新）
        factor截面 = (
            factor_before.sort("date", descending=True)
            .group_by("code")
            .first()
        )

        # 只保留候选池中的股票
        factor截面 = factor截面.filter(pl.col("code").is_in(stock_codes))
        if len(factor截面) == 0:
            return {}

        # 对每个因子做 z-score 标准化
        scores: dict[str, float] = {}
        factor_cols = [
            c for c in factor截面.columns if c in self.factor_names
        ]
        if not factor_cols:
            return {}

        # 计算每个因子的 z-score
        factor_scores: dict[str, dict[str, float]] = {}  # {factor: {code: zscore}}
        for factor_name in factor_cols:
            col_data = factor截面.select(["code", factor_name]).drop_nulls(
                factor_name
            )
            if len(col_data) < 5:
                continue
            vals = col_data[factor_name].to_numpy()
            mean = np.mean(vals)
            std = np.std(vals, ddof=1)
            if std < 1e-10:
                continue
            zscores = (vals - mean) / std
            codes = col_data["code"].to_list()
            factor_scores[factor_name] = {
                code: float(z) for code, z in zip(codes, zscores)
            }

        # v53: 因子正交化（Gram-Schmidt残差化）
        # 对每个(base, target)对，target_orth = target_z - corr * base_z
        # 然后重新标准化target_orth（std=1）
        if self.use_factor_orthogonalization and self.orthogonalize_pairs:
            for pair in self.orthogonalize_pairs:
                if len(pair) != 2:
                    continue
                base_f, target_f = pair[0], pair[1]
                if base_f not in factor_scores or target_f not in factor_scores:
                    continue
                base_map = factor_scores[base_f]
                target_map = factor_scores[target_f]
                common_codes = set(base_map.keys()) & set(target_map.keys())
                if len(common_codes) < 10:
                    continue
                base_vals = np.array([base_map[c] for c in common_codes])
                target_vals = np.array([target_map[c] for c in common_codes])
                # z-score已标准化，corr即回归系数
                corr = float(np.corrcoef(base_vals, target_vals)[0, 1])
                if np.isnan(corr):
                    continue
                # 残差 = target - corr * base（与base正交）
                orth_vals = target_vals - corr * base_vals
                orth_std = float(np.std(orth_vals, ddof=1))
                if orth_std < 1e-10:
                    # target完全由base解释，正交化后无信号，保留原值
                    continue
                # 重新标准化
                for c, ov in zip(common_codes, orth_vals):
                    target_map[c] = float(ov / orth_std)
                logger.debug(
                    f"v53 因子正交化: {target_f} ~ {base_f} (corr={corr:.4f}), "
                    f"{target_f} 替换为残差"
                )

        if not factor_scores:
            return {}

        # v49/v50: IC加权（启用时用滚动rank IC调节因子权重）
        ic_weights: dict[str, float] = {}
        if self.use_ic_weighting and close is not None:
            ic_weights = self._compute_factor_ic_weights(
                select_date, stock_codes, close
            )
        # v50/v51/v52: multiplier模式下计算归一化IC（norm_ic ∈ [0, 1]）
        norm_ic_map: dict[str, float] = {}
        if (
            self.use_ic_weighting
            and self.ic_weighting_mode == "multiplier"
            and ic_weights
        ):
            # v52: regime-aware IC - 震荡市(market_scale<1.0)禁用IC boost
            if self.ic_regime_aware and self._current_market_scale < 1.0:
                # 震荡市：norm_ic_map保持空，所有因子w_final=w_static
                logger.debug(
                    f"v52 regime-aware IC: 震荡市(market_scale={self._current_market_scale:.2f})，"
                    f"禁用IC boost"
                )
            elif self.ic_sign_confirm:
                # v51: 仅IC符号与静态权重符号一致时计入effective_ic
                # 反向IC的因子effective_ic=0，不参与归一化也不boost
                effective_ic_map: dict[str, float] = {}
                for fname, ic_val in ic_weights.items():
                    w_static = self.factor_weights.get(fname, 1.0)
                    if np.sign(ic_val) == np.sign(w_static):
                        effective_ic_map[fname] = abs(ic_val)
                    else:
                        effective_ic_map[fname] = 0.0
                max_eff_ic = (
                    max(effective_ic_map.values()) if effective_ic_map else 0.0
                )
                if max_eff_ic > 1e-10:
                    norm_ic_map = {
                        k: v / max_eff_ic for k, v in effective_ic_map.items()
                    }
            else:
                # v50: 直接用|IC|归一化
                max_abs_ic = (
                    max(abs(v) for v in ic_weights.values())
                    if ic_weights
                    else 0.0
                )
                if max_abs_ic > 1e-10:
                    norm_ic_map = {
                        k: abs(v) / max_abs_ic for k, v in ic_weights.items()
                    }
        # 加权求和（支持负权重实现反向因子：weight_sum 用 abs(w) 归一化）
        # v66: regime-aware hk_hold（熊市禁用北向因子）
        skip_hk_hold = (
            self.hk_hold_regime_aware
            and self._current_market_scale < 1.0
        )
        for code in stock_codes:
            total = 0.0
            weight_sum = 0.0
            for factor_name, code_scores in factor_scores.items():
                if skip_hk_hold and factor_name.startswith("hk_hold_ratio_change"):
                    continue
                if code in code_scores:
                    w_static = self.factor_weights.get(factor_name, 1.0)
                    if self.use_ic_weighting and factor_name in ic_weights:
                        if self.ic_weighting_mode == "multiplier":
                            # v50/v51: w_final = w_static * (1 + scale * norm_ic)
                            # 保留静态权重结构，仅按IC幅度调节
                            norm_ic = norm_ic_map.get(factor_name, 0.0)
                            w = float(
                                w_static
                                * (1.0 + self.ic_weight_scale * norm_ic)
                            )
                        else:
                            # v49: w_final = sign(w_static) * |IC|
                            # IC幅度替代静态幅度，方向保留静态
                            w = float(
                                np.sign(w_static) * abs(ic_weights[factor_name])
                            )
                    else:
                        w = w_static
                    total += w * code_scores[code]
                    weight_sum += abs(w)
            if weight_sum > 0:
                scores[code] = total / weight_sum

        return scores

    def _compute_reversal_factor_scores(
        self, select_date: Any, stock_codes: list[str]
    ) -> dict[str, float]:
        """计算独立反转因子评分（v38新增，修正v16失败实现）

        对给定日期的截面反转因子值做 z-score 标准化。
        反转因子（如BIAS20）：低值=超跌=反弹潜力大，应得高分。
        通过 crowding_reversal_direction 控制方向：
            - direction=-1（默认）：低因子值得高分（适用于BIAS20等乖离率因子）
            - direction=1：高因子值得高分（适用于正向反转因子）

        Args:
            select_date: 选股日期
            stock_codes: 候选股票列表

        Returns:
            {code: reversal_zscore}
        """
        factor_data = self._load_factor_data()
        if factor_data is None:
            return {}

        if hasattr(select_date, "date"):
            select_date_obj = select_date.date()
        else:
            select_date_obj = select_date

        factor_before = factor_data.filter(
            pl.col("date").dt.date() <= select_date_obj
        )
        if len(factor_before) == 0:
            return {}

        # 取每个code最新截面
        factor截面 = (
            factor_before.sort("date", descending=True)
            .group_by("code")
            .first()
        )
        factor截面 = factor截面.filter(pl.col("code").is_in(stock_codes))

        # 检查反转因子列是否存在
        if self.crowding_reversal_factor not in factor截面.columns:
            logger.warning(
                f"反转因子 {self.crowding_reversal_factor} 不在 factor_data 中, "
                f"可用列: {factor截面.columns[:20]}..."
            )
            return {}

        col_data = factor截面.select(
            ["code", self.crowding_reversal_factor]
        ).drop_nulls(self.crowding_reversal_factor)
        if len(col_data) < 5:
            return {}

        vals = col_data[self.crowding_reversal_factor].to_numpy()
        mean = np.mean(vals)
        std = np.std(vals, ddof=1)
        if std < 1e-10:
            return {}

        zscores = (vals - mean) / std
        # 应用方向：-1表示低值得高分（反转），1表示高值得高分（正向）
        zscores = zscores * self.crowding_reversal_direction
        codes = col_data["code"].to_list()
        return {code: float(z) for code, z in zip(codes, zscores)}

    def _compute_market_scale(self, select_idx: int, close: pl.DataFrame) -> float:
        """计算大盘趋势过滤系数

        跌破短期均线 → 0.5（降仓50%）
        跌破长期均线 → 0.0（空仓）
        否则 → 1.0（满仓）

        Args:
            select_idx: 选股截面索引（用 t-1 的数据）
            close: 候选池收盘价宽表（用于对齐日期）

        Returns:
            仓位缩放系数 [0.0, 1.0]
        """
        market_close = self._load_market_close()
        if market_close is None:
            return 1.0

        # 用候选池日期对齐大盘指数
        if select_idx >= len(close) or select_idx < self.market_ma_long + 1:
            return 1.0

        # 取选股日的日期
        select_date = close.row(select_idx, named=True).get("date")
        if select_date is None:
            return 1.0

        # 转为 date 类型比较（避免字符串比较 "2024-01-05 00:00:00" > "2024-01-05" 的bug）
        if hasattr(select_date, "date"):
            select_date_obj = select_date.date()
        else:
            from datetime import datetime
            select_date_obj = select_date if isinstance(select_date, datetime) else None
            if select_date_obj is None:
                return 1.0

        # 取大盘指数在 select_date 之前（含当天）的数据
        market_before = market_close.filter(pl.col("date").dt.date() <= select_date_obj)
        if len(market_before) < self.market_ma_long + 1:
            return 1.0

        prices = market_before["close"].to_list()
        current_price = prices[-1]
        ma_short = float(np.mean(prices[-self.market_ma_short:]))
        ma_long = float(np.mean(prices[-self.market_ma_long:]))

        if self.market_filter_binary:
            # 二值模式（v62+）：只决定是否空仓，仓位幅度交风控层
            if current_price < ma_long:
                ma_scale = 0.0  # 跌破长期均线，空仓
            else:
                ma_scale = 1.0  # 不空仓，仓位幅度由风控层决定

            # 绝对动量作为空仓信号（而非降仓）
            if (
                self.absolute_momentum
                and ma_scale > 0
                and len(prices) >= self.absolute_momentum_window + 1
            ):
                abs_ret = (
                    prices[-1] / prices[-self.absolute_momentum_window - 1] - 1
                )
                if abs_ret < self.absolute_momentum_threshold:
                    ma_scale = 0.0
                    logger.debug(
                        f"绝对动量空仓: {self.absolute_momentum_window}日收益="
                        f"{abs_ret:.2%} < {self.absolute_momentum_threshold}"
                    )
        else:
            # 原三档逻辑（向后兼容）
            if current_price < ma_long:
                ma_scale = 0.0  # 跌破长期均线，空仓
            elif current_price < ma_short:
                ma_scale = 0.5  # 跌破短期均线，降仓50%
            else:
                ma_scale = 1.0

            # 绝对动量叠加（Dual Momentum）：近期收益为负时进一步降仓
            # 参考 Antonacci 双动量：绝对动量提供趋势过滤，在下跌趋势中主动避险
            if (
                self.absolute_momentum
                and ma_scale > 0
                and len(prices) >= self.absolute_momentum_window + 1
            ):
                abs_ret = (
                    prices[-1] / prices[-self.absolute_momentum_window - 1] - 1
                )
                if abs_ret < self.absolute_momentum_threshold:
                    ma_scale *= self.absolute_momentum_scale
                    logger.debug(
                        f"绝对动量降仓: {self.absolute_momentum_window}日收益="
                        f"{abs_ret:.2%} < {self.absolute_momentum_threshold}, "
                        f"仓位×{self.absolute_momentum_scale}"
                    )

        return ma_scale

    def _compute_residual_momentum(
        self,
        select_idx: int,
        close: pl.DataFrame,
        stock_codes: list[str],
        mom_short: pl.DataFrame,
        mom_long: pl.DataFrame,
    ) -> tuple[dict[str, float], dict[str, float]]:
        """计算残差动量（剔除市场Beta暴露）

        残差动量 = stock_return - raw_beta * market_return

        研报参考：华泰金工《残差动量行业轮动》年化超额12.90%
        剔除市场Beta后，更能反映股票自身的强势，避免高Beta股虚假动量

        Args:
            select_idx: 选股截面索引（用 t-1 数据）
            close: 候选池收盘价宽表（用于获取 select_date）
            stock_codes: 候选股票列表
            mom_short: 短期动量宽表 close.shift(momentum_short)
            mom_long: 长期动量宽表 close.shift(momentum_long)

        Returns:
            (residual_short_dict, residual_long_dict)
            每个dict: {code: residual_momentum}
        """
        # 1. 获取选股日
        select_date_raw = close.row(select_idx, named=True).get("date")
        if hasattr(select_date_raw, "date"):
            select_date_obj = select_date_raw.date()
        else:
            select_date_obj = select_date_raw

        # 2. 加载 raw_beta 因子截面
        factor_data = self._load_factor_data()
        beta_dict: dict[str, float] = {}
        if factor_data is not None:
            # 取 select_date 当天或之前最近的因子数据
            factor_before = factor_data.filter(
                pl.col("date").dt.date() <= select_date_obj
            )
            if len(factor_before) > 0:
                # 取每个code最新截面
                beta截面 = (
                    factor_before.sort("date", descending=True)
                    .group_by("code")
                    .first()
                )
                beta截面 = beta截面.filter(pl.col("code").is_in(stock_codes))
                if self.residual_beta_factor in beta截面.columns:
                    for row in beta截面.iter_rows(named=True):
                        v = row.get(self.residual_beta_factor)
                        if v is not None and not (isinstance(v, float) and np.isnan(v)):
                            beta_dict[row["code"]] = float(v)

        # 3. 获取市场收益率（短期/长期）
        market_close = self._load_market_close()
        if market_close is None:
            # 无大盘数据，回退到简单动量
            short_row = mom_short.row(select_idx, named=True)
            long_row = mom_long.row(select_idx, named=True)
            return (
                {c: float(short_row.get(c, 0) or 0) for c in stock_codes},
                {c: float(long_row.get(c, 0) or 0) for c in stock_codes},
            )

        # 取大盘在 select_date 之前（含当天）的数据
        market_before = market_close.filter(
            pl.col("date").dt.date() <= select_date_obj
        )
        if len(market_before) < self.momentum_long + 1:
            # 数据不足，回退到简单动量
            short_row = mom_short.row(select_idx, named=True)
            long_row = mom_long.row(select_idx, named=True)
            return (
                {c: float(short_row.get(c, 0) or 0) for c in stock_codes},
                {c: float(long_row.get(c, 0) or 0) for c in stock_codes},
            )

        prices = market_before["close"].to_list()
        # 与 stock_mom 对齐：用 t-1 截面，所以market_return也用 t-1 截面
        market_ret_short = prices[-1] / prices[-self.momentum_short - 1] - 1
        market_ret_long = prices[-1] / prices[-self.momentum_long - 1] - 1

        # 4. 计算残差动量
        short_row = mom_short.row(select_idx, named=True)
        long_row = mom_long.row(select_idx, named=True)

        residual_short: dict[str, float] = {}
        residual_long: dict[str, float] = {}
        n_beta_used = 0
        for code in stock_codes:
            s = short_row.get(code)
            l = long_row.get(code)
            if s is None or l is None:
                continue
            if not (isinstance(s, (int, float)) and isinstance(l, (int, float))):
                continue
            if np.isnan(s) or np.isnan(l):
                continue
            beta = beta_dict.get(code, self.residual_beta_default)
            if code in beta_dict:
                n_beta_used += 1
            # 残差动量 = 个股收益 - beta * 市场收益
            residual_short[code] = float(s) - beta * market_ret_short
            residual_long[code] = float(l) - beta * market_ret_long

        logger.debug(
            f"残差动量计算: {len(residual_short)} 只股票, "
            f"beta覆盖率={n_beta_used}/{len(residual_short)}, "
            f"market_ret_short={market_ret_short:.4f}, "
            f"market_ret_long={market_ret_long:.4f}"
        )

        return residual_short, residual_long

    def _compute_industry_crowding(
        self,
        select_idx: int,
        close: pl.DataFrame,
        top_industries: list[str],
        industry_stocks: dict[str, list[str]],
    ) -> dict[str, int]:
        """计算行业拥挤度得分（华泰金工3指标简化版）

        拥挤度指标（预计算因子）：
        - VOL20: 20日成交量
        - turnover_volatility: 换手率波动率
        - Skewness20: 20日偏度

        对每个行业，计算该行业所有股票的拥挤度因子均值，
        然后取近 crowding_window 日的分位，超过 crowding_threshold 则触发。
        触发数 >= crowding_min_triggers 为高拥挤行业。

        Args:
            select_idx: 选股截面索引（用 t-1 数据）
            close: 候选池收盘价宽表（用于获取 select_date）
            top_industries: 候选行业列表
            industry_stocks: {industry: [code1, code2, ...]}

        Returns:
            {industry: crowding_score}  crowding_score=触发的指标数
        """
        factor_data = self._load_factor_data()
        if factor_data is None:
            return {ind: 0 for ind in top_industries}

        # 获取选股日
        select_date_raw = close.row(select_idx, named=True).get("date")
        if hasattr(select_date_raw, "date"):
            select_date_obj = select_date_raw.date()
        else:
            select_date_obj = select_date_raw

        # 检查因子列是否存在
        available_factors = [
            f for f in self.crowding_factors if f in factor_data.columns
        ]
        if not available_factors:
            logger.warning(
                f"拥挤度因子全部不可用: {self.crowding_factors}, "
                f"factor_data列: {factor_data.columns[:20]}..."
            )
            return {ind: 0 for ind in top_industries}

        # 取近 crowding_window 日的因子数据
        factor_recent = factor_data.filter(
            pl.col("date").dt.date() <= select_date_obj
        ).sort("date").group_by("code").map_groups(
            lambda g: g.tail(self.crowding_window)
        )

        if len(factor_recent) == 0:
            return {ind: 0 for ind in top_industries}

        # 对每个行业计算拥挤度得分
        crowding_scores: dict[str, int] = {}
        for industry in top_industries:
            stocks = industry_stocks.get(industry, [])
            if not stocks:
                crowding_scores[industry] = 0
                continue

            # 取该行业股票的因子数据
            ind_data = factor_recent.filter(pl.col("code").is_in(stocks))
            if len(ind_data) == 0:
                crowding_scores[industry] = 0
                continue

            # 计算每个因子的当前值（截面均值）和历史分位
            triggers = 0
            for factor_name in available_factors:
                if factor_name not in ind_data.columns:
                    continue
                # 按日期聚合（行业截面均值）
                daily_ind = (
                    ind_data.group_by("date")
                    .agg(pl.col(factor_name).mean().alias("factor_val"))
                    .drop_nulls("factor_val")
                    .sort("date")
                )
                if len(daily_ind) < 30:  # 数据不足
                    continue

                current_val = daily_ind["factor_val"][-1]
                if current_val is None:
                    continue

                # 计算近 crowding_window 日的分位
                history_vals = daily_ind["factor_val"].to_numpy()
                history_vals = history_vals[~np.isnan(history_vals)]
                if len(history_vals) < 30:
                    continue

                # 95%分位阈值
                threshold = float(np.quantile(history_vals, self.crowding_threshold))
                if current_val > threshold:
                    triggers += 1

            crowding_scores[industry] = triggers

        return crowding_scores

    def _compute_industry_pe_percentile(
        self,
        select_idx: int,
        close: pl.DataFrame,
        top_industries: list[str],
        industry_stocks: dict[str, list[str]],
        factor_name: str | None = None,
    ) -> dict[str, float]:
        """计算行业估值分位（华商基金估值安全边际思路）

        使用 earnings_to_price_ratio(=1/PE) 作为估值代理：
        - 高 E/P = 便宜（低估）
        - 低 E/P = 昂贵（高估）

        对每个行业，计算该行业所有股票 E/P 的截面均值，
        然后取近 pe_lookback 日的分位值：
        - 分位 < pe_expensive_percentile 表示当前 E/P 处于历史低位（即 PE 处于高位，估值贵）

        Args:
            select_idx: 选股截面索引
            close: 候选池收盘价宽表（用于获取 select_date）
            top_industries: 候选行业列表
            industry_stocks: {industry: [code1, code2, ...]}
            factor_name: 估值因子名（v47新增，默认None用self.pe_factor）

        Returns:
            {industry: ep_percentile}  ep_percentile in [0, 1]
            高分位=便宜，低分位=贵
        """
        factor_data = self._load_factor_data()
        if factor_data is None:
            return {ind: 0.5 for ind in top_industries}

        # 获取选股日
        select_date_raw = close.row(select_idx, named=True).get("date")
        if hasattr(select_date_raw, "date"):
            select_date_obj = select_date_raw.date()
        else:
            select_date_obj = select_date_raw

        # v47: 支持任意估值因子（默认self.pe_factor向后兼容）
        use_factor = factor_name if factor_name is not None else self.pe_factor

        # 检查因子列
        if use_factor not in factor_data.columns:
            logger.warning(
                f"估值因子 {use_factor} 不在 factor_data 中, "
                f"可用列: {factor_data.columns[:20]}..."
            )
            return {ind: 0.5 for ind in top_industries}

        # 取近 pe_lookback 日的因子数据
        factor_recent = factor_data.filter(
            pl.col("date").dt.date() <= select_date_obj
        ).sort("date").group_by("code").map_groups(
            lambda g: g.tail(self.pe_lookback)
        )

        if len(factor_recent) == 0:
            return {ind: 0.5 for ind in top_industries}

        # 对每个行业计算 E/P 分位
        pe_percentiles: dict[str, float] = {}
        for industry in top_industries:
            stocks = industry_stocks.get(industry, [])
            if not stocks:
                pe_percentiles[industry] = 0.5
                continue

            # 取该行业股票的因子数据
            ind_data = factor_recent.filter(pl.col("code").is_in(stocks))
            if len(ind_data) == 0:
                pe_percentiles[industry] = 0.5
                continue

            # 按日期聚合（行业截面均值，排除极端值）
            daily_ind = (
                ind_data.group_by("date")
                .agg(pl.col(use_factor).mean().alias("factor_val"))
                .drop_nulls("factor_val")
                .sort("date")
            )
            if len(daily_ind) < 30:
                pe_percentiles[industry] = 0.5
                continue

            current_val = daily_ind["factor_val"][-1]
            if current_val is None:
                pe_percentiles[industry] = 0.5
                continue

            # 计算当前 E/P 在历史中的分位
            history_vals = daily_ind["factor_val"].to_numpy()
            history_vals = history_vals[~np.isnan(history_vals)]
            if len(history_vals) < 30:
                pe_percentiles[industry] = 0.5
                continue

            # 分位 = 当前值在历史中的位置（0=最低/最贵，1=最高/最便宜）
            percentile = float(np.mean(history_vals <= current_val))
            pe_percentiles[industry] = percentile

        return pe_percentiles

    def _build_ml_training_data(
        self, select_idx: int, close: pl.DataFrame, stock_codes: list[str]
    ) -> tuple[np.ndarray | None, np.ndarray | None]:
        """构建ML训练数据（向量化）

        用历史因子值预测未来收益。
        X = 因子值, y = 未来 horizon 日收益率

        Args:
            select_idx: 选股截面索引（用 t-1 数据）
            close: 候选池收盘价宽表
            stock_codes: 候选股票列表

        Returns:
            (X, y) 或 (None, None)
        """
        factor_data = self._load_factor_data()
        if factor_data is None:
            return None, None

        horizon = self.ml_target_horizon
        train_start_idx = max(0, select_idx - self.ml_train_window)
        train_end_idx = select_idx - horizon

        if train_end_idx <= train_start_idx + 60:
            return None, None

        close_dates = close["date"].to_list()
        start_date = close_dates[train_start_idx]
        end_date = close_dates[train_end_idx]
        # 统一为 date 类型（close 中可能是 datetime）
        if hasattr(start_date, "date"):
            start_date = start_date.date()
        if hasattr(end_date, "date"):
            end_date = end_date.date()

        factor_cols = [c for c in factor_data.columns if c in self.factor_names]
        if not factor_cols:
            return None, None

        # close 宽表转长表，按 code 分组计算未来收益
        close_long = close.melt(
            id_vars="date", variable_name="code", value_name="close"
        )
        # 统一 date 类型为 date（与因子数据对齐）
        close_long = close_long.with_columns(
            pl.col("date").cast(pl.Date).alias("date")
        )
        close_long = close_long.filter(
            pl.col("close").is_not_null()
            & pl.col("code").is_in(stock_codes)
            & (pl.col("date") >= start_date)
            & (pl.col("date") <= end_date)
        ).sort(["code", "date"])

        # 按 code 分组计算 horizon 日未来收益
        close_long = close_long.with_columns(
            pl.col("close").shift(-horizon).over("code").alias("close_future")
        ).with_columns(
            (pl.col("close_future") / pl.col("close") - 1.0).alias("fwd_return")
        )

        close_long = close_long.drop_nulls("fwd_return")

        if len(close_long) == 0:
            return None, None

        # 因子数据过滤到训练期，统一 date 类型
        factor_filtered = factor_data.select(
            ["date", "code"] + factor_cols
        ).with_columns(
            pl.col("date").cast(pl.Date).alias("date")
        ).filter(
            pl.col("code").is_in(stock_codes)
            & (pl.col("date") >= start_date)
            & (pl.col("date") <= end_date)
        )

        # inner join on (date, code)
        train_df = close_long.join(
            factor_filtered, on=["date", "code"], how="inner"
        ).drop_nulls(factor_cols)

        if len(train_df) < 200:
            return None, None

        # 截面 z-score 标准化（每个日期内，对每个因子做 z-score）
        # 这样模型学习相对排名而非绝对水平
        zscore_exprs = []
        for fc in factor_cols:
            zscore_exprs.append(
                ((pl.col(fc).cast(pl.Float64) - pl.col(fc).cast(pl.Float64).mean().over("date"))
                 / (pl.col(fc).cast(pl.Float64).std().over("date") + 1e-10)).alias(fc)
            )
        train_df = train_df.with_columns(zscore_exprs)
        # 替换 inf/nan 为 0
        train_df = train_df.with_columns(
            [pl.when(pl.col(fc).is_finite()).then(pl.col(fc)).otherwise(0.0).alias(fc) for fc in factor_cols]
        )

        X = train_df.select(factor_cols).to_numpy()
        y = train_df["fwd_return"].to_numpy()

        # 过滤极端收益（去极值）
        y_median = float(np.median(y))
        y_mad = float(np.median(np.abs(y - y_median)))
        if y_mad > 0:
            z = 0.6745 * (y - y_median) / y_mad
            mask = np.abs(z) < 5.0
            X = X[mask]
            y = y[mask]

        if len(X) < 200:
            return None, None

        logger.info(
            f"ML训练数据: {len(X)} 样本, {X.shape[1]} 特征, "
            f"窗口=[{start_date}, {end_date}]"
        )
        return X, y

    def _build_ml_prediction_features(
        self, select_date: Any, stock_codes: list[str]
    ) -> tuple[np.ndarray | None, list[str]]:
        """构建ML预测截面特征

        取 select_date 当天或之前最近的因子截面。
        """
        factor_data = self._load_factor_data()
        if factor_data is None:
            return None, []

        if hasattr(select_date, "date"):
            select_date_obj = select_date.date()
        else:
            select_date_obj = select_date

        factor_before = factor_data.filter(
            pl.col("date").dt.date() <= select_date_obj
        )
        if len(factor_before) == 0:
            return None, []

        # 取每个 code 最新截面
        factor截面 = (
            factor_before.sort("date", descending=True)
            .group_by("code")
            .first()
        )
        factor截面 = factor截面.filter(
            pl.col("code").is_in(stock_codes)
        )

        factor_cols = [c for c in factor截面.columns if c in self.factor_names]
        factor截面 = factor截面.drop_nulls(factor_cols)

        if len(factor截面) == 0:
            return None, []

        # 截面 z-score 标准化（与训练数据一致）
        for fc in factor_cols:
            mean_val = factor截面[fc].cast(pl.Float64).mean()
            std_val = factor截面[fc].cast(pl.Float64).std()
            if std_val is not None and float(std_val) > 1e-10:
                factor截面 = factor截面.with_columns(
                    ((pl.col(fc).cast(pl.Float64) - float(mean_val)) / float(std_val)).alias(fc)
                )
            else:
                factor截面 = factor截面.with_columns(
                    pl.lit(0.0).alias(fc)
                )

        X = factor截面.select(factor_cols).to_numpy()
        codes = factor截面["code"].to_list()
        return X, codes

    def _compute_ml_scores(
        self, select_idx: int, close: pl.DataFrame, stock_codes: list[str]
    ) -> dict[str, float]:
        """ML选股：用LightGBM预测未来收益作为评分

        Returns:
            {code: predicted_return}
        """
        # 判断是否需要重训练
        need_retrain = (
            self._ml_model is None
            or (select_idx - self._ml_last_train_idx) >= self.ml_retrain_freq
        )

        if need_retrain:
            try:
                X, y = self._build_ml_training_data(select_idx, close, stock_codes)
            except Exception as e:
                logger.warning(f"ML训练数据构建失败: {e}")
                return {}
            if X is None or len(X) < 200:
                logger.warning("ML训练数据不足，回退到因子评分")
                return {}

            try:
                import lightgbm as lgb

                self._ml_model = lgb.LGBMRegressor(
                    n_estimators=self.ml_n_estimators,
                    max_depth=self.ml_max_depth,
                    learning_rate=self.ml_learning_rate,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    verbose=-1,
                    n_jobs=-1,
                )
                self._ml_model.fit(X, y)
                self._ml_last_train_idx = select_idx
                logger.info(
                    f"ML模型训练完成: {self.ml_n_estimators} 树, "
                    f"深度={self.ml_max_depth}"
                )
            except Exception as e:
                logger.warning(f"ML训练失败: {e}")
                return {}

        # 构建预测特征
        select_date = close.row(select_idx, named=True).get("date")
        X_pred, pred_codes = self._build_ml_prediction_features(
            select_date, stock_codes
        )
        if X_pred is None or len(X_pred) == 0:
            return {}

        scores = self._ml_model.predict(X_pred)
        return {code: float(s) for code, s in zip(pred_codes, scores)}

    def select(
        self,
        factors: dict[str, pl.DataFrame],
        ic_df: pl.DataFrame,
        stock_codes: list[str],
        current_idx: int,
        close: pl.DataFrame,
        regime: str | None = None,
        strong_factors: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, float] | None:
        """行业轮动选股

        Args: 见 BaseSelector.select
        Returns: {code: weight} 或 None
        """
        # 数据不足，跳过（多预留1天避免前视偏差：用 t-1 截面选股，t 日持有）
        select_idx = current_idx - 1
        if select_idx < self.momentum_long + 1:
            return None

        industry_map = self._load_industry_map()
        if not industry_map:
            return None

        # 大盘趋势过滤（用 t-1 数据判断）
        market_scale = 1.0
        if self.market_filter:
            market_scale = self._compute_market_scale(select_idx, close)
            if market_scale <= 0.0:
                logger.debug(f"大盘跌破长期均线，空仓 @ idx={current_idx}")
                return {}  # 空仓（明确返回空dict，区别于None=数据不足跳过）
        # v52: 更新当前market_scale供因子评分使用（regime-aware IC）
        self._current_market_scale = market_scale

        # 计算短期/长期动量（基于 close）
        close_cols = [c for c in close.columns if c != "date"]
        close_numeric = close.select(close_cols)
        mom_short = close_numeric / close_numeric.shift(self.momentum_short) - 1
        mom_long = close_numeric / close_numeric.shift(self.momentum_long) - 1

        if select_idx >= len(mom_short):
            return None

        # 残差动量（华泰金工）：剔除市场Beta暴露后的特异性动量
        # residual_return = stock_return - raw_beta * market_return
        if self.use_residual_momentum:
            short_row, long_row = self._compute_residual_momentum(
                select_idx, close, stock_codes, mom_short, mom_long
            )
        else:
            # 取昨日截面动量（防前视偏差：t-1 日选股，t 日持有赚 close[t]/close[t-1]-1）
            short_row = mom_short.row(select_idx, named=True)
            long_row = mom_long.row(select_idx, named=True)

        # 计算每只股票的综合动量 + 行业归属
        # short_row/long_row 既可以是 dict（残差动量）也可以是 named_row（简单动量）
        stock_momentum: dict[str, float] = {}
        stock_industry: dict[str, str] = {}
        for code in stock_codes:
            if code not in industry_map:
                continue
            s = short_row.get(code)
            l = long_row.get(code)
            if s is None or l is None:
                continue
            if isinstance(s, (int, float)) and isinstance(l, (int, float)):
                if not (np.isnan(s) or np.isnan(l)):
                    stock_momentum[code] = (
                        self.weight_short * float(s) + self.weight_long * float(l)
                    )
                    stock_industry[code] = industry_map[code]

        if not stock_momentum:
            return None

        # 按行业分组，计算行业平均动量
        industry_stocks: dict[str, list[str]] = {}
        industry_momentum_sum: dict[str, float] = {}
        for code, mom in stock_momentum.items():
            ind = stock_industry[code]
            industry_stocks.setdefault(ind, []).append(code)
            industry_momentum_sum[ind] = industry_momentum_sum.get(ind, 0.0) + mom

        # 行业平均动量
        industry_momentum: dict[str, float] = {
            ind: industry_momentum_sum[ind] / len(industry_stocks[ind])
            for ind in industry_stocks
        }

        # 选 Top-N 行业
        sorted_industries = sorted(
            industry_momentum.items(), key=lambda x: x[1], reverse=True
        )
        top_industries = [ind for ind, _ in sorted_industries[: self.top_industries]]

        if not top_industries:
            return None

        # RRG 行业选择：用相对强度（RS-Ratio）+ 相对强度动量（RS-Momentum）替代绝对动量
        # 研报参考：2026 量化轮动策略报告（RRG 框架下行业轮动）
        # 核心：RS-Momentum 是先行指标，能在行业绝对动量仍正但相对强度已转弱时提前剔除
        # 解决 v8 OOS 6/22 选了电子/通信/建筑材料（绝对动量仍正但7月下跌）的问题
        rrg_table = None
        select_date_obj = None
        if self.use_rrg:
            rrg_table = self._compute_rrg_table(close)
            if rrg_table is not None:
                # 取 select_idx 对应日期
                select_date_raw = close.row(select_idx, named=True).get("date")
                if hasattr(select_date_raw, "date"):
                    select_date_obj = select_date_raw.date()
                else:
                    select_date_obj = select_date_raw

                # 取该日所有行业的 RRG 数据
                # 多周期模式下过滤任一 RS-Mom 列非null，单周期模式保持原逻辑
                rrg_mom_cols = [
                    c for c in rrg_table.columns
                    if c.startswith("rs_momentum")
                ]
                if len(rrg_mom_cols) > 1:
                    # 多周期：任一列非null即可
                    null_filter = pl.col("rs_ratio").is_not_null()
                    for c in rrg_mom_cols:
                        null_filter = null_filter & pl.col(c).is_not_null()
                    rrg_at_date = rrg_table.filter(
                        (pl.col("date").cast(pl.Date) == select_date_obj)
                        & null_filter
                    )
                else:
                    rrg_at_date = rrg_table.filter(
                        (pl.col("date").cast(pl.Date) == select_date_obj)
                        & pl.col("rs_ratio").is_not_null()
                        & pl.col("rs_momentum").is_not_null()
                    )

                if len(rrg_at_date) > 0:
                    # 步骤1: 按 RS-Ratio 降序取候选（扩大候选池到 top_industries × 2）
                    rrg_sorted = rrg_at_date.sort("rs_ratio", descending=True)
                    candidate_n = min(
                        len(rrg_sorted),
                        self.top_industries * 2,
                    )
                    rrg_candidates = rrg_sorted.head(candidate_n)

                    # 步骤2: 从候选中筛选领先行业
                    # 多周期投票模式：要求 >= vote_threshold 个窗口的 RS-Mom >= 阈值
                    # 单周期模式：保持向后兼容，要求 rs_momentum >= 阈值
                    if len(rrg_mom_cols) > 1:
                        # 多周期投票
                        if (
                            self.rs_momentum_vote_weights
                            and len(self.rs_momentum_vote_weights) == len(rrg_mom_cols)
                        ):
                            # v40 加权投票：weighted_vote = sum(w_i * (RS-Mom_i≥100))
                            # 阈值改为0.5（默认），表示权重和需超过0.5
                            # 例如权重[0.5,0.3,0.2]：
                            #   - 仅10日领先：0.5 = 阈值，入选（短期主导）
                            #   - 仅30日领先：0.3 < 0.5，不入选
                            #   - 10+30日领先：0.8 > 0.5，入选
                            #   - 10+60日领先：0.7 > 0.5，入选
                            #   - 30+60日领先：0.5 = 阈值，入选
                            vote_weight_threshold = float(self.rs_momentum_vote_threshold) / len(rrg_mom_cols) if self.rs_momentum_vote_threshold >= len(rrg_mom_cols) else 0.5
                            vote_weight_threshold = max(vote_weight_threshold, 0.5)  # 至少0.5
                            vote_exprs = [
                                (
                                    pl.col(c) >= self.rrg_momentum_threshold
                                ).cast(pl.Float64) * w
                                for c, w in zip(rrg_mom_cols, self.rs_momentum_vote_weights)
                            ]
                            rrg_candidates = rrg_candidates.with_columns(
                                sum(vote_exprs).alias("weighted_vote")
                            )

                            # v43 PE调节RRG投票：在weighted_vote上叠加PE调节项
                            # adjusted_vote = weighted_vote + alpha * (ep_percentile - 0.5)
                            # 便宜行业（ep_percentile高）加分，昂贵行业（ep_percentile低）减分
                            if self.use_pe_adjusted_rrg_vote:
                                # v45 regime-aware: 趋势市(market_scale>=1.0)用alpha，
                                # 震荡市(market_scale<1.0)用alpha_choppy（若配置）
                                if (
                                    self.pe_vote_adjust_alpha_choppy is not None
                                    and market_scale < 1.0
                                ):
                                    effective_alpha = self.pe_vote_adjust_alpha_choppy
                                    regime_label = "震荡市"
                                else:
                                    effective_alpha = self.pe_vote_adjust_alpha
                                    regime_label = "趋势市"

                                # v47: 计算总估值调节项（E/P + B/P双估值）
                                total_adjustments: list[float] = []
                                has_any_adjustment = False

                                # E/P 调节
                                if effective_alpha > 0:
                                    pe_percentiles_v43 = self._compute_industry_pe_percentile(
                                        select_idx, close,
                                        rrg_candidates["industry"].to_list(),
                                        industry_stocks,
                                    )
                                    ep_adjustments = [
                                        float(
                                            effective_alpha
                                            * (pe_percentiles_v43.get(ind, 0.5) - 0.5)
                                        )
                                        for ind in rrg_candidates["industry"].to_list()
                                    ]
                                    has_any_adjustment = True
                                else:
                                    ep_adjustments = [0.0] * len(rrg_candidates)

                                # B/P 调节（v47 NEW，与E/P独立，不受regime影响）
                                if self.pe_vote_adjust_alpha_pb > 0:
                                    pb_percentiles = self._compute_industry_pe_percentile(
                                        select_idx, close,
                                        rrg_candidates["industry"].to_list(),
                                        industry_stocks,
                                        factor_name=self.pb_factor,
                                    )
                                    bp_adjustments = [
                                        float(
                                            self.pe_vote_adjust_alpha_pb
                                            * (pb_percentiles.get(ind, 0.5) - 0.5)
                                        )
                                        for ind in rrg_candidates["industry"].to_list()
                                    ]
                                    has_any_adjustment = True
                                else:
                                    bp_adjustments = [0.0] * len(rrg_candidates)

                                # 合并 E/P + B/P 调节项
                                if has_any_adjustment:
                                    total_adjustments = [
                                        ep + bp
                                        for ep, bp in zip(ep_adjustments, bp_adjustments)
                                    ]
                                    rrg_candidates = rrg_candidates.with_columns(
                                        pl.Series("pe_adjustment", total_adjustments, dtype=pl.Float64)
                                    ).with_columns(
                                        (pl.col("weighted_vote") + pl.col("pe_adjustment")).alias("weighted_vote")
                                    )
                                    logger.debug(
                                        f"v43/v45/v47 估值调节RRG投票: {regime_label} "
                                        f"alpha_ep={effective_alpha}, alpha_bp={self.pe_vote_adjust_alpha_pb}, "
                                        f"调节范围=[{min(total_adjustments):.3f}, {max(total_adjustments):.3f}]"
                                    )

                            leading = rrg_candidates.filter(
                                pl.col("weighted_vote") >= vote_weight_threshold
                            )
                            leading = leading.sort(
                                ["weighted_vote", "rs_ratio"], descending=[True, True]
                            )
                            logger.debug(
                                f"RRG加权投票: weights={self.rs_momentum_vote_weights}, "
                                f"threshold={vote_weight_threshold:.2f}"
                            )
                        else:
                            # v30 等权投票：vote_count = sum((RS-Mom_i≥100))
                            vote_exprs = [
                                (
                                    pl.col(c) >= self.rrg_momentum_threshold
                                ).cast(pl.Int32)
                                for c in rrg_mom_cols
                            ]
                            rrg_candidates = rrg_candidates.with_columns(
                                sum(vote_exprs).alias("vote_count")
                            )
                            leading = rrg_candidates.filter(
                                pl.col("vote_count") >= self.rs_momentum_vote_threshold
                            )
                            leading = leading.sort(
                                ["vote_count", "rs_ratio"], descending=[True, True]
                            )
                    else:
                        # 单周期模式
                        leading = rrg_candidates.filter(
                            pl.col("rs_momentum") >= self.rrg_momentum_threshold
                        )

                    # 步骤3: 至少保留 rrg_min_industries 个，不足时按 RS-Ratio 排名补充
                    if len(leading) >= self.rrg_min_industries:
                        new_top = leading["industry"].to_list()[
                            : self.top_industries
                        ]
                    else:
                        # 不足时用 RS-Ratio 排名（绝对强度优先）
                        new_top = rrg_sorted["industry"].to_list()[
                            : self.top_industries
                        ]

                    if new_top:
                        removed_by_rrg = set(top_industries) - set(new_top)
                        added_by_rrg = set(new_top) - set(top_industries)
                        if removed_by_rrg or added_by_rrg:
                            logger.info(
                                f"RRG 行业重选: 剔除绝对动量入选但相对强度转弱的 "
                                f"{list(removed_by_rrg)}，"
                                f"新增相对强度领先的 {list(added_by_rrg)}，"
                                f"最终 Top-{self.top_industries}: {new_top}"
                            )
                        top_industries = new_top

        # 行业短期风险过滤：剔除近期下跌的行业（规避高风险板块）
        # 当行业中长期动量仍为正但短期已转负时，及时退出
        if self.industry_risk_filter and self.risk_filter_window > 0:
            mom_risk = close_numeric / close_numeric.shift(
                self.risk_filter_window
            ) - 1
            if select_idx < len(mom_risk):
                risk_row = mom_risk.row(select_idx, named=True)
                # 计算每个选中行业的短期动量
                industry_risk_mom: dict[str, float] = {}
                for ind in top_industries:
                    vals = []
                    for code in industry_stocks[ind]:
                        v = risk_row.get(code)
                        if isinstance(v, (int, float)) and not np.isnan(v):
                            vals.append(float(v))
                    industry_risk_mom[ind] = float(np.mean(vals)) if vals else 0.0
                # 过滤：仅保留短期动量非负的行业
                filtered = [
                    ind for ind in top_industries
                    if industry_risk_mom.get(ind, 0) >= 0
                ]
                # 确保至少保留 risk_filter_min_industries 个行业
                if len(filtered) < self.risk_filter_min_industries:
                    filtered = top_industries[: self.risk_filter_min_industries]
                removed = set(top_industries) - set(filtered)
                if removed:
                    logger.info(
                        f"行业风险过滤({self.risk_filter_window}日): "
                        f"剔除{len(removed)}个下跌行业 "
                        f"{[r for r in removed]}，"
                        f"保留{len(filtered)}/{self.top_industries}"
                    )
                top_industries = filtered

        # 拥挤度过滤（NEW: 华泰金工+西南证券思路）
        # 高拥挤行业（量价极度活跃）容易发生动量崩盘，应剔除
        if self.use_crowding_filter and top_industries:
            crowding_scores = self._compute_industry_crowding(
                select_idx, close, top_industries, industry_stocks
            )
            # 剔除高拥挤行业（触发数 >= crowding_min_triggers）
            filtered = [
                ind for ind in top_industries
                if crowding_scores.get(ind, 0) < self.crowding_min_triggers
            ]
            # 确保至少保留 crowding_min_industries 个行业
            if len(filtered) < self.crowding_min_industries:
                # 按拥挤度得分升序（低拥挤优先）补充
                sorted_by_crowd = sorted(
                    top_industries,
                    key=lambda x: crowding_scores.get(x, 0),
                )
                filtered = sorted_by_crowd[: self.crowding_min_industries]
            removed = set(top_industries) - set(filtered)
            if removed:
                logger.info(
                    f"拥挤度过滤(>={self.crowding_min_triggers}指标触发95%分位): "
                    f"剔除{len(removed)}个高拥挤行业 "
                    f"{[r for r in removed]}，"
                    f"保留{len(filtered)}/{len(top_industries)}"
                )
            top_industries = filtered

        # 行业估值过滤（NEW v15: 华商基金估值安全边际思路）
        # 剔除 E/P 历史分位 < pe_expensive_percentile 的行业（即 PE 处于历史高位的过贵行业）
        if self.use_pe_filter and top_industries:
            pe_percentiles = self._compute_industry_pe_percentile(
                select_idx, close, top_industries, industry_stocks
            )
            # 剔除估值过贵的行业（E/P 分位过低 = PE 过高 = 贵）
            filtered = [
                ind for ind in top_industries
                if pe_percentiles.get(ind, 0.5) >= self.pe_expensive_percentile
            ]
            # 确保至少保留 pe_min_industries 个行业
            if len(filtered) < self.pe_min_industries:
                # 按 E/P 分位降序（便宜优先）补充
                sorted_by_pe = sorted(
                    top_industries,
                    key=lambda x: pe_percentiles.get(x, 0.5),
                    reverse=True,
                )
                filtered = sorted_by_pe[: self.pe_min_industries]
            removed = set(top_industries) - set(filtered)
            if removed:
                expensive_detail = {
                    ind: f"{pe_percentiles.get(ind, 0.5):.2f}"
                    for ind in removed
                }
                logger.info(
                    f"估值过滤(E/P分位<{self.pe_expensive_percentile:.2f}视为过贵): "
                    f"剔除{len(removed)}个过贵行业 {list(removed)} "
                    f"(E/P分位: {expensive_detail})，"
                    f"保留{len(filtered)}/{len(top_industries)}"
                )
            top_industries = filtered

        # 每个选中行业选 Top-M 只股票
        # use_ml=true: 按ML预测收益排序
        # use_factors=true: 按多因子复合评分排序
        # 否则: 按个股动量排序
        stock_scores: dict[str, float] = stock_momentum  # 默认用动量
        if self.use_ml:
            ml_scores = self._compute_ml_scores(select_idx, close, stock_codes)
            if ml_scores:
                stock_scores = ml_scores
                logger.debug(f"使用ML预测评分: {len(ml_scores)} 只有评分")
            elif self.use_factors:
                # ML失败时回退到因子评分
                select_date = close.row(select_idx, named=True).get("date")
                factor_scores = self._compute_factor_scores(select_date, stock_codes, close)
                if factor_scores:
                    stock_scores = factor_scores
        elif self.use_factors:
            select_date = close.row(select_idx, named=True).get("date")
            factor_scores = self._compute_factor_scores(select_date, stock_codes, close)
            if factor_scores:
                stock_scores = factor_scores
                logger.debug(
                    f"使用多因子评分: {len(factor_scores)} 只有评分"
                )

        # 拥挤度动态分域反转（NEW v16: 西南证券思路）
        # 对高拥挤行业的股票，反转评分符号（-score），选"输家"期望反弹
        # 非拥挤行业保持动量（趋势跟踪），高拥挤行业切换到反转（均值回归）
        if self.use_crowding_reversal and top_industries:
            crowding_scores_rev = self._compute_industry_crowding(
                select_idx, close, top_industries, industry_stocks
            )
            high_crowd_industries = {
                ind for ind, score in crowding_scores_rev.items()
                if score >= self.crowding_min_triggers
            }
            if high_crowd_industries:
                # 复制评分并反转高拥挤行业的股票评分
                stock_scores = dict(stock_scores)
                reversed_count = 0
                for code in list(stock_scores.keys()):
                    ind = industry_map.get(code, "")
                    if ind in high_crowd_industries:
                        stock_scores[code] = -stock_scores[code]
                        reversed_count += 1
                logger.info(
                    f"拥挤度动态分域反转: 高拥挤行业 "
                    f"{list(high_crowd_industries)}（触发数>="
                    f"{self.crowding_min_triggers}），反转{reversed_count}只股票评分"
                )

        # 拥挤度动态分域反转因子（NEW v38: 修正v16失败实现）
        # 对高拥挤行业的股票，使用独立反转因子(BIAS20)替换原评分
        # v16失败根因：符号反转(-score)相当于选"质量差+估值贵"股票
        # v38正确做法：用独立反转因子单独评分，选"超跌"股票期望反弹
        if self.use_crowding_reversal_factor and top_industries:
            crowding_scores_v38 = self._compute_industry_crowding(
                select_idx, close, top_industries, industry_stocks
            )
            high_crowd_industries_v38 = {
                ind for ind, score in crowding_scores_v38.items()
                if score >= self.crowding_min_triggers
            }
            if high_crowd_industries_v38:
                select_date_v38 = close.row(select_idx, named=True).get("date")
                reversal_scores = self._compute_reversal_factor_scores(
                    select_date_v38, stock_codes
                )
                if reversal_scores:
                    stock_scores = dict(stock_scores)
                    replaced_count = 0
                    for code in list(stock_scores.keys()):
                        ind = industry_map.get(code, "")
                        if ind in high_crowd_industries_v38 and code in reversal_scores:
                            stock_scores[code] = reversal_scores[code]
                            replaced_count += 1
                    logger.info(
                        f"拥挤度反转因子(v38): 高拥挤行业 "
                        f"{list(high_crowd_industries_v38)}，"
                        f"用{self.crowding_reversal_factor}替换{replaced_count}只股票评分"
                    )

        selected: list[str] = []
        for ind in top_industries:
            stocks_in_ind = industry_stocks[ind]
            sorted_stocks = sorted(
                stocks_in_ind,
                key=lambda c: stock_scores.get(c, -float("inf")),
                reverse=True,
            )
            selected.extend(sorted_stocks[: self.stocks_per_industry])

        if not selected:
            return None

        n_stocks = len(selected)

        # 行业RS-Ratio加权（NEW in v19: 结构性改进）
        # 用 RS-Ratio 作为行业权重（替代等权），让长期跑赢大盘的行业权重大
        # 实现：行业权重 ∝ max(rs_ratio, 0)，归一化后应用 max_industry_weight 上限
        #       行业内股票等权分配行业权重
        # 与等权相比：能聚焦强势行业，但避免单一行业过度集中
        use_industry_rs_weight = (
            self.use_industry_weight_by_rs
            and rrg_table is not None
            and select_date_obj is not None
        )
        industry_weights: dict[str, float] | None = None
        if use_industry_rs_weight:
            try:
                rrg_at_date_w = rrg_table.filter(
                    pl.col("date").cast(pl.Date) == select_date_obj
                )
                if len(rrg_at_date_w) > 0:
                    # 获取每个入选行业的RS-Ratio
                    ind_rs = {
                        r["industry"]: float(r["rs_ratio"])
                        for r in rrg_at_date_w.iter_rows(named=True)
                        if r["industry"] in top_industries
                        and r.get("rs_ratio") is not None
                    }
                    # 只对有RS-Ratio数据的行业加权，其余行业用等权fallback
                    if len(ind_rs) == len(top_industries) and len(ind_rs) > 0:
                        # 行业权重 ∝ max(rs_ratio, 0)
                        # 注意：不应用max_industry_weight截断
                        # 因为截断+归一化会让所有行业变等权（当所有行业都>cap时）
                        # 让RS-Ratio差异自然保留，由max_stock_weight间接限制行业权重
                        raw_weights = {
                            ind: max(rs, 0.0) for ind, rs in ind_rs.items()
                        }
                        total_rs = sum(raw_weights.values())
                        if total_rs > 0:
                            industry_weights = {
                                ind: w / total_rs
                                for ind, w in raw_weights.items()
                            }
                            logger.debug(
                                f"行业RS-Ratio加权(无cap): "
                                f"{[(ind, f'{w:.3f}') for ind, w in industry_weights.items()]}"
                            )
            except Exception as e:
                logger.warning(f"行业RS-Ratio加权失败，回退等权: {e}")
                industry_weights = None

        # 逆波动率加权（风险平价）或等权
        # 参考 Risk Parity 研究：逆波动率加权降低高波动股暴露，平滑收益
        if self.use_inv_vol_weight:
            close_numeric = close.select(
                [c for c in close.columns if c != "date"]
            )
            vol_dict: dict[str, float] = {}
            for code in selected:
                prices_list = close_numeric[code].to_list()
                if len(prices_list) >= self.inv_vol_window + 1:
                    rets = [
                        prices_list[i] / prices_list[i - 1] - 1
                        for i in range(
                            len(prices_list) - self.inv_vol_window,
                            len(prices_list),
                        )
                        if prices_list[i - 1] and prices_list[i - 1] > 0
                    ]
                    vol = (
                        float(np.std(rets, ddof=1))
                        if len(rets) > 1
                        else 0.02
                    )
                    vol_dict[code] = max(vol, 0.01)
                else:
                    vol_dict[code] = 0.02
            inv_vols = {
                code: 1.0 / vol_dict[code] for code in selected
            }
            total_inv_vol = sum(inv_vols.values())
            weights = {
                code: inv_vols[code] / total_inv_vol for code in selected
            }
            logger.debug(
                f"逆波动率加权: vol范围=[{min(vol_dict.values()):.4f}, "
                f"{max(vol_dict.values()):.4f}]"
            )
        else:
            # 行业RS-Ratio加权：行业权重按RS-Ratio分配，行业内股票等权
            # 否则：所有股票等权
            if industry_weights is not None:
                weights = {}
                # 按行业分组selected股票
                selected_by_industry: dict[str, list[str]] = {
                    ind: [] for ind in top_industries
                }
                for code in selected:
                    ind = industry_map.get(code, "")
                    if ind in selected_by_industry:
                        selected_by_industry[ind].append(code)
                for ind, stocks_in_ind in selected_by_industry.items():
                    if not stocks_in_ind:
                        continue
                    ind_w = industry_weights.get(ind, 0.0)
                    # 行业内股票等权分配行业权重
                    per_stock = ind_w / len(stocks_in_ind)
                    for code in stocks_in_ind:
                        weights[code] = per_stock
            else:
                base_weight = 1.0 / n_stocks
                weights = {code: base_weight for code in selected}

        # 应用个股权重上限（逆波动率加权时跳过：风险平价本身就是风险控制，
        # 强制 cap 会将所有权重截断到上限后归一化为等权，破坏风险平价效果）
        if not self.use_inv_vol_weight:
            weights = self.apply_weight_cap(weights, self.max_stock_weight)

        # 应用大盘趋势过滤系数（降仓）
        if market_scale < 1.0:
            weights = {k: v * market_scale for k, v in weights.items()}
            logger.debug(
                f"大盘趋势过滤: 仓位×{market_scale:.1f} @ idx={current_idx}"
            )

        logger.debug(
            f"行业轮动选股: {n_stocks} 只, "
            f"行业数={len(top_industries)}, "
            f"权重范围=[{min(weights.values()):.3f}, {max(weights.values()):.3f}]"
        )
        return weights

    def select_strong_factors(
        self, ic_df: pl.DataFrame, train_end: str
    ) -> list[str]:
        """返回所有因子（行业轮动不依赖 IC 筛选）"""
        return [c for c in ic_df.columns if c != "date"]


__all__ = ["IndustryRotationSelector"]
