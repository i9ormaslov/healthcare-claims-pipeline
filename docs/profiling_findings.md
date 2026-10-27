# Profiling Findings: DE-SynPUF Sample 2 (raw layer)

Source: `notebooks/01_profile_raw.ipynb`, run against `raw.*` tables loaded by `src/ingest.py`.
Every count is exact. Profiled 2026-10-27.
This document is the input to Phase 2 (`src/validate.py` and the data-quality report).

## Data at a glance

| Table | Rows | Columns | Grain (verified key) |
|---|---:|---:|---|
| beneficiary | 343,858 | 32 + 2 | one member per year: `(DESYNPUF_ID, file_year)` |
| inpatient | 66,494 | 81 + 1 | one claim segment: `(CLM_ID, SEGMENT)` |
| outpatient | 792,562 | 76 + 1 | one claim segment: `(CLM_ID, SEGMENT)` |
| pde | 5,561,154 | 8 + 1 | one prescription fill: `PDE_ID` |

The +1 or +2 columns are lineage added at ingest: `source_file`, plus `file_year` for beneficiary.

Members: 116,395 in 2008 → 114,618 in 2009 → 112,845 in 2010. The decline comes from deaths and members leaving fee-for-service; no new members enter.

## Findings and the Phase 2 rule each one implies

| # | Finding | Count | Severity | Phase 2 rule |
|---|---|---:|---|---|
| 1 | `CLM_ID` not unique; key is `(CLM_ID, SEGMENT)` | 60 IP / 11,009 OP duplicate IDs | High | Claims = `COUNT(DISTINCT CLM_ID)`; payments summed over segments |
| 2 | Segment-2 rows have no dates but carry payments | 59/60 IP, 10,968/11,201 OP with payment | High | Inherit dates from segment 1; never drop segment 2 |
| 3 | Inpatient `HCPCS_CD_1..45` 100% empty | 45 columns | Low | Drop (inpatient is billed by DRG) |
| 4 | Claims start in 2007, end in 2008 | 204 IP / 330 OP | Low | Claim year = through date (DECISIONS #12) |
| 5 | Negative `CLM_PMT_AMT` | 58 IP / 2,557 OP | Medium | Flag `is_adjustment`; keep in totals; exclude from averages |
| 6 | Zero `CLM_PMT_AMT` | 1,980 IP / 30,164 OP | Low | Flag `is_zero_paid` |
| 7 | Costs rounded and top-coded | 100% of OP payments are multiples of $10; 8,611 OP rows at the $3,300 max | Medium | Use percentile-based outlier rules; caveat in summary |
| 8 | `OTHER` placeholder codes | 5,640 OP dx1 (5,616 in segment 2); 15 Rx drug codes | Medium | NULL + flag; exclude from top-N |
| 9 | `BENE_ESRD_IND` coded `0`/`Y` | 92.1% / 7.9% | Medium | Standardize to boolean |
| 10 | `SP_*` chronic flags coded 1/2 | Diabetes: 29–42% if 1 = yes | Medium | Map 1 → true, 2 → false *(confirm in codebook)* |
| 11 | Rx patient paid > total drug cost | 288,824 fills (5.2%) | High | Flag `rx_cost_inconsistent`; exclude from cost-per-fill |
| 12 | Rx quantity = 0 / days supply = 0 | 232,166 / 118,118 fills | High | Flag `rx_nothing_dispensed` |
| 13 | Date format, date logic, after-death, and orphan checks | 0 violations | Info | Keep as automated checks |
| 14 | *Found during cleaning:* segment-2 rows with no segment 1 | 192 OP claims, $247,460 | Medium | Keep, flag `orphan_segment`, leave year NULL (DECISIONS #14) |

## Caveats to carry into every summary
- **Synthetic data.** CMS synthesis weakens real relationships between variables. Findings demonstrate method, not clinical truth. For example, the five lipid-disorder codes have suspiciously even counts.
- **No carrier claims** (DECISIONS #5), so "outpatient" means institutional outpatient only, and total cost per member is understated.
- **Top-coded costs** mean the true high-cost tail is not visible.
