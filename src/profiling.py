"""
profiling.py - Small, reusable helpers for profiling raw tables.

WHY A HELPER INSTEAD OF ONE-OFF NOTEBOOK CODE
The notebook (notebooks/01_profile_raw.ipynb) is for *looking*. This module is
for *repeatable* checks. Phase 2's data-quality report will import the same
functions, so "what the profile showed" and "what the pipeline checks" never drift.

HOW IT WORKS
DuckDB's built-in `SUMMARIZE <table>` computes, in one scan, per column:
min, max, approx_unique (approximate distinct count), and null_percentage.
We add three flags on top:
  - all_null:  column is 100% empty   -> candidate to drop
  - constant:  only one distinct value -> carries no information
  - id_like:   distinct count ~= row count -> possible key (verify exactly!)
`approx_unique` is an estimate (HyperLogLog), so anything that looks like a
key must be confirmed with an exact COUNT(DISTINCT ...) - see check_key().
Low-cardinality columns are re-counted exactly inside profile_table().
"""

from __future__ import annotations

import duckdb
import pandas as pd


def profile_table(con: duckdb.DuckDBPyConnection, table: str) -> pd.DataFrame:
    """One row per column: completeness, cardinality, range, and flags."""
    n_rows = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    df = con.execute(f"SUMMARIZE {table}").df()

    # null_percentage comes back as a number (newer DuckDB) or text like "12.3%".
    pct = df["null_percentage"].astype(str).str.rstrip("%").astype(float)

    out = pd.DataFrame({
        "column": df["column_name"],
        "pct_null": pct.round(2),
        "approx_distinct": df["approx_unique"].astype("int64"),
        "min": df["min"],
        "max": df["max"],
    })
    out["all_null"] = out["pct_null"] >= 100

    # approx_unique is unreliable at tiny cardinalities (it reported 1 for a
    # column holding "0" and "Y"), so confirm low-cardinality columns exactly.
    low = out.index[(out["approx_distinct"] <= 3) & ~out["all_null"]]
    for i in low:
        col = out.at[i, "column"]
        out.at[i, "approx_distinct"] = con.execute(
            f'SELECT COUNT(DISTINCT "{col}") FROM {table}').fetchone()[0]
    out["constant"] = (out["approx_distinct"] == 1) & ~out["all_null"]
    out["id_like"] = out["approx_distinct"] >= 0.95 * n_rows
    out.attrs["n_rows"] = n_rows
    return out


def check_key(con: duckdb.DuckDBPyConnection, table: str, cols: list[str]) -> dict:
    """Exact test: do these columns uniquely identify a row?"""
    key = ", ".join(cols)
    n, d = con.execute(
        f"SELECT COUNT(*), COUNT(DISTINCT ({key})) FROM {table}"
    ).fetchone()
    return {"table": table, "key": key, "rows": n, "distinct": d,
            "duplicates": n - d, "is_unique": n == d}


def top_values(con: duckdb.DuckDBPyConnection, table: str, column: str,
               n: int = 10) -> pd.DataFrame:
    """Most frequent values with their share of rows (NULL counted explicitly)."""
    return con.execute(f"""
        SELECT {column} AS value,
               COUNT(*) AS n,
               ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct
        FROM {table}
        GROUP BY 1
        ORDER BY n DESC
        LIMIT {n}
    """).df()
