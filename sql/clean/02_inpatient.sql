-- clean.inpatient: one row per claim SEGMENT (same grain as raw).
-- Key: (claim_id, segment). Count claims with COUNT(DISTINCT claim_id).
--
-- What changes from raw:
--   * Segment-2 rows inherit dates from segment 1 (finding #2).
--     `dates_inherited` marks which rows were filled. `orphan_segment` marks
--     segment-2 rows whose claim has no segment 1 (finding #14: 192 in
--     outpatient, 0 in inpatient). Those keep NULL dates and claim_year.
--   * claim_year = year of the THROUGH date (DECISIONS.md #12).
--   * 'OTHER' diagnosis placeholders -> NULL, with a flag (finding #8).
--   * Flags for negative and zero payments (findings #5, #6). Rows are kept.
--   * Dropped: 45 empty HCPCS columns (finding #3), procedure codes, physician
--     NPIs, and minor cost-sharing fields the analysis doesn't use. They stay
--     in raw.inpatient if ever needed.
--
-- The window function MAX(...) OVER (PARTITION BY CLM_ID) looks across all
-- rows of the same claim. Segment 2 has NULL dates, segment 1 has real ones,
-- and MAX ignores NULLs, so every row of the claim gets segment 1's date.
-- Unlike GROUP BY, a window function does not collapse rows: grain is preserved.

CREATE OR REPLACE TABLE clean.inpatient AS
WITH typed AS (
    SELECT
        CLM_ID                                          AS claim_id,
        TRY_CAST(SEGMENT AS INTEGER)                    AS segment,
        DESYNPUF_ID                                     AS member_id,
        PRVDR_NUM                                       AS provider_id,
        TRY_STRPTIME(CLM_FROM_DT,  '%Y%m%d')::DATE      AS from_date_raw,
        TRY_STRPTIME(CLM_THRU_DT,  '%Y%m%d')::DATE      AS thru_date_raw,
        TRY_STRPTIME(CLM_ADMSN_DT, '%Y%m%d')::DATE      AS admit_date,
        TRY_STRPTIME(NCH_BENE_DSCHRG_DT, '%Y%m%d')::DATE AS discharge_date,
        TRY_CAST(CLM_UTLZTN_DAY_CNT AS INTEGER)         AS utilization_days,
        CLM_DRG_CD                                      AS drg_code,
        NULLIF(ADMTNG_ICD9_DGNS_CD, 'OTHER')            AS admitting_dx,
        NULLIF(ICD9_DGNS_CD_1, 'OTHER')                 AS primary_dx,
        (ICD9_DGNS_CD_1 = 'OTHER')                      AS primary_dx_placeholder,
        TRY_CAST(CLM_PMT_AMT AS DECIMAL(12,2))          AS paid_amount,
        TRY_CAST(NCH_PRMRY_PYR_CLM_PD_AMT AS DECIMAL(12,2)) AS primary_payer_paid,
        TRY_CAST(NCH_BENE_IP_DDCTBL_AMT AS DECIMAL(12,2))   AS member_deductible,
        source_file
    FROM raw.inpatient
)
SELECT
    claim_id,
    segment,
    member_id,
    provider_id,
    MAX(from_date_raw) OVER (PARTITION BY claim_id)     AS from_date,
    MAX(thru_date_raw) OVER (PARTITION BY claim_id)     AS thru_date,
    (from_date_raw IS NULL)                             AS dates_inherited,
    -- A segment 2 with no segment 1 in the same claim has nowhere to
    -- inherit dates from; its dates and claim_year stay NULL.
    NOT BOOL_OR(segment = 1) OVER (PARTITION BY claim_id) AS orphan_segment,
    YEAR(MAX(thru_date_raw) OVER (PARTITION BY claim_id)) AS claim_year,
    admit_date,
    discharge_date,
    utilization_days,
    drg_code,
    admitting_dx,
    primary_dx,
    COALESCE(primary_dx_placeholder, FALSE)             AS primary_dx_placeholder,
    paid_amount,
    primary_payer_paid,
    member_deductible,
    (paid_amount < 0)                                   AS is_adjustment,
    (paid_amount = 0)                                   AS is_zero_paid,
    source_file
FROM typed;
