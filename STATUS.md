# Status

**Rule:** the resume claims only what is in the **Done** column.
Overall: 🟡 **In progress** (Phase 2 of 6)

| Phase | Item | Status |
|---|---|---|
| 0 | Repo structure, `.gitignore`, requirements | ✅ Done |
| 0 | `src/download.py`: fetch Sample 2 (6 files) | ✅ Done |
| 0 | `src/ingest.py`: raw load into DuckDB + load log | ✅ Done |
| 1 | `src/profiling.py`: reusable profile / key / top-value helpers | ✅ Done |
| 1 | `notebooks/01_profile_raw.ipynb`: grain, completeness, dates, linkage, costs, codes | ✅ Done |
| 1 | `docs/profiling_findings.md`: findings → Phase 2 rules | ✅ Done |
| 2 | `src/config.py`: shared paths + `CLAIMS_DB` override | ✅ Done |
| 2 | `sql/clean/*.sql` + `src/clean.py`: typed clean tables, flags, segment date inheritance | ✅ Done |
| 2 | `src/checks.py` + `src/validate.py`: 62 checks, history table, exit code, `docs/data_quality_report.md` | 🟡 Built; verified on a test copy including 6 deliberate breakages. **Run on your machine, then mark Done** |
| 2 | pytest tests for validation logic | ⬜ Planned |
| 3 | Unified claims table | ⬜ Planned |
| 3 | Analysis SQL (CTEs, window functions) | ⬜ Planned |
| 4 | Power BI dashboard + exports | ⬜ Planned |
| 5 | README architecture diagram, 1-page summary, slides | ⬜ Planned |
| 6 | Trend / projection view (maybe R) | ⬜ Later |

## Safe resume wording right now
Once validate.py has run on your machine and is committed, this is safe to list **as in progress**:

> **Healthcare Claims Data Pipeline** *(in progress)*. Python, SQL (DuckDB), Git
> - Built a pipeline ingesting 6.8M synthetic Medicare records (claims, prescription fills, and member enrollment; CMS DE-SynPUF) into a layered DuckDB database (raw → typed, flagged clean layer), reconciled to the cent.
> - Wrote 62 automated data-quality checks (duplicates, nulls, impossible dates, orphaned keys, cost outliers) with severity levels and tolerances, producing a data-quality report and failing the run on regressions.

Don't mention the dashboard, analysis, or summary until those rows say Done.
