-- clean.outpatient: one row per claim SEGMENT (same grain as raw).
-- Same rules as clean.inpatient (see 02_inpatient.sql for the reasoning).
-- Outpatient has no admit/discharge dates or DRG; it bills by HCPCS, so the
-- first HCPCS code is kept as a sample of the services on the claim.

CREATE OR REPLACE TABLE clean.outpatient AS
WITH typed AS (
    SELECT
        CLM_ID                                          AS claim_id,
        TRY_CAST(SEGMENT AS INTEGER)                    AS segment,
        DESYNPUF_ID                                     AS member_id,
        PRVDR_NUM                                       AS provider_id,
        TRY_STRPTIME(CLM_FROM_DT, '%Y%m%d')::DATE       AS from_date_raw,
        TRY_STRPTIME(CLM_THRU_DT, '%Y%m%d')::DATE       AS thru_date_raw,
        NULLIF(ADMTNG_ICD9_DGNS_CD, 'OTHER')            AS admitting_dx,
        NULLIF(ICD9_DGNS_CD_1, 'OTHER')                 AS primary_dx,
        (ICD9_DGNS_CD_1 = 'OTHER')                      AS primary_dx_placeholder,
        HCPCS_CD_1                                      AS first_hcpcs,
        TRY_CAST(CLM_PMT_AMT AS DECIMAL(12,2))          AS paid_amount,
        TRY_CAST(NCH_PRMRY_PYR_CLM_PD_AMT AS DECIMAL(12,2)) AS primary_payer_paid,
        TRY_CAST(NCH_BENE_PTB_DDCTBL_AMT AS DECIMAL(12,2))  AS member_deductible,
        TRY_CAST(NCH_BENE_PTB_COINSRNC_AMT AS DECIMAL(12,2)) AS member_coinsurance,
        source_file
    FROM raw.outpatient
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
    admitting_dx,
    primary_dx,
    COALESCE(primary_dx_placeholder, FALSE)             AS primary_dx_placeholder,
    first_hcpcs,
    paid_amount,
    primary_payer_paid,
    member_deductible,
    member_coinsurance,
    (paid_amount < 0)                                   AS is_adjustment,
    (paid_amount = 0)                                   AS is_zero_paid,
    source_file
FROM typed;
