"""探索4张关键数据表的结构和样本数据

表：stock_hk_hold, stock_money_flow, stock_valuation, stock_industry_daily
"""
import duckdb

con = duckdb.connect()
DATA_ROOT = "D:/Work/Project/download_a_share/data"

tables = ["stock_hk_hold", "stock_money_flow", "stock_valuation", "stock_industry_daily"]

for t in tables:
    print(f"\n{'='*100}")
    print(f"表: {t}")
    print(f"{'='*100}")

    # 列结构
    con.execute(f"""
        CREATE OR REPLACE TEMP VIEW v_{t} AS
        SELECT * FROM read_parquet('{DATA_ROOT}/parquet/{t}/**/*.parquet') LIMIT 0
    """)
    cols = con.execute(f"""
        SELECT column_name, data_type FROM information_schema.columns
        WHERE table_name = 'v_{t}'
    """).fetchall()
    print(f"列数: {len(cols)}")
    for c in cols:
        print(f"  {c[0]:<45} {c[1]}")

    # 行数和时间范围
    try:
        info = con.execute(f"""
            SELECT count(*) as n,
                   min(date) as min_date,
                   max(date) as max_date,
                   count(DISTINCT code) as n_codes
            FROM read_parquet('{DATA_ROOT}/parquet/{t}/**/*.parquet')
        """).fetchone()
        print(f"\n行数: {info[0]:,}  时间: {info[1]} ~ {info[2]}  股票数: {info[3]}")
    except:
        try:
            info = con.execute(f"""
                SELECT count(*) as n,
                   min(trade_date) as min_date,
                   max(trade_date) as max_date
            FROM read_parquet('{DATA_ROOT}/parquet/{t}/**/*.parquet')
            """).fetchone()
            print(f"\n行数: {info[0]:,}  时间: {info[1]} ~ {info[2]}")
        except Exception as e:
            print(f"  统计失败: {e}")

    # 样本数据
    try:
        sample = con.execute(f"""
            SELECT * FROM read_parquet('{DATA_ROOT}/parquet/{t}/**/*.parquet')
            WHERE date >= '2025-01-01'
            LIMIT 3
        """).fetchdf()
        print(f"\n样本数据（2025年后）:")
        print(sample.to_string())
    except:
        try:
            sample = con.execute(f"""
                SELECT * FROM read_parquet('{DATA_ROOT}/parquet/{t}/**/*.parquet')
                LIMIT 3
            """).fetchdf()
            print(f"\n样本数据:")
            print(sample.to_string())
        except Exception as e:
            print(f"  样本失败: {e}")
