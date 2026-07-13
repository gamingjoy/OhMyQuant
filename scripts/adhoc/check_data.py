"""检查数据目录内容"""
import duckdb
import polars as pl

con = duckdb.connect()

# 检查股票宽表
print("=" * 60)
print("股票宽表 (stock_daily_wide_partitioned)")
print("=" * 60)
try:
    df = con.execute("""
        SELECT COUNT(*) as cnt, MIN(date) as min_date, MAX(date) as max_date,
               COUNT(DISTINCT code) as n_codes
        FROM read_parquet('D:/Work/Project/download_a_share/data/stock_daily_wide_partitioned/**/*.parquet', hive_partitioning=1)
    """).arrow()
    print(pl.from_arrow(df))
except Exception as e:
    print(f"错误: {e}")

# 检查 ETF 宽表
print("\n" + "=" * 60)
print("ETF 宽表 (etf_daily_wide_partitioned)")
print("=" * 60)
try:
    df = con.execute("""
        SELECT COUNT(*) as cnt, MIN(date) as min_date, MAX(date) as max_date,
               COUNT(DISTINCT code) as n_codes
        FROM read_parquet('D:/Work/Project/download_a_share/data/etf_daily_wide_partitioned/**/*.parquet', hive_partitioning=1)
    """).arrow()
    print(pl.from_arrow(df))
except Exception as e:
    print(f"错误: {e}")

# 检查因子宽表
print("\n" + "=" * 60)
print("因子宽表 (factors_wide)")
print("=" * 60)
try:
    df = con.execute("""
        SELECT COUNT(*) as cnt, MIN(date) as min_date, MAX(date) as max_date
        FROM read_parquet('D:/Work/Project/download_a_share/data/parquet/factors_wide/**/*.parquet', hive_partitioning=1)
    """).arrow()
    print(pl.from_arrow(df))
except Exception as e:
    print(f"错误: {e}")

# 检查指数成分股
print("\n" + "=" * 60)
print("指数成分股 (index_constituents)")
print("=" * 60)
try:
    df = con.execute("""
        SELECT COUNT(*) as cnt, COUNT(DISTINCT code) as n_codes,
               MIN(date) as min_date, MAX(date) as max_date
        FROM read_parquet('D:/Work/Project/download_a_share/data/parquet/index_constituents/**/*.parquet', hive_partitioning=1)
    """).arrow()
    print(pl.from_arrow(df))
except Exception as e:
    print(f"错误: {e}")

# 检查交易日历
print("\n" + "=" * 60)
print("交易日历 (trade_calendar)")
print("=" * 60)
try:
    df = con.execute("""
        SELECT COUNT(*) as cnt, MIN(date) as min_date, MAX(date) as max_date,
               SUM(CASE WHEN is_trade_day = true THEN 1 ELSE 0 END) as trade_days
        FROM read_parquet('D:/Work/Project/download_a_share/data/parquet/trade_calendar/**/*.parquet', hive_partitioning=1)
    """).arrow()
    print(pl.from_arrow(df))
except Exception as e:
    print(f"错误: {e}")

# 检查指数行情
print("\n" + "=" * 60)
print("指数行情 (index_daily_price)")
print("=" * 60)
try:
    df = con.execute("""
        SELECT COUNT(DISTINCT code) as n_codes, MIN(date) as min_date, MAX(date) as max_date
        FROM read_parquet('D:/Work/Project/download_a_share/data/parquet/index_daily_price/**/*.parquet', hive_partitioning=1)
    """).arrow()
    print(pl.from_arrow(df))
except Exception as e:
    print(f"错误: {e}")

con.close()
