# Healthcare Claims Data Pipeline

> 🟡 **In progress.** See [STATUS.md](STATUS.md) for what is built vs. planned.

An end-to-end pipeline over **synthetic** Medicare claims (CMS DE-SynPUF, Sample 2). It covers ingesting and validating the raw files, loading them into DuckDB, analyzing utilization and cost with SQL, and presenting the results in a Power BI dashboard.

**No real patient data is used.** DE-SynPUF is fully synthetic. Its findings illustrate methods and are not clinical conclusions.

## Data
| File | Contents |
|---|---|
| Beneficiary Summary (2008, 2009, 2010) | One row per member per year: demographics, chronic conditions |
| Inpatient claims | Hospital stays |
| Outpatient claims | Institutional outpatient services |
| Prescription Drug Events | Part D prescription fills |

Source: [CMS DE-SynPUF](https://www.cms.gov/data-research/statistics-trends-and-reports/medicare-claims-synthetic-public-use-files/cms-2008-2010-data-entrepreneurs-synthetic-public-use-file-de-synpuf)

## Setup (Windows, PowerShell)
```powershell
git clone <this repo>
cd healthcare-claims-pipeline
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python src/download.py      # ~6 files into data/raw/
python src/ingest.py        # loads data/processed/claims.duckdb
jupyter notebook            # open notebooks/01_profile_raw.ipynb, Run All
```

## Repo layout
```
data/raw/        downloaded CSVs (not in Git)
data/processed/  DuckDB database (not in Git)
data/extracts/   small aggregated CSVs for the dashboard (in Git)
src/             pipeline code
sql/             analysis queries
notebooks/       exploration and profiling
tests/           pytest tests
docs/            data-quality report, summary, slides, dashboard exports
```

## Architecture
_Diagram coming in Phase 5._ Current flow: `download.py → data/raw/*.csv → ingest.py → DuckDB raw schema`.

See [DECISIONS.md](DECISIONS.md) for why each choice was made.
