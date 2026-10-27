"""
ingest.py - Load raw DE-SynPUF CSVs into DuckDB, untouched, in a `raw` schema.

WHY A "RAW" LAYER
We land the data exactly as CMS shipped it, every column as text (VARCHAR).
Cleaning and typing happen later, in a separate step (Phase 2).
Benefits:
- Nothing is silently lost. If a date is "20081399", a typed load would
  fail or turn it into NULL, and we would never know. As text, it survives
  and our validation checks can *count* it and report it.
- We can always re-derive clean tables from raw without re-downloading.
This is the common "bronze / silver / gold" (raw / clean / analytics) pattern.

WHAT IT ADDS
- `source_file` on every row: lineage (which file did this row come from?).
- `raw._load_log`: one row per table with row count and load time, an audit
  trail you can show in the data-quality report.

Usage:
    python src/ingest.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

from config import DB_PATH, DEFAULT_SAMPLE, RAW_DIR



def sources(n: int) -> dict[str, str]:
    """table name -> glob pattern of source CSV(s) for sample n.
    Patterns include the sample number so files from a different sample
    sitting in data/raw/ can never be mixed in."""
    return {
        "beneficiary": f"DE1_0_20??_Beneficiary_Summary_File_Sample_{n}.csv",  # 3 files, one per year
        "inpatient":   f"DE1_0_2008_to_2010_Inpatient_Claims_Sample_{n}.csv",
        "outpatient":  f"DE1_0_2008_to_2010_Outpatient_Claims_Sample_{n}.csv",
        "pde":         f"DE1_0_2008_to_2010_Prescription_Drug_Events_Sample_{n}.csv",
    }


def optional_sources(n: int) -> dict[str, str]:
    return {"carrier": f"DE1_0_2008_to_2010_Carrier_Claims_Sample_{n}[AB].csv"}  # A + B halves


def load_table(con: duckdb.DuckDBPyConnection, table: str, pattern: str) -> int:
    files = sorted(RAW_DIR.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No files match {pattern} in {RAW_DIR}. Run src/download.py first.")

    # Forward slashes work on Windows too and avoid backslash-escaping issues in SQL.
    file_list = ", ".join(f"'{f.as_posix()}'" for f in files)

    year_col = ""
    if table == "beneficiary":
        # The year lives only in the file name, so we extract it. Without this,
        # three years of rows for the same member would be indistinguishable.
        year_col = (r", CAST(regexp_extract(parse_filename(filename), 'DE1_0_(\d{4})_', 1)"
                    r" AS INTEGER) AS file_year")

    # filename = true makes DuckDB add a `filename` column (full path).
    # We keep just the base name as `source_file` for readable lineage.
    con.execute(f"""
        CREATE OR REPLACE TABLE raw.{table} AS
        SELECT * EXCLUDE (filename),
               parse_filename(filename) AS source_file
               {year_col}
        FROM read_csv([{file_list}],
                      header = true,
                      all_varchar = true,    -- land as text; type later
                      union_by_name = true,  -- tolerate column-order differences
                      filename = true)
    """)

    rows = con.execute(f"SELECT COUNT(*) FROM raw.{table}").fetchone()[0]
    con.execute(
        "INSERT INTO raw._load_log VALUES (?, ?, ?, now())",
        [table, len(files), rows],
    )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Load raw DE-SynPUF CSVs into DuckDB.")
    parser.add_argument("--sample", type=int, default=DEFAULT_SAMPLE)
    args = parser.parse_args()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    con.execute("""
        CREATE TABLE IF NOT EXISTS raw._load_log (
            table_name VARCHAR, files_loaded INTEGER, row_count BIGINT, loaded_at TIMESTAMP
        )
    """)

    to_load = sources(args.sample)
    extra = optional_sources(args.sample)
    if any(RAW_DIR.glob(extra["carrier"])):
        to_load.update(extra)

    print(f"DE-SynPUF Sample {args.sample}\n")
    for table, pattern in to_load.items():
        rows = load_table(con, table, pattern)
        print(f"raw.{table:<12} {rows:>12,} rows")

    con.close()
    print(f"\nLoaded into {DB_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
