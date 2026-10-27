"""
download.py - Fetch one CMS DE-SynPUF sample (default: Sample 2) into data/raw/.

WHY THIS FILE EXISTS
Raw data is not committed to Git (too large, and the source is public anyway).
Instead, anyone can reproduce the dataset by running this script.
That is the "reproducible setup" an interviewer will ask about.

DESIGN CHOICES (each one is defensible in an interview)
- Standard library only (urllib, zipfile): no extra dependency for a simple job.
- Idempotent: if a CSV is already there, it is skipped. Re-running is safe.
- Verifies the expected CSV name after unzipping, because a CMS download
  link can point at the wrong file (see DECISIONS.md #4 and #8).
- Carrier (physician) claims are optional because they are large;
  we skip them in the MVP (DECISIONS.md #5).

Usage:
    python src/download.py                    # MVP files (6 files), Sample 2
    python src/download.py --sample 5         # a different sample
    python src/download.py --include-carrier  # also the two carrier files
"""

from __future__ import annotations

import argparse
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

CMS_BASE = (
    "https://www.cms.gov/research-statistics-data-and-systems/"
    "downloadable-public-use-files/synpufs/downloads/"
)
CMS_FILES_BASE = "https://downloads.cms.gov/files/"

# Sample 2, not Sample 1: CMS never published a working 2010 beneficiary
# file for Sample 1 (its link points at Sample 20 and the Sample 1 URL 404s).
# See DECISIONS.md #8. Every sample is internally complete, so any one works.
DEFAULT_SAMPLE = 2


def mvp_files(n: int) -> list[tuple[str, str]]:
    """(expected CSV inside the zip, download URL) for sample n."""
    files = [
        (f"DE1_0_{y}_Beneficiary_Summary_File_Sample_{n}.csv",
         CMS_BASE + f"de1_0_{y}_beneficiary_summary_file_sample_{n}.zip")
        for y in (2008, 2009, 2010)
    ]
    for kind in ("Inpatient_Claims", "Outpatient_Claims"):
        files.append((f"DE1_0_2008_to_2010_{kind}_Sample_{n}.csv",
                      CMS_BASE + f"de1_0_2008_to_2010_{kind.lower()}_sample_{n}.zip"))
    files.append((f"DE1_0_2008_to_2010_Prescription_Drug_Events_Sample_{n}.csv",
                  CMS_FILES_BASE + f"DE1_0_2008_to_2010_Prescription_Drug_Events_Sample_{n}.zip"))
    return files


def carrier_files(n: int) -> list[tuple[str, str]]:
    return [
        (f"DE1_0_2008_to_2010_Carrier_Claims_Sample_{n}{half}.csv",
         CMS_FILES_BASE + f"DE1_0_2008_to_2010_Carrier_Claims_Sample_{n}{half}.zip")
        for half in ("A", "B")
    ]


def download(url: str, dest: Path) -> None:
    """Stream a URL to disk so large files never sit fully in memory."""
    print(f"  downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "claims-portfolio/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as f:
        shutil.copyfileobj(resp, f)


def fetch(expected_csv: str, url: str) -> None:
    target = RAW_DIR / expected_csv
    if target.exists():
        print(f"[skip] {expected_csv} already present")
        return

    zip_path = RAW_DIR / (expected_csv + ".zip")
    download(url, zip_path)

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        # Case-insensitive match: CMS zips are not consistent about capitalization.
        match = next((n for n in names if Path(n).name.lower() == expected_csv.lower()), None)
        if match is None:
            zip_path.unlink()
            raise RuntimeError(
                f"Zip from {url} did not contain {expected_csv}. Found: {names}. "
                "The CMS link may be wrong; check the download page manually."
            )
        with zf.open(match) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)

    zip_path.unlink()  # keep only the CSV
    size_mb = target.stat().st_size / 1_000_000
    print(f"[ok]   {expected_csv} ({size_mb:,.1f} MB)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--sample", type=int, default=DEFAULT_SAMPLE, choices=range(1, 21),
                        metavar="1-20", help=f"which DE-SynPUF sample (default {DEFAULT_SAMPLE})")
    parser.add_argument("--include-carrier", action="store_true",
                        help="also download the two large carrier claim files")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print(f"DE-SynPUF Sample {args.sample}\n")
    files = mvp_files(args.sample) + (carrier_files(args.sample) if args.include_carrier else [])

    failures = []
    for expected_csv, url in files:
        try:
            fetch(expected_csv, url)
        except Exception as exc:  # report every failure, not just the first
            print(f"[fail] {expected_csv}: {exc}")
            failures.append(expected_csv)

    if failures:
        print(f"\n{len(failures)} file(s) failed. Fix and re-run; finished files are skipped.")
        return 1
    print("\nAll files present in data/raw/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
