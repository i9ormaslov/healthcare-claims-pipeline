-- clean.rx_fills: one row per prescription fill (Part D event). Key: fill_id.
--
-- Flags from profiling (findings #8, #11, #12). Rows are kept, not deleted:
--   drug_code_placeholder  - PROD_SRVC_ID was 'OTHER' instead of a real NDC
--   rx_nothing_dispensed   - quantity or days supply is 0
--   rx_cost_inconsistent   - member paid more than the total drug cost,
--                            which is impossible (member share is part of total)
-- Cost-per-fill metrics should exclude rows where either rx_ flag is TRUE.

CREATE OR REPLACE TABLE clean.rx_fills AS
SELECT
    PDE_ID                                              AS fill_id,
    DESYNPUF_ID                                         AS member_id,
    TRY_STRPTIME(SRVC_DT, '%Y%m%d')::DATE               AS service_date,
    TRY_CAST(LEFT(SRVC_DT, 4) AS INTEGER)               AS fill_year,
    NULLIF(PROD_SRVC_ID, 'OTHER')                       AS drug_code,
    (PROD_SRVC_ID = 'OTHER')                            AS drug_code_placeholder,
    TRY_CAST(QTY_DSPNSD_NUM AS DECIMAL(12,3))           AS quantity,
    TRY_CAST(DAYS_SUPLY_NUM AS INTEGER)                 AS days_supply,
    TRY_CAST(PTNT_PAY_AMT   AS DECIMAL(12,2))           AS member_paid,
    TRY_CAST(TOT_RX_CST_AMT AS DECIMAL(12,2))           AS total_cost,
    (TRY_CAST(QTY_DSPNSD_NUM AS DECIMAL(12,3)) = 0
       OR TRY_CAST(DAYS_SUPLY_NUM AS INTEGER) = 0)      AS rx_nothing_dispensed,
    (TRY_CAST(PTNT_PAY_AMT AS DECIMAL(12,2))
       > TRY_CAST(TOT_RX_CST_AMT AS DECIMAL(12,2)))     AS rx_cost_inconsistent,
    source_file
FROM raw.pde;
