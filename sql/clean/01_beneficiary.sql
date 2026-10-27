-- clean.beneficiary: one row per member per year (same grain as raw).
--
-- What changes from raw:
--   * Text -> real types (DATE, INTEGER, BOOLEAN, DECIMAL).
--   * Cryptic CMS names -> readable snake_case names.
--   * Codes standardized:
--       BENE_ESRD_IND  '0'/'Y'  -> has_esrd BOOLEAN          (finding #9)
--       SP_* flags     '1'/'2'  -> has_* BOOLEAN, 1 = yes    (finding #10;
--                      likely coding, confirm in the DE 1.0 Codebook)
--   * Sex and race stay as CMS codes; labels belong in a lookup table, not
--     hard-coded here.
--
-- TRY_CAST / TRY_STRPTIME return NULL instead of failing on bad input.
-- Validation (Phase 2b) counts any value that was non-NULL in raw but NULL here,
-- so no conversion failure can go unnoticed.

CREATE OR REPLACE TABLE clean.beneficiary AS
SELECT
    DESYNPUF_ID                                         AS member_id,
    file_year                                           AS year,
    TRY_STRPTIME(BENE_BIRTH_DT, '%Y%m%d')::DATE         AS birth_date,
    TRY_STRPTIME(BENE_DEATH_DT, '%Y%m%d')::DATE         AS death_date,
    file_year - TRY_CAST(LEFT(BENE_BIRTH_DT, 4) AS INTEGER) AS age_in_year,
    BENE_SEX_IDENT_CD                                   AS sex_code,
    BENE_RACE_CD                                        AS race_code,
    SP_STATE_CODE                                       AS state_code,
    BENE_COUNTY_CD                                      AS county_code,

    -- Months of coverage during the year (0-12)
    TRY_CAST(BENE_HI_CVRAGE_TOT_MONS  AS INTEGER)       AS part_a_months,
    TRY_CAST(BENE_SMI_CVRAGE_TOT_MONS AS INTEGER)       AS part_b_months,
    TRY_CAST(BENE_HMO_CVRAGE_TOT_MONS AS INTEGER)       AS hmo_months,
    TRY_CAST(PLAN_CVRG_MOS_NUM        AS INTEGER)       AS part_d_months,

    CASE BENE_ESRD_IND WHEN 'Y' THEN TRUE WHEN '0' THEN FALSE END AS has_esrd,

    -- Chronic conditions: 1 = yes, 2 = no
    CASE SP_ALZHDMTA WHEN '1' THEN TRUE WHEN '2' THEN FALSE END AS has_alzheimers,
    CASE SP_CHF      WHEN '1' THEN TRUE WHEN '2' THEN FALSE END AS has_heart_failure,
    CASE SP_CHRNKIDN WHEN '1' THEN TRUE WHEN '2' THEN FALSE END AS has_chronic_kidney,
    CASE SP_CNCR     WHEN '1' THEN TRUE WHEN '2' THEN FALSE END AS has_cancer,
    CASE SP_COPD     WHEN '1' THEN TRUE WHEN '2' THEN FALSE END AS has_copd,
    CASE SP_DEPRESSN WHEN '1' THEN TRUE WHEN '2' THEN FALSE END AS has_depression,
    CASE SP_DIABETES WHEN '1' THEN TRUE WHEN '2' THEN FALSE END AS has_diabetes,
    CASE SP_ISCHMCHT WHEN '1' THEN TRUE WHEN '2' THEN FALSE END AS has_ischemic_heart,
    CASE SP_OSTEOPRS WHEN '1' THEN TRUE WHEN '2' THEN FALSE END AS has_osteoporosis,
    CASE SP_RA_OA    WHEN '1' THEN TRUE WHEN '2' THEN FALSE END AS has_arthritis,
    CASE SP_STRKETIA WHEN '1' THEN TRUE WHEN '2' THEN FALSE END AS has_stroke_tia,

    -- CMS's own annual payment summaries per member (useful later to
    -- reconcile against claim-level totals)
    TRY_CAST(MEDREIMB_IP  AS DECIMAL(12,2)) AS ip_medicare_paid,
    TRY_CAST(BENRES_IP    AS DECIMAL(12,2)) AS ip_member_paid,
    TRY_CAST(PPPYMT_IP    AS DECIMAL(12,2)) AS ip_primary_payer_paid,
    TRY_CAST(MEDREIMB_OP  AS DECIMAL(12,2)) AS op_medicare_paid,
    TRY_CAST(BENRES_OP    AS DECIMAL(12,2)) AS op_member_paid,
    TRY_CAST(PPPYMT_OP    AS DECIMAL(12,2)) AS op_primary_payer_paid,
    TRY_CAST(MEDREIMB_CAR AS DECIMAL(12,2)) AS carrier_medicare_paid,
    TRY_CAST(BENRES_CAR   AS DECIMAL(12,2)) AS carrier_member_paid,
    TRY_CAST(PPPYMT_CAR   AS DECIMAL(12,2)) AS carrier_primary_payer_paid,

    source_file
FROM raw.beneficiary;
