# Interview Prep

How to use this file:
- **Hints** are my notes.
- **My answer** is yours. Write it in your own words, out loud first, then type it.
- If you can't answer without peeking at the hints, you're not ready to claim that part yet.

---

## Data & setup

**Q: Why did you pick DE-SynPUF over Synthea?**
- Hints:
  - It uses the real CMS claims structure.
  - It has multi-file linkage through `DESYNPUF_ID`.
  - No generator is needed.
  - The honest weakness: synthetic noise weakens real relationships, plus ICD-9 and 2008–2010 dates.
- My answer:

**Q: How would someone else reproduce your project?**
- Hints:
  - Clone the repo, create a venv, install requirements.
  - Run `download.py`, then `ingest.py`.
  - Raw data isn't in Git, and here's why.
- My answer:

**Q: Tell me about a data problem you found before you even started analyzing.**
- Hints:
  - The CMS download page links the 2010 Sample 1 beneficiary file to Sample 20, and the "correct-looking" URL returns 404.
  - What would have broken: mixing samples creates orphaned keys and wrong member counts. Skipping 2010 loses a year of enrollment data.
  - What you did: the script checks file names inside each zip, you switched to Sample 2, and the sample number became a parameter.
  - The general lesson: validate inputs at the boundary; don't trust the source's labels.
- My answer:

## Architecture

**Q: Why DuckDB instead of Postgres or SQLite?**
- Hints:
  - It's columnar and built for analytics, with no server.
  - It reads CSVs directly.
  - Postgres would add setup cost and no analytical benefit at this size.
  - It is not for many concurrent writers.
- My answer:

**Q: Why load everything as text first?**
- Hints:
  - A typed load can hide bad values.
  - Validation needs to see bad values to count them.
  - This is the raw → clean → analytics layering pattern.
- My answer:

**Q: What does the `source_file` column / `_load_log` table give you?**
- Hints: lineage (which file each row came from) and an audit trail (row counts per run, which make drift detectable).
- My answer:

## Scope

**Q: Why no carrier (physician) claims?**
- Hints:
  - It's the largest file type.
  - The MVP still covers inpatient, outpatient, and Rx.
  - Consequence: cost per member is understated, and "outpatient" means institutional only.
- My answer:

## Profiling (Phase 1)

**Q: What was the most important thing profiling told you?**
- Hints:
  - `CLM_ID` is not unique; the key is `(CLM_ID, SEGMENT)`.
  - Segment-2 rows have no dates but carry payments.
  - Dropping them understates cost; counting them as claims overstates volume.
  - You found it with an exact key check, not by eyeballing.
- My answer:

**Q: Some of your claim rows had no dates. Why didn't you just drop them?**
- Evidence (your own predict-then-run, notebook 01):
  - Segment-2 rows = continuations of a claim ("page 2 of the invoice"); same `CLM_ID`, no dates.
  - Dropping them removes $15.1M of $225.5M outpatient payments (7.2%) vs only 0.2% for inpatient.
  - Segment-2 median payment is *higher* than segment 1 (outpatient $1,500 vs $70), so the loss lands on the most expensive claims.
  - Your prediction "1–5%" was right combined (~2%) but hid the 0.2% vs 7.2% split: averages across groups hide differences within them.
- Starter answer (rewrite this in your own voice): "Dropping the date-less segment rows looked harmless, but they held 7% of outpatient payments and skewed toward high-cost claims, so I kept them and inherited their dates from segment 1."
- My answer:

**Q: Your data was synthetic. Did you find any real data-quality problems?**
- Hints:
  - Structural checks passed (dates, death, orphans), and that's evidence too.
  - Semantic problems: about 5% of Rx fills show the patient paying more than the total cost.
  - Zero quantity or days supply; negative payments; `OTHER` placeholder codes.
  - Inconsistent coding: ESRD `0`/`Y`, chronic conditions 1/2.
- My answer:

**Q: How did you decide what "1" means in the chronic-condition flags?**
- Hints:
  - Tested both readings against plausible prevalence: diabetes 30–40% vs 60–70%.
  - Then confirmed in the codebook.
  - Data checks the documentation; the documentation checks the data.
- My answer:

