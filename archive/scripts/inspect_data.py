"""Inspect data and factors on disk."""
import polars as pl
from pathlib import Path

DATA_ROOT = Path("D:/Work/Project/download_a_share/data")

print("=" * 60)
print("1. factors_wide content (only 2005 and 2026 exist)")
print("=" * 60)
for year in [2005, 2026]:
    fp = DATA_ROOT / f"parquet/factors_wide/year={year}/data.parquet"
    if fp.exists():
        df = pl.read_parquet(fp)
        print(f"Year {year}: rows={len(df)}, cols={len(df.columns)}")
        if len(df) > 0:
            print(f"  date range: {df['date'].min()} to {df['date'].max()}")
            print(f"  cols (first 15): {df.columns[:15]}")

print()
print("=" * 60)
print("2. Pre-computed factors directory (sample)")
print("=" * 60)
factors_dir = DATA_ROOT / "parquet/factors"
factor_subdirs = sorted([d.name for d in factors_dir.iterdir() if d.is_dir()])
print(f"Total factor dirs: {len(factor_subdirs)}")
print(f"First 30 factors: {factor_subdirs[:30]}")

# Check year coverage for a few factors
print()
print("Year coverage per factor (sample of 8):")
sample_factors = ["beta", "BIAS20", "RSI", "VOL20", "mom_1m", "pe_ttm", "turnover_20d", "ACCA"]
# Pick factors that exist
sample_factors = [f for f in sample_factors if f in factor_subdirs]
if not sample_factors:
    sample_factors = factor_subdirs[:8]

for fname in sample_factors:
    fdir = factors_dir / fname
    years = sorted([d.name for d in fdir.iterdir() if d.is_dir()])
    # Check first and last year file sizes
    print(f"  {fname}: {len(years)} years, range={years[0] if years else 'N/A'} to {years[-1] if years else 'N/A'}")
    if years:
        first_file = fdir / years[0] / "data.parquet"
        last_file = fdir / years[-1] / "data.parquet"
        try:
            df_first = pl.read_parquet(first_file)
            df_last = pl.read_parquet(last_file)
            print(f"    {years[0]}: rows={len(df_first)}, cols={df_first.columns}")
            print(f"    {years[-1]}: rows={len(df_last)}")
            if len(df_first) > 0:
                print(f"    sample row: {df_first.head(1).to_dicts()[0]}")
        except Exception as e:
            print(f"    Error: {e}")

print()
print("=" * 60)
print("3. Stock wide table schema (year=2024)")
print("=" * 60)
stock_wide = DATA_ROOT / "stock_daily_wide_partitioned/year=2024/data.parquet"
if stock_wide.exists():
    df = pl.read_parquet(stock_wide)
    print(f"Rows: {len(df)}, Cols: {len(df.columns)}")
    print(f"All columns: {df.columns}")
    print(f"Date range: {df['date'].min()} to {df['date'].max()}")
    print(f"Unique codes: {df['code'].n_unique()}")
    print(f"Sample row: {df.head(1).to_dicts()[0]}")

print()
print("=" * 60)
print("4. Stock wide table year coverage")
print("=" * 60)
stock_years_dir = DATA_ROOT / "stock_daily_wide_partitioned"
years = sorted([d.name for d in stock_years_dir.iterdir() if d.is_dir()])
print(f"Years: {years}")

print()
print("=" * 60)
print("5. Check 2026 data extent")
print("=" * 60)
fp_2026 = DATA_ROOT / "stock_daily_wide_partitioned/year=2026/data.parquet"
if fp_2026.exists():
    df = pl.read_parquet(fp_2026)
    print(f"2026: rows={len(df)}, date range: {df['date'].min()} to {df['date'].max()}")
    print(f"Unique codes: {df['code'].n_unique()}")

print()
print("=" * 60)
print("6. Index constituents (CSI 300)")
print("=" * 60)
ic_dir = DATA_ROOT / "parquet/index_constituents"
if ic_dir.exists():
    files = list(ic_dir.rglob("*.parquet"))
    print(f"Files: {len(files)}")
    if files:
        df = pl.read_parquet(files[0])
        print(f"First file: {files[0].name}")
        print(f"Rows: {len(df)}, Cols: {df.columns}")
        print(df.head(3))
