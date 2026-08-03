"""ths_utils 单元测试

测试 ohmyquant.execution.ths_utils 中的通用函数:
  - compute_lot_shares: 整手股数计算
  - generate_trades: 建仓/调仓交易流水生成
  - write_xlsx: xlsx 写入(需模板,仅集成测试)
  - get_open_prices / replay_history: 需数据源,仅接口测试
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ohmyquant.execution.ths_utils import (
    CAPITAL,
    LOT_SIZE,
    TRANSACTION_COST_RATE,
    compute_lot_shares,
    generate_trades,
    get_open_prices,
    replay_history,
    write_xlsx,
)


class TestConstants:
    """常量定义测试"""

    def test_capital_positive(self):
        assert CAPITAL > 0

    def test_lot_size_positive(self):
        assert LOT_SIZE > 0

    def test_cost_rate_in_range(self):
        assert 0 < TRANSACTION_COST_RATE < 0.01


class TestComputeLotShares:
    """compute_lot_shares 函数测试"""

    def test_basic_case(self):
        """10% 权重, 10元价格, 1000万资金 → 10000 股"""
        shares = compute_lot_shares(10_000_000, 0.1, 10.0)
        assert shares == 100_000  # 10% * 10M / 10 = 100000

    def test_lot_size_alignment(self):
        """结果必须是 LOT_SIZE 的整数倍"""
        shares = compute_lot_shares(10_000_000, 0.123, 25.6)
        assert shares % LOT_SIZE == 0

    def test_zero_price(self):
        """价格为 0 返回 0"""
        assert compute_lot_shares(10_000_000, 0.1, 0) == 0

    def test_negative_price(self):
        """价格为负返回 0"""
        assert compute_lot_shares(10_000_000, 0.1, -5.0) == 0

    def test_zero_weight(self):
        """权重为 0 返回 0"""
        assert compute_lot_shares(10_000_000, 0.0, 10.0) == 0

    def test_custom_lot_size(self):
        """自定义整手大小"""
        shares = compute_lot_shares(1_000_000, 0.5, 10.0, lot_size=500)
        assert shares % 500 == 0
        assert shares == 50_000


class TestGenerateTrades:
    """generate_trades 函数测试"""

    def test_build_basic(self):
        """建仓: 2 只股票, 简单权重"""
        target = {"000001": 0.5, "000002": 0.5}
        prices = {"000001": 10.0, "000002": 20.0}
        trades, shares, cash = generate_trades(
            "2026-06-01", {}, target, prices, 10_000_000,
            is_build=True, strategy_name="test",
        )
        assert len(trades) == 2
        assert all(t["业务类型"] == "买入" for t in trades)
        assert shares["000001"] > 0
        assert shares["000002"] > 0
        assert cash < 10_000_000  # 现金减少

    def test_build_missing_price(self):
        """建仓: 缺失价格的股票跳过"""
        target = {"000001": 0.5, "000002": 0.5}
        prices = {"000001": 10.0}  # 000002 缺失
        trades, shares, cash = generate_trades(
            "2026-06-01", {}, target, prices, 10_000_000,
            is_build=True,
        )
        assert len(trades) == 1
        assert "000002" not in shares

    def test_rebalance_sell_then_buy(self):
        """调仓: 先卖后买"""
        prev = {"000001": 100_000, "000002": 50_000}
        target = {"000001": 0.3, "000003": 0.7}  # 减仓001, 清仓002, 买入003
        prices = {"000001": 10.0, "000002": 20.0, "000003": 15.0}
        trades, shares, cash = generate_trades(
            "2026-06-08", prev, target, prices, 0,
            is_build=False, capital=10_000_000,
        )
        sell_trades = [t for t in trades if t["业务类型"] == "卖出"]
        buy_trades = [t for t in trades if t["业务类型"] == "买入"]
        assert len(sell_trades) > 0  # 有卖出
        assert len(buy_trades) > 0   # 有买入
        assert "000002" not in shares  # 002 被清仓

    def test_trade_fields(self):
        """交易字段完整性"""
        target = {"000001": 1.0}
        prices = {"000001": 10.0}
        trades, _, _ = generate_trades(
            "2026-06-01", {}, target, prices, 10_000_000, is_build=True,
        )
        t = trades[0]
        required_keys = {"交易日期", "证券代码", "业务类型", "数量", "价格",
                         "成交金额", "费用", "证券类型", "说明"}
        assert set(t.keys()) == required_keys
        assert isinstance(t["交易日期"], datetime)
        assert t["证券类型"] == "A股"

    def test_cost_calculation(self):
        """交易费用计算正确"""
        target = {"000001": 1.0}
        prices = {"000001": 10.0}
        trades, _, _ = generate_trades(
            "2026-06-01", {}, target, prices, 10_000_000,
            is_build=True, cost_rate=0.001,
        )
        t = trades[0]
        expected_cost = t["成交金额"] * 0.001
        assert abs(t["费用"] - round(expected_cost, 2)) < 0.01


class TestGetOpenPrices:
    """get_open_prices 函数测试(用 mock 数据源)"""

    @patch("ohmyquant.execution.ths_utils.DuckDBSource")
    def test_basic_fetch(self, mock_source_cls):
        """正常获取开盘价"""
        mock_source = MagicMock()
        mock_source.load_daily_price.return_value = MagicMock(
            iter_rows=lambda: [
                {"code": "000001", "open": 10.5},
                {"code": "000002", "open": 20.3},
            ]
        )
        result = get_open_prices(mock_source, ["000001", "000002"], "2026-06-01")
        assert result["000001"] == 10.5
        assert result["000002"] == 20.3

    @patch("ohmyquant.execution.ths_utils.DuckDBSource")
    def test_empty_codes(self, mock_source_cls):
        """空股票列表"""
        mock_source = MagicMock()
        mock_source.load_daily_price.return_value = MagicMock(iter_rows=lambda: [])
        result = get_open_prices(mock_source, [], "2026-06-01")
        assert result == {}


class TestReplayHistory:
    """replay_history 函数测试(用 mock)"""

    @patch("ohmyquant.execution.ths_utils.get_open_prices")
    def test_empty_log(self, mock_prices):
        """空调仓日志返回初始状态"""
        mock_source = MagicMock()
        shares, cash = replay_history(mock_source, [], "2026-06-01")
        assert shares == {}
        assert cash == CAPITAL

    @patch("ohmyquant.execution.ths_utils.get_open_prices")
    def test_single_build(self, mock_prices):
        """单次建仓"""
        mock_prices.return_value = {"000001": 10.0}
        mock_source = MagicMock()
        log = [{"date": "2026-06-01", "holdings": {"000001": 1.0}}]
        shares, cash = replay_history(mock_source, log, "2026-06-08")
        assert "000001" in shares
        assert shares["000001"] > 0
        assert cash < CAPITAL  # 现金减少


class TestWriteXlsx:
    """write_xlsx 函数测试(集成测试,需模板)"""

    def test_write_with_template(self, tmp_path):
        """写入 xlsx(需模板存在)"""
        template = Path("templates/ths_pms_template.xlsx")
        if not template.exists():
            pytest.skip("同花顺模板不存在,跳过集成测试")

        trades = [{
            "交易日期": datetime(2026, 6, 1),
            "证券代码": "000001",
            "业务类型": "买入",
            "数量": 1000,
            "价格": 10.0,
            "成交金额": 10000.0,
            "费用": 10.0,
            "证券类型": "A股",
            "说明": "测试",
        }]
        output = tmp_path / "test.xlsx"
        write_xlsx(trades, output, template)
        assert output.exists()

    def test_write_empty_trades(self, tmp_path):
        """空交易列表"""
        template = Path("templates/ths_pms_template.xlsx")
        if not template.exists():
            pytest.skip("同花顺模板不存在,跳过集成测试")

        output = tmp_path / "empty.xlsx"
        write_xlsx([], output, template)
        assert output.exists()
