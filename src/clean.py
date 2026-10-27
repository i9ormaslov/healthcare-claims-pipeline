"""
clean.py - Build the `clean` schema from `raw` by running sql/clean/*.sql.

WHY THE SQL LIVES IN .sql FILES, NOT PYTHON STRINGS
- Each transformation can be read, reviewed, and diffed on its own.
- The same SQL can be pasted into the notebook or the DuckDB UI to debug.
- Python's job is just orchestration: order, transaction, reporting.

WHY ONE TRANSACTION
All four tables are rebuilt between BEGIN and COMMIT. If any file fails, the
ROLLBACK leaves the previous clean tables untouched. You never end up with
a mix of new and stale tables that disagree with each other.

ORDER
Files run in name order (01_, 02_, ...). The numeric prefix is the ordering
contract: adding a step means adding a file, not editing this script.

Usage:
    python src/clean.py
"""

from __future__ import annotations

import sys
import time

import duckdb

from config import DB_PATH, SQL_DIR

CLEAN_SQL_DIR = SQL_DIR / "clean"


def build(con: duckdb.DuckDBPyConnection) -> list[tuple[str, int, float]]:
    files = sorted(CLEAN_SQL_DIR.glob("*.sql"))
    if not files:
        raise FileNotFoundError(f"No SQL files in {CLEAN_SQL_DIR}")

    results = []
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS clean")
        for f in files:
            start = time.perf_counter()
            con.execute(f.read_text(encoding="utf-8"))
            results.append((f.name, time.perf_counter() - start))
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return results


def main() -> int:
    if not DB_PATH.exists():
        print(f"{DB_PATH} not found. Run src/ingest.py first.")
        return 1

    con = duckdb.connect(str(DB_PATH))
    try:
        timings = build(con)
    except Exception as exc:
        print(f"Clean build failed and was rolled back: {exc}")
        return 1

    for name, secs in timings:
        print(f"  ran {name:<22} {secs:5.1f}s")

    print()
    tables = con.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'clean' ORDER BY table_name
    """).fetchall()
    for (t,) in tables:
        n = con.execute(f"SELECT COUNT(*) FROM clean.{t}").fetchone()[0]
        print(f"clean.{t:<14} {n:>12,} rows")

    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
