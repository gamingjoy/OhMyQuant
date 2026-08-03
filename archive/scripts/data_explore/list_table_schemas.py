"""列出所有parquet表的列名和行数"""
import duckdb

con = duckdb.connect()

tables = [
    "stock_hk_hold", "stock_margin_trading", "stock_money_flow",
    "stock_billboard", "stock_locked_shares", "stock_valuation",
    "stock_concept", "stock_st_status", "stock_industry_daily",
    "stock_income", "stock_balance", "stock_cash_flow", "stock_indicator",
    "etf_daily_price", "etf_portfolio_stock", "etf_share",
    "stock_daily_price", "index_daily_price", "security_info",
    "stock_industry",
]

for t in tables:
    try:
        cols = con.execute(f"""
                SELECT column_name, data_type FROM information_schema.columns
                WHERE table_name = 'temp_{t}'
            """).fetchall()

        if not cols:
            # 创建临时视图
            con.execute(f"""
                CREATE OR REPLACE VIEW temp_{t} AS
                SELECT * FROM read_parquet('D:/Work/Project/download_a_share/data/parquet/{t}/**/*.parquet')
                LIMIT 0
            """)
            cols = con.execute(f"""
                SELECT column_name, data_type FROM information_schema.columns
                WHERE table_name = 'temp_{t}'
            """).fetchall()

        # 获取行数和时间范围
        try:
            count = con.execute(f"""
                SELECT count(*) FROM read_parquet('D:/Work/Project/download_a_share/data/parquet/{t}/**/*.parquet')
            """).fetchone()[0]
        except:
            count = -1

        date_col = None
        for c in cols:
            if c[0] in ("date", "trade_date", "day"):
                date_col = c[0]
                break

        if date_col and count > 0:
            try:
                rng = con.execute(f"""
                    SELECT min({date_col}), max({date_col})
                    FROM read_parquet('D:/Work/Project/download_a_share/data/parquet/{t}/**/*.parquet')
                """).fetchone()
                date_range = f"{rng[0]} ~ {rng[1]}"
            except:
                date_range = "N/A"
        else:
            date_range = "N/A"

        print(f"\n{'='*80}")
        print(f"表: {t}  行数: {count:,}  时间: {date_range}")
        print(f"{'='*80}")
        for c in cols:
            print(f"  {c[0]:<40} {c[1]}")
    except Exception as e:
        print(f"\n表: {t}  错误: {e}")
