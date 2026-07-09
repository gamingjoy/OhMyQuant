"""回测模块测试

测试回测功能：
  - 回测引擎
  - 成本模型
  - 执行器
  - 结果处理
"""
import numpy as np
import pytest

from ohmyquant.engine.backtest import BacktestEngine
from ohmyquant.execution.cost_model import StockCostModel, ETFCostModel, create_cost_model
from ohmyquant.execution.executor import SimulatedExecutor


class TestCostModel:
    """成本模型测试"""

    def test_stock_cost_model(self):
        """测试 A 股成本模型"""
        cost_model = StockCostModel()
        buy_cost = cost_model.buy_cost(0.1)
        sell_cost = cost_model.sell_cost(0.1)
        assert buy_cost > 0
        assert sell_cost > buy_cost

    def test_etf_cost_model(self):
        """测试 ETF 成本模型"""
        cost_model = ETFCostModel()
        buy_cost = cost_model.buy_cost(0.1)
        sell_cost_short = cost_model.sell_cost(0.1, hold_days=3)
        sell_cost_long = cost_model.sell_cost(0.1, hold_days=10)
        assert sell_cost_short > sell_cost_long

    def test_create_cost_model(self):
        """测试创建成本模型"""
        model = create_cost_model({"name": "stock_cn"})
        assert isinstance(model, StockCostModel)

        model = create_cost_model({"name": "etf_cn"})
        assert isinstance(model, ETFCostModel)


class TestExecutor:
    """执行器测试"""

    def test_executor_init(self):
        """测试执行器初始化"""
        executor = SimulatedExecutor()
        assert executor is not None


class TestBacktestEngine:
    """回测引擎测试"""

    def test_engine_class_exists(self):
        """测试回测引擎类存在"""
        assert BacktestEngine is not None
