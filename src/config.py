"""
config.py - One place for paths and settings every pipeline step shares.

WHY
download.py and ingest.py each had their own copy of the paths and the sample
number, with a comment saying "must match". A comment is not a guarantee.
With three or more scripts, duplicated settings drift apart. Now every script
imports from here, so there's a single source of truth.

OVERRIDE
Set the CLAIMS_DB environment variable to point every step (and the notebook)
at a different database file, e.g. a scratch copy for testing:
    $env:CLAIMS_DB = "C:\\temp\\test.duckdb"    # PowerShell
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
SQL_DIR = ROOT / "sql"
DOCS_DIR = ROOT / "docs"
DB_PATH = Path(os.environ.get("CLAIMS_DB", ROOT / "data" / "processed" / "claims.duckdb"))

# Sample 2, not 1: CMS never published a working 2010 beneficiary file for
# Sample 1 (DECISIONS.md #8). Every sample is internally complete.
DEFAULT_SAMPLE = 2


def connect_db(read_only: bool = False):
    """Open the project database with a clear message for the most common failure.

    DuckDB allows many readers OR one writer per file. If anything else has the
    file open (usually a notebook kernel), a writer can't get in.
    """
    import duckdb  # imported here so config.py stays importable without duckdb

    try:
        return duckdb.connect(str(DB_PATH), read_only=read_only)
    except duckdb.IOException as exc:
        if "being used by another process" in str(exc) or "Could not set lock" in str(exc):
            raise SystemExit(
                f"\n{DB_PATH.name} is open in another program (usually the notebook's kernel).\n"
                "Fix: in the notebook run con.close() or click Restart, then try again.\n"
                f"(Original error: {exc})"
            ) from None
        raise
