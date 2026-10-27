# Decisions Log

Each entry: what we chose, what else we considered, and why. Newest at the bottom.
Format: **Decision** · Alternatives · Tradeoffs · Date

---

### 1. Dataset: CMS DE-SynPUF (one sample), not Synthea
- **Chose:** one DE-SynPUF sample — Sample 2, see #8 (1 of 20 samples, ~116K synthetic Medicare members, 2008–2010).
- **Alternatives:** Synthea (generated EHR + claims); all 20 SynPUF samples.
- **Why:**
  - It uses the real CMS claims layout, so programs written on it are meant to run on CMS Limited Data Sets.
  - It has multiple linked files (keyed on `DESYNPUF_ID`), which makes cross-file validation meaningful.
  - No generator setup is needed.
  - One sample is enough. All claims for a member live in the same sample number, so a single sample is internally complete.
- **Tradeoffs:**
  - Codes are ICD-9 (the US switched to ICD-10 in 2015).
  - The data is from 2008–2010.
  - CMS synthesis weakens relationships between variables, so findings demonstrate *method*, not clinical truth. Every summary must say so.
- **Date:** 2026-10-27

### 2. Raw data is never committed; a download script reproduces it
- **Chose:** `.gitignore` covers `data/raw/` and `data/processed/`. `src/download.py` fetches the files.
- **Alternatives:** Commit the CSVs; use Git LFS.
- **Why:**
  - The files are hundreds of MB.
  - The source is public and stable.
  - A script documents exactly where the data came from.
- **Tradeoffs:** A reviewer must run one command before anything works. Small aggregated extracts (`data/extracts/`) are committed, so the dashboard works without it.
- **Date:** 2026-10-27

### 3. Database: DuckDB
- **Chose:** DuckDB, as a single file at `data/processed/claims.duckdb`.
- **Alternatives:** SQLite (simplest), Postgres (most "production").
- **Why:**
  - DuckDB is columnar and built for analytical queries (GROUP BY, window functions) over millions of rows.
  - It reads CSVs directly and needs no server.
- **Tradeoffs:**
  - It is less familiar to some interviewers than Postgres.
  - It is not designed for many concurrent writers. That doesn't matter for a batch pipeline.
  - Postgres would add install and configuration work with no analytical benefit at this size.
- **Date:** 2026-10-27

### 4. Verify file contents after download, not just the URL
- **Chose:** `download.py` checks that each zip contains the expected CSV name.
- **Why:** On CMS's own Sample 1 download page (checked 2026-10-27), the "2010 Beneficiary Summary File" link points to the **Sample 20** file. Trusting the link would silently mix two samples and create thousands of orphaned keys.
- **Tradeoffs:** None worth mentioning. It's a few lines of code.
- **Date:** 2026-10-27

### 5. Skip carrier (physician/supplier) claims in the MVP
- **Chose:** Inpatient, outpatient, and Part D (PDE) only. Carrier is behind a `--include-carrier` flag.
- **Why:** Carrier is by far the largest file type and is split into two parts. The three service types in the spec are covered without it.
- **Tradeoffs:** "Outpatient" here means *institutional* outpatient only. Physician office visits are not included, so total cost per member is understated. Say this out loud in any cost discussion.
- **Date:** 2026-10-27

### 6. Land raw data as text (VARCHAR), type it later
- **Chose:** `raw` schema, all columns VARCHAR, plus a `source_file` column. Typed, cleaned tables come in Phase 2.
- **Alternatives:** Let DuckDB infer types on load.
- **Why:**
  - A typed load can drop or NULL out bad values, for example a date like `20081399`, without telling you.
  - As text, bad values survive, so the validation step can count and report them.
  - We can rebuild clean tables at any time without re-downloading.
- **Tradeoffs:** There is an extra transformation step, and the raw tables are bigger on disk.
- **Date:** 2026-10-27

### 7. Dashboard: Power BI Desktop, with static exports in the repo
- **Chose:** Build in Power BI Desktop (Windows, free). Commit the `.pbix`, plus a PDF export, screenshots, and a short screen recording in `docs/`.
- **Alternatives:** Tableau Public (free public hosting); Streamlit (live web app).
- **Why:**
  - Power BI is commonly listed in healthcare analyst postings.
  - You already have some exposure to it.
  - It runs natively on Windows.
- **Tradeoffs:** Publishing to the Power BI service requires a work or school account; personal emails like Gmail aren't accepted. Even a school account may have "Publish to web" turned off by the university admin. So reviewers likely can't click a live link. Mitigations:
  1. PDF and screenshots in the README.
  2. Try your university email.
  3. Optional Streamlit version later if a live link matters.
- **Date:** 2026-10-27

