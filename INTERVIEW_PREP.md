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

_(Questions for cleaning, SQL, the dashboard, and communication will be added as we build those phases.)_