**Q: Why flag bad rows instead of deleting them?**
- Hints:
  - Negatives are usually adjustments.
  - Deleting hides how much was affected.
  - Flags keep the choice visible and reversible.
  - Each metric states its own exclusions.
- My answer:

**Q: Anything surprising about the cost fields?**
- Hints:
  - Every outpatient amount is a multiple of $10.
  - Thousands of rows sit at exactly the maximum, so CMS top-coded for privacy.
  - Consequence: use percentiles, not z-scores, and the high-cost analysis understates the tail.
- My answer:

**Q: What's a mistake you made, and how did you catch it?**
- Hints:
  - The approximate distinct count (`SUMMARIZE`) was 37% too high for members with Rx.
  - It also called a two-value column "constant."
  - Now: exact counts for anything reported.
  - Also: `>=` version ranges broke the DuckDB file on another machine, so you pinned versions.
- My answer:

## Cleaning (Phase 2)

**Q: Walk me through your clean layer. What does it guarantee?**
- Hints:
  - Same rows as raw (same grain), so it reconciles row-for-row and dollar-for-dollar.
  - Real types; readable names; codes become booleans.
  - Findings become flags, not deletions.
  - SQL lives in files; Python runs them in one transaction.
- My answer:

**Q: Why DECIMAL instead of FLOAT for money?**
- Hints:
  - Binary floating point can't represent most cents exactly (0.1 + 0.2 ≠ 0.3).
  - Sums over millions of rows drift.
  - DECIMAL is exact, and your raw vs clean totals match to the cent.
- My answer:

**Q: How did you fill in the missing dates on segment-2 rows?**
- Hints:
  - Window function `MAX(date) OVER (PARTITION BY claim_id)`.
  - MAX ignores NULLs, so every segment gets segment 1's date.
  - Unlike GROUP BY, a window keeps every row (grain preserved).
- My answer:

**Q: Tell me about something your checks caught that you didn't expect.**
- Hints:
  - After cleaning, 192 outpatient rows still had no dates: segment 2 with no segment 1.
  - Profiling didn't catch it; checking the *output* did.
  - Decision: keep ($247K is real money), flag `orphan_segment`, leave the year NULL rather than invent one.
  - Lesson: verify transformations, not just inputs.
- My answer:

**Q: What happens if one of your cleaning steps fails halfway?**
- Hints:
  - All steps run in one transaction.
  - A failure triggers ROLLBACK and the previous clean tables stay intact.
  - No half-rebuilt layer where tables disagree.
- My answer:

## Validation (Phase 2b)

**Q: How do you know your data is good?**
- Hints:
  - 62 automated checks in 7 categories: reconciliation, duplicates, nulls, impossible dates, orphaned keys, values, outliers.
  - Three severities. Known issues are tolerated visibly, with a threshold.
  - Results are stored per run; the report is regenerated; the exit code stops the pipeline.
- My answer:

**Q: How do you know your checks actually work?**
- Hints:
  - Broke a copy of the data six ways on purpose: lost rows, a duplicate fill, reversed dates, an unknown member, an unmapped code, a known issue past tolerance.
  - Every one was caught, most by two checks.
  - Also: a crashed check counts as FAIL, and that caught a bug in my own check SQL.
- My answer:

**Q: Your data has known problems. Why doesn't validation just fail?**
- Hints:
  - The problems are documented and flagged, and they come from the synthetic source.
  - Failing every run would train people to ignore failures.
  - Tolerances (about 2× today's rate) catch the day it gets worse; tested at 5.2% → 11.9%.
- My answer:

**Q: How did you detect cost outliers, and why that method?**
- Hints:
  - Costs are right-skewed; dollar-scale IQR flagged 11%, which is meaningless.
  - Log-scale Tukey fences: 1.3% / 2.8% / 0%.
  - The extreme fence is above the CMS cap, so top-coding removed all extreme outliers. The high-cost analysis understates the tail.
- My answer:

**Q: What happens downstream when validation fails?**
- Hints:
  - Exit code 1. The pipeline runner (Phase 3) stops before building analysis tables.
  - The report lists failures first, with rows and dollars affected.
- My answer:

_(Questions for tests, SQL, the dashboard, and communication will be added as we build those phases.)_
