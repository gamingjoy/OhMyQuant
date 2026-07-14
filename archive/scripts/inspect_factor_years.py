"""Check factor year coverage and rebalance schedule."""
import polars as pl
from pathlib import Path
from collections import Counter

DATA_ROOT = Path("D:/Work/Project/download_a_share/data")

print("=" * 60)
print("1. Year coverage across ALL 260 pre-computed factors")
print("=" * 60)
factors_dir = DATA_ROOT / "parquet/factors"
factor_subdirs = sorted([d for d in factors_dir.iterdir() if d.is_dir()])

# Count how many factors have each year
year_factor_count = Counter()
factor_year_sets = {}
for fdir in factor_subdirs:
    years = sorted([d.name.replace("year=", "") for d in fdir.iterdir() if d.is_dir()])
    factor_year_sets[fdir.name] = set(years)
    for y in years:
        year_factor_count[y] += 1

print("Year -> # factors available that year:")
for y in sorted(year_factor_count.keys()):
    print(f"  {y}: {year_factor_count[y]} / {len(factor_subdirs)} factors")

# Find years where most factors have data
full_years = [y for y, c in year_factor_count.items() if c >= 250]
print(f"\nYears with >=250 factors (near-complete): {full_years}")

# Find common years across ALL factors
if factor_year_sets:
    common_years = set.intersection(*factor_year_sets.values())
    print(f"Years common to ALL {len(factor_subdirs)} factors: {sorted(common_years)}")

# Show a few factors with their exact year sets
print("\nSample factor year sets:")
for fname in ["beta", "BIAS20", "VOL20", "ACCA", "mom_1m", "pe_ttm", "DIVIDENDYIELD"]:
    if fname in factor_year_sets:
        print(f"  {fname}: {sorted(factor_year_sets[fname])}")

print()
print("=" * 60)
print("2. Check factors_wide for ALL years (maybe more exist)")
print("=" * 60)
fw_dir = DATA_ROOT / "parquet/factors_wide"
fw_years = sorted([d.name for d in fw_dir.iterdir() if d.is_dir()])
print(f"factors_wide years present: {fw_years}")

print()
print("=" * 60)
print("3. Monthly rebalance dates check (June-July 2026)")
print("=" * 60)
# Check what dates are first trading day of month in 2026
fp_2026 = DATA_ROOT / "stock_daily_wide_partitioned/year=2026/data.parquet"
df = pl.read_parquet(fp_2026, columns=["date"])
df = df.with_columns(pl.col("date").cast(pl.Date).alias("date_only"))
df = df.unique(subset=["date_only"]).sort("date_only")
dates_2026 = df["date_only"].to_list()
print(f"2026 trading days: {len(dates_2026)}")
print(f"First 5: {dates_2026[:5]}")
print(f"Last 5: {dates_2026[-5:]}")

# Find first trading day of each month in 2026
from collections import defaultdict
first_of_month = {}
for d in dates_2026:
    key = f"{d.year}-{d.month:02d}"
    if key not in first_of_month:
        first_of_month[key] = d
print("\nFirst trading day of each month in 2026:")
for k, v in sorted(first_of_month.items()):
    print(f"  {k}: {v}")

print()
print("=" * 60)
print("4. Sample pre-computed factor data shape (VOL20 for 2024)")
print("=" * 60)
vol20_2024 = DATA_ROOT / "parquet/factors/VOL20/year=2024/data.parquet"
if vol20_2024.exists():
    df = pl.read_parquet(vol20_2024)
    print(f"Rows: {len(df)}, Cols: {df.columns}")
    print(f"Date range: {df['date'].min()} to {df['date'].max()}")
    print(f"Unique codes: {df['code'].n_unique()}")
    print(f"Null count: {df['VOL20'].null_count()}")
    print(df.head(3))
else:
    print("VOL20/year=2024 not found")
    # Try to find which years VOL20 has
    vol20_dir = DATA_ROOT / "parquet/factors/VOL20"
    if vol20_dir.exists():
        print(f"VOL20 has years: {sorted([d.name for d in vol20_dir.iterdir() if d.is_dir()])}")

print()
print("=" * 60)
print("5. CSI 300 latest constituents count")
print("=" * 60)
ic_files = list((DATA_ROOT / "parquet/index_constituents").rglob("*.parquet"))
# Combine all and get latest
all_ic = pl.concat([pl.read_parquet(f) for f in ic_files], how="diagonal_relaxed")
csi300 = all_ic.filter(pl.col("index_code") == "000300.XSHG")
latest_date = csi300["date"].max()
latest_constituents = csi300.filter(pl.col("date") == latest_date)
print(f"CSI 300 latest date: {latest_date}")
print(f"CSI 300 latest constituents count: {len(latest_constituents)}")
