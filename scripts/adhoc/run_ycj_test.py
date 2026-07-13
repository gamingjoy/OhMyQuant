"""试运行 ycj 策略 - 全流程测试"""
import sys
sys.path.insert(0, ".")

from ohmyquant.strategy.registry import StrategyRegistry
from ohmyquant.data.sources.duckdb_source import DuckDBSource
from ohmyquant.data.base import DataCatalog
from ohmyquant.engine.backtest import BacktestEngine
from ohmyquant.core.config_models import StrategyConfig

# 1. 创建数据源
print("=" * 60)
print("步骤1: 创建数据源")
print("=" * 60)
source = DuckDBSource({"data_root": "D:/Work/Project/download_a_share/data"})
catalog = DataCatalog(source)

# 获取部分股票做测试（取沪深300成分股中的前20只）
print("获取指数成分股...")
try:
    import duckdb
    con = duckdb.connect()
    df = con.execute("""
        SELECT code FROM read_parquet('D:/Work/Project/download_a_share/data/parquet/index_constituents/**/*.parquet', hive_partitioning=1)
        WHERE index_code = '000300.XSHG'
        ORDER BY date DESC
        LIMIT 30
    """).arrow()
    import polars as pl
    stocks_df = pl.from_arrow(df)
    # 转换代码格式
    test_stocks = []
    for code in stocks_df["code"].to_list():
        if code.endswith(".XSHG"):
            test_stocks.append(code.replace(".XSHG", ".SH"))
        elif code.endswith(".XSHE"):
            test_stocks.append(code.replace(".XSHE", ".SZ"))
    print(f"测试股票池: {len(test_stocks)} 只, 示例: {test_stocks[:5]}")
    con.close()
except Exception as e:
    print(f"获取成分股失败: {e}")
    test_stocks = ["000001.SZ", "000002.SZ", "600000.SH", "600519.SH", "601318.SH"]

# 2. 构建策略配置
print("\n" + "=" * 60)
print("步骤2: 构建策略配置")
print("=" * 60)
config = StrategyConfig(
    strategy_type="ycj",
    strategy_version="v1",
    strategy_name="YCJ 测试",
    backtest={
        "start_date": "2024-01-01",
        "end_date": "2024-06-30",
        "data_start_date": "2023-01-01",
        "transaction_cost": 0.001,
    },
    selection={
        "method": "icir",
        "top_n": 10,
        "max_stock_weight": 0.1,
    },
    risk={"target_vol": 0.25},
    allocation={"method": "equal"},
    rebalance={
        "frequency": "monthly",
        "method": "cost_benefit",
        "cost_model": {"name": "stock_cn"},
    },
    data={"source": "duckdb", "data_root": "D:/Work/Project/download_a_share/data"},
    factors=["mom_1m", "mom_3m"],
    pools={"main": test_stocks},
)

print(f"策略: {config.strategy_type} {config.strategy_version}")
print(f"回测区间: {config.backtest.start_date} ~ {config.backtest.end_date}")
print(f"股票池: {len(test_stocks)} 只")
print(f"因子: {config.factors}")

# 3. 运行回测
print("\n" + "=" * 60)
print("步骤3: 运行回测")
print("=" * 60)
try:
    engine = BacktestEngine(catalog, config)
    result = engine.run(
        pools={"main": test_stocks},
        start_date="2024-01-01",
        end_date="2024-06-30",
    )

    print("\n" + "=" * 60)
    print("回测结果")
    print("=" * 60)
    print(f"回测天数: {result.n_days}")
    print(f"最终净值: {result.final_nav:.4f}")
    print(f"调仓次数: {len(result.pool_weight_log)}")

    # 计算绩效指标
    if result.daily_returns is not None and len(result.daily_returns) > 0:
        import numpy as np
        returns = np.array(result.daily_returns.to_list())
        from ohmyquant.analysis.metrics import compute_metrics, print_metrics
        metrics = compute_metrics(returns)
        print_metrics(metrics)

    print("\n试运行成功!")

except Exception as e:
    import traceback
    print(f"回测失败: {e}")
    traceback.print_exc()
