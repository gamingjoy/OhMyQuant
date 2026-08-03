"""列出 factors_wide 表的所有列名"""
import duckdb

con = duckdb.connect()
con.execute("""
    CREATE VIEW factors_wide AS
    SELECT * FROM read_parquet('D:/Work/Project/download_a_share/data/parquet/factors_wide/**/*.parquet')
""")

cols = con.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'factors_wide' ORDER BY ordinal_position
""").fetchall()

print(f"Total columns: {len(cols)}")
for c in cols:
    print(c[0])