### 8. Switched from Sample 1 to Sample 2
- **Chose:** Sample 2 as the default. The sample number is now a `--sample` flag on both scripts.
- **What happened:** The first real run got `HTTP 404` for the 2010 Sample 1 beneficiary file. Following the URL pattern of 2008/2009 didn't work, and CMS's own link points at Sample 20 (#4). An open GitHub issue on the OHDSI ETL-CMS project reports the same problem with no working URL. The file appears not to be published at all.
- **Alternatives considered:**
  - Keep Sample 1 with only 2008–2009 beneficiary data. We'd lose 2010 enrollment, chronic-condition flags, and deaths for 2010 claims. That's a real analytical gap, which is worse than a re-download.
  - Use Sample 20's 2010 file. That's a different synthetic population, so it would create the exact orphan-key problem #4 guards against.
- **Why Sample 2:** All eight files are linked consistently (checked 2026-10-27). Each sample is a complete, self-contained slice, so nothing analytical depends on which number we pick.
- **Tradeoff:** One extra download. The ingest patterns include the sample number, so leftover Sample 1 files in `data/raw/` can't be mixed in.
- **Date:** 2026-10-27

### 9. Pin exact dependency versions
- **Chose:** `==` pins in `requirements.txt` (duckdb 2.0.0, pandas 3.1.0, pytest 9.1.1, jupyter 1.1.1; Python 3.14).
- **What happened:** The original `>=` ranges installed DuckDB 2.0.0 on Windows. A database file written by 2.0 could not be opened by DuckDB 1.5.6 on another machine ("database file was created with a newer version").
- **Alternatives:** Ranges (`>=`); a lock file tool (pip-tools, uv, poetry).
- **Why:** A DuckDB file is tied to the engine version that wrote it, so "works on my machine" turns into a real failure. Exact pins are the simplest fix that a reviewer can read at a glance.
- **Tradeoffs:** Pins don't lock *transitive* dependencies (numpy, etc.). A lock file would, at the cost of another tool. Upgrades are now deliberate: bump the pin, re-run, commit.
- **Date:** 2026-10-27

### 10. Claim grain is (CLM_ID, SEGMENT)
- **Chose:** Treat `(CLM_ID, SEGMENT)` as the row key for inpatient and outpatient. Count claims as `COUNT(DISTINCT CLM_ID)`. Sum payments across all segments.
- **Evidence:** `CLM_ID` alone has 60 duplicates (inpatient) and 11,009 (outpatient). With `SEGMENT` added, there are zero. Segment-2 rows have no dates but 59/60 (inpatient) and 10,968/11,201 (outpatient) carry payments. (Notebook 01, section 2.)
- **Alternatives:** Drop segment 2 (understates cost); treat each row as a claim (overstates claim volume).
- **Tradeoffs:** Segment-2 dates must be inherited from segment 1, which is one extra join in cleaning.
- **Date:** 2026-10-27

### 11. Flag suspicious values; don't delete them
- **Chose:** Negative payments, zero payments, `OTHER` placeholder codes, and impossible Rx values get **flags** in the clean tables. They are not dropped. Each metric states which flags it excludes.
- **Why:** Negative payments are usually adjustments; deleting them overstates cost. Deleting rows also makes the data-quality report unable to say how much was affected. Flagging keeps the decision visible and reversible.
- **Tradeoffs:** Every analysis query must apply the right filter. This will be centralized in Phase 3 views so it isn't repeated.
- **Date:** 2026-10-27

### 12. Assign a claim to a year by its through (end) date
- **Chose:** Claim year = year of `CLM_THRU_DT` (claims) / `SRVC_DT` (Rx).
- **Evidence:** 204 inpatient and 330 outpatient claims start in late 2007 and end in 2008.
- **Why:** This is the CMS convention. It keeps every claim inside 2008–2010 and matches how the beneficiary files are split by year.
- **Tradeoffs:** A stay from Dec 2008 to Jan 2009 counts entirely in 2009. That's fine at annual granularity; Phase 6 monthly trends will note it.
- **Date:** 2026-10-27

### 13. Clean layer: same grain as raw, typed, flagged, SQL in files
- **Chose:** A `clean` schema built by `sql/clean/01_…04_*.sql`, run by `src/clean.py` in one transaction.
  - Each clean table has **exactly the same rows as its raw table**. No aggregation happens here.
  - Money is `DECIMAL(12,2)`, dates are `DATE`, and codes become booleans.
  - Every profiling finding becomes a flag column.
- **Alternatives:** Do cleaning in pandas; aggregate to claim level during cleaning; store SQL as Python strings.
- **Why:**
  - **Same grain** means raw and clean can be reconciled row-for-row and dollar-for-dollar, so cleaning provably loses nothing. Aggregating to claim level comes in Phase 3.
  - **DECIMAL for money:** floating point (DOUBLE) can't represent most cents exactly, so sums drift by fractions of a cent. Raw vs clean totals now match to the cent.
  - **SQL in .sql files** can be read, diffed, and pasted into the notebook for debugging. Python only orchestrates.
  - **One transaction:** if any step fails, ROLLBACK keeps the old clean tables. You never get a half-rebuilt layer.
- **Tradeoffs:**
  - Columns the analysis doesn't need are not carried into clean: procedure codes, NPIs, most HCPCS, minor cost-sharing fields. They remain in `raw`, so adding one back is a one-line change.
  - DECIMAL math is slightly slower than DOUBLE. That's irrelevant at this size.
- **Date:** 2026-10-27

### 14. Orphaned claim segments: keep, flag, leave the year NULL
- **What happened:** After cleaning, 192 outpatient rows still had no dates. They are **segment-2 rows whose claim has no segment 1**: page 2 with no page 1. They carry $247,460. Profiling didn't catch it; the post-cleaning reconciliation did.
- **Chose:** Keep the rows, add `orphan_segment = TRUE`, and leave `from_date`, `thru_date`, and `claim_year` NULL.
- **Alternatives:**
  - Drop them: loses real money.
  - Guess a year (e.g., the member's first claim year): invents data.
  - Fill from a neighboring claim: also invents data.
- **Why:** NULL plus a flag is honest. Totals stay complete, yearly breakdowns exclude these rows *visibly*, and the data-quality report states the amount.
- **Tradeoff:** Yearly totals sum to $247K less than the all-time total. The report must say so, or the numbers look inconsistent.
- **Date:** 2026-10-27

### 15. Shared config module
- **Chose:** `src/config.py` holds paths, the default sample, and the database location (overridable with the `CLAIMS_DB` environment variable).
- **Why:** download.py and ingest.py had duplicate settings guarded only by a comment saying they "must match." With a third script, duplication becomes drift. `CLAIMS_DB` also lets every step run against a scratch database for testing.
- **Tradeoff:** One more file to explain.
- **Date:** 2026-10-27

### 16. Validation: declarative checks with three severities and tolerances
- **Chose:** 62 checks defined as data in `src/checks.py`, run by `src/validate.py`.
  - Each check is an ID, a category, a severity, and one SQL query returning `violations, total, amount, detail`.
  - **error** = must be zero.
  - **warn** = known, documented issue; fails only if its rate exceeds `fail_above_pct`.
  - **info** = context; never fails.
- **Alternatives:**
  - A framework (Great Expectations, Soda, dbt tests): powerful, but heavy to install and explain for a portfolio project.
  - Ad-hoc asserts in scripts: no report and no history.
- **Why:**
  - Adding a check is adding one entry.
  - Tolerances let known synthetic-data issues (e.g., 5.2% impossible Rx costs) pass *visibly* while still catching the day they get worse. Tested: pushing that rate to 11.9% flipped WARN → FAIL.
  - The status logic (`evaluate()`) is a pure function, so it's testable without a database (2c).
- **Tradeoffs:** Tolerances are judgment calls, roughly 2× today's rate, and documented in the code. A framework would add features (scheduling, alerting) we don't need yet.
- **Date:** 2026-10-27

### 17. A crashed check is a FAIL, and the run exits non-zero
- **Chose:**
  - If a check's SQL errors, its status is FAIL with the error text as detail.
  - `validate.py` exits with code 1 when anything fails.
  - Results append to `qa.check_results` with a run ID.
- **What happened:** On the first run, two of my own conversion-loss checks had a SQL bug. Because crashes count as failures, the run failed loudly. Had they been skipped, the report would have shown "60 passed" and nobody would know two checks never ran.
- **Why:**
  - A broken check must never look like a passing one.
  - The exit code lets a pipeline stop before building analysis on bad data ("fail fast").
  - The history table shows whether an issue is growing between runs.
- **Verified:** Six deliberate kinds of damage on a copy of the data were all caught, most by more than one check: lost rows, a duplicate fill, reversed dates, an unknown member, an unmapped code, and a known issue past tolerance.
- **Date:** 2026-10-27

### 18. High-cost flags use Tukey fences on log(cost)
- **Chose:** Flag claims above Q3 + 1.5×IQR of **ln(amount)**. Also report the extreme fence (Q3 + 3×IQR).
- **What happened:** The first version used dollar-scale fences (Q3 + 3×IQR on raw dollars) and flagged **11%** of outpatient claims. Costs are so right-skewed (median $70) that the dollar quartile range is tiny. That isn't outlier detection; it's the normal right tail.
- **Alternatives:**
  - Mean ± 3 standard deviations: distorted by skew and by the cap.
  - Fixed percentile (top 1%): always flags exactly 1%, which says nothing.
- **Why log:** Cost data behaves multiplicatively ("10× typical"), so distance on the log scale matches how analysts think about it. The result is 1.3% inpatient, 2.8% outpatient, 0% Rx.
- **Finding:** The **extreme** fence is above CMS's cap in all three files ($228K vs $57K, $25K vs $3.3K, $66K vs $570). **Top-coding removed every extreme outlier.** The high-cost analysis will understate the real tail, and this proves it.
- **Date:** 2026-10-27
