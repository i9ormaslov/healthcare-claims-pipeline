"""
checks.py - The data-quality rules, written as data.

WHY DECLARATIVE
Each check is a record: what it tests, how bad a violation is, and one SQL
query. validate.py runs them all the same way. Adding a check = adding one
entry here; the runner, history table, and report pick it up automatically.

THE SQL CONTRACT
Every query returns exactly one row with these columns:
    violations  rows that break the rule
    total       rows the rule applies to (the denominator for %)
    amount      dollars on violating rows (NULL when not meaningful)
    detail      short explanation (NULL when not needed)

SEVERITY
    error  Must be zero. Any violation fails the run (exit code 1).
           Duplicates, lost rows, impossible dates, broken keys.
    warn   A known, documented data issue. Reported, not fatal, unless the
           violation rate exceeds fail_above_pct. Then something changed
           upstream and a human should look.
    info   Context for analysts (outliers, top-coding). Never fails.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Check:
    id: str
    category: str
    table: str
    description: str
    severity: str                        # "error" | "warn" | "info"
    sql: str
    fail_above_pct: float | None = None  # warn checks only
    reference: str = ""                  # where the reasoning is documented


# ---------------------------------------------------------------------------
# Helpers that generate repetitive SQL
# ---------------------------------------------------------------------------

def _count_sql(table: str, condition: str, amount: str | None = None) -> str:
    """Violations = rows matching `condition` in `table`."""
    amt = f"SUM({amount}) FILTER (WHERE {condition})" if amount else "NULL"
    return f"""
        SELECT COUNT(*) FILTER (WHERE {condition}) AS violations,
               COUNT(*)                            AS total,
               {amt}                               AS amount,
               NULL                                AS detail
        FROM {table}"""


def _unique_sql(table: str, key: str) -> str:
    """Violations = rows beyond the first for each key value."""
    return f"""
        SELECT COUNT(*) - COUNT(DISTINCT ({key})) AS violations,
               COUNT(*) AS total, NULL AS amount,
               'key: {key}' AS detail
        FROM {table}"""


def _row_count_sql(raw: str, clean: str) -> str:
    return f"""
        SELECT ABS((SELECT COUNT(*) FROM {raw}) - (SELECT COUNT(*) FROM {clean})) AS violations,
               (SELECT COUNT(*) FROM {raw}) AS total, NULL AS amount,
               'raw ' || (SELECT COUNT(*) FROM {raw}) || ' vs clean ' || (SELECT COUNT(*) FROM {clean}) AS detail"""


def _money_sql(raw: str, raw_col: str, clean: str, clean_col: str) -> str:
    # Raw is text: cast with exact DECIMAL so the comparison is to the cent.
    return f"""
        WITH t AS (
            SELECT (SELECT SUM(TRY_CAST({raw_col} AS DECIMAL(14,2))) FROM {raw})  AS raw_total,
                   (SELECT SUM({clean_col}) FROM {clean})                        AS clean_total
        )
        SELECT CASE WHEN raw_total = clean_total THEN 0 ELSE 1 END AS violations,
               1 AS total,
               ABS(raw_total - clean_total) AS amount,
               'raw $' || raw_total || ' vs clean $' || clean_total AS detail
        FROM t"""


def _conversion_loss_sql(raw: str, clean: str, raw_key: list[str],
                         clean_key: list[str], cols: list[tuple[str, str]]) -> str:
    """Values present in raw but NULL after typing = silent conversion failures."""
    # No table prefixes: each CTE reads one table, and keys may be expressions
    # like CAST(segment AS VARCHAR), which can't take a "c." prefix.
    sel_r = ", ".join(f"{rk} AS rk{i}" for i, rk in enumerate(raw_key))
    sel_r += ", " + ", ".join(f"{rc} AS r_{n}" for n, (rc, _) in enumerate(cols))
    sel_c = ", ".join(f"{ck} AS ck{i}" for i, ck in enumerate(clean_key))
    sel_c += ", " + ", ".join(f"{cc} AS c_{n}" for n, (_, cc) in enumerate(cols))
    on = " AND ".join(f"r.rk{i} = c.ck{i}" for i in range(len(raw_key)))
    per_col = " UNION ALL ".join(
        f"SELECT '{cc}' AS col, COUNT(*) FILTER (WHERE r_{n} IS NOT NULL AND c_{n} IS NULL) AS n FROM j"
        for n, (_, cc) in enumerate(cols)
    )
    return f"""
        WITH r AS (SELECT {sel_r} FROM {raw}),
             c AS (SELECT {sel_c} FROM {clean}),
             j AS (SELECT * FROM r JOIN c ON {on}),
             losses AS ({per_col})
        SELECT SUM(n) AS violations,
               (SELECT COUNT(*) FROM {raw}) AS total,
               NULL AS amount,
               COALESCE(STRING_AGG(col || '=' || n, ', ') FILTER (WHERE n > 0), 'none') AS detail
        FROM losses"""


def _outlier_sql(table: str, amount: str, where: str = "TRUE") -> str:
    """High-cost rows by Tukey's fences on the LOG of the amount.

    Why log: costs are extremely right-skewed (outpatient median $70, max
    $3,300). On the raw dollar scale the quartile range is tiny, so a dollar
    fence flags ~11% of claims - not outliers, just the normal right tail.
    On the log scale, distance means "how many times larger than typical",
    which is how cost data behaves.

    Fences: mild = Q3 + 1.5*IQR (counted), extreme = Q3 + 3*IQR (reported).
    Percentiles, not mean/standard deviation, so the CMS cap can't distort it.
    """
    return f"""
        WITH s AS (
            SELECT QUANTILE_CONT(LN({amount}::DOUBLE), 0.25) AS q1,
                   QUANTILE_CONT(LN({amount}::DOUBLE), 0.75) AS q3,
                   MAX({amount}) AS mx
            FROM {table} WHERE {where}
        ),
        b AS (SELECT EXP(q3 + 1.5 * (q3 - q1)) AS mild,
                     EXP(q3 + 3.0 * (q3 - q1)) AS extreme, mx FROM s)
        SELECT COUNT(*) FILTER (WHERE {amount} > b.mild) AS violations,
               COUNT(*) AS total,
               SUM({amount}) FILTER (WHERE {amount} > b.mild) AS amount,
               'above $' || ROUND(b.mild)::BIGINT
                 || CASE WHEN b.extreme > b.mx
                         THEN '; extreme fence $' || ROUND(b.extreme)::BIGINT
                              || ' is above the $' || ROUND(b.mx)::BIGINT
                              || ' cap, so top-coding removed all extreme outliers'
                         ELSE '' END AS detail
        FROM {table}, b WHERE {where}
        GROUP BY b.mild, b.extreme, b.mx"""


def _at_max_sql(table: str, amount: str) -> str:
    """Many rows sitting at exactly the maximum value = a cap (top-coding)."""
    return f"""
        WITH m AS (SELECT MAX({amount}) AS mx FROM {table})
        SELECT COUNT(*) FILTER (WHERE {amount} = m.mx) AS violations,
               COUNT(*) AS total,
               SUM({amount}) FILTER (WHERE {amount} = m.mx) AS amount,
               'max $' || m.mx AS detail
        FROM {table}, m GROUP BY m.mx"""


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------

CLAIM_TABLES = [("inpatient", "raw.inpatient", "clean.inpatient"),
                ("outpatient", "raw.outpatient", "clean.outpatient")]

CHECKS: list[Check] = []
add = CHECKS.append

# 1. Reconciliation: did cleaning lose or invent anything? ------------------
for name, raw, clean in [("beneficiary", "raw.beneficiary", "clean.beneficiary"),
                         *CLAIM_TABLES,
                         ("rx_fills", "raw.pde", "clean.rx_fills")]:
    add(Check(f"REC_ROWS_{name.upper()}", "reconciliation", clean,
              "Clean has exactly the same number of rows as raw",
              "error", _row_count_sql(raw, clean), reference="DECISIONS #13"))

for name, raw, clean in CLAIM_TABLES:
    add(Check(f"REC_PAID_{name.upper()}", "reconciliation", clean,
              "Total paid amount matches raw to the cent",
              "error", _money_sql(raw, "CLM_PMT_AMT", clean, "paid_amount"),
              reference="DECISIONS #13"))
add(Check("REC_COST_RX", "reconciliation", "clean.rx_fills",
          "Total drug cost matches raw to the cent",
          "error", _money_sql("raw.pde", "TOT_RX_CST_AMT", "clean.rx_fills", "total_cost"),
          reference="DECISIONS #13"))

add(Check("REC_TYPES_BENEFICIARY", "reconciliation", "clean.beneficiary",
          "No value lost when converting text to typed columns",
          "error", _conversion_loss_sql(
              "raw.beneficiary", "clean.beneficiary",
              ["DESYNPUF_ID", "file_year"], ["member_id", "year"],
              [("BENE_BIRTH_DT", "birth_date"), ("BENE_DEATH_DT", "death_date"),
               ("BENE_HI_CVRAGE_TOT_MONS", "part_a_months"),
               ("BENE_SMI_CVRAGE_TOT_MONS", "part_b_months"),
               ("BENE_HMO_CVRAGE_TOT_MONS", "hmo_months"),
               ("PLAN_CVRG_MOS_NUM", "part_d_months"),
               ("BENE_ESRD_IND", "has_esrd"), ("SP_DIABETES", "has_diabetes"),
               ("SP_CHF", "has_heart_failure"), ("SP_CNCR", "has_cancer"),
               ("MEDREIMB_IP", "ip_medicare_paid"), ("MEDREIMB_OP", "op_medicare_paid")]),
          reference="DECISIONS #6"))
for name, raw, clean in CLAIM_TABLES:
    cols = [("CLM_PMT_AMT", "paid_amount"), ("NCH_PRMRY_PYR_CLM_PD_AMT", "primary_payer_paid"),
            ("CLM_FROM_DT", "from_date"), ("CLM_THRU_DT", "thru_date")]
    if name == "inpatient":
        cols += [("CLM_ADMSN_DT", "admit_date"), ("NCH_BENE_DSCHRG_DT", "discharge_date"),
                 ("CLM_UTLZTN_DAY_CNT", "utilization_days")]
    add(Check(f"REC_TYPES_{name.upper()}", "reconciliation", clean,
              "No value lost when converting text to typed columns",
              "error", _conversion_loss_sql(raw, clean, ["CLM_ID", "SEGMENT"],
                                            ["claim_id", "CAST(segment AS VARCHAR)"], cols),
              reference="DECISIONS #6"))
add(Check("REC_TYPES_RX", "reconciliation", "clean.rx_fills",
          "No value lost when converting text to typed columns",
          "error", _conversion_loss_sql(
              "raw.pde", "clean.rx_fills", ["PDE_ID"], ["fill_id"],
              [("SRVC_DT", "service_date"), ("QTY_DSPNSD_NUM", "quantity"),
               ("DAYS_SUPLY_NUM", "days_supply"), ("PTNT_PAY_AMT", "member_paid"),
               ("TOT_RX_CST_AMT", "total_cost")]),
          reference="DECISIONS #6"))

# 2. Duplicates ---------------------------------------------------------------
add(Check("DUP_BENEFICIARY", "duplicates", "clean.beneficiary",
          "One row per member per year", "error",
          _unique_sql("clean.beneficiary", "member_id, year"), reference="Profiling #1"))
for name, _, clean in CLAIM_TABLES:
    add(Check(f"DUP_{name.upper()}", "duplicates", clean,
              "One row per claim segment", "error",
              _unique_sql(clean, "claim_id, segment"), reference="DECISIONS #10"))
add(Check("DUP_RX", "duplicates", "clean.rx_fills",
          "One row per prescription fill", "error",
          _unique_sql("clean.rx_fills", "fill_id")))
for name, raw, _ in CLAIM_TABLES:
    add(Check(f"DUP_EXACT_{name.upper()}", "duplicates", raw,
              "No fully identical rows (same claim submitted twice)", "error",
              f"""SELECT COUNT(*) - (SELECT COUNT(*) FROM (SELECT DISTINCT * EXCLUDE (source_file) FROM {raw})) AS violations,
                         COUNT(*) AS total, NULL AS amount, NULL AS detail FROM {raw}"""))

# 3. Required values (nulls) --------------------------------------------------
add(Check("NULL_KEYS_BENEFICIARY", "nulls", "clean.beneficiary",
          "member_id, year, birth_date always present", "error",
          _count_sql("clean.beneficiary", "member_id IS NULL OR year IS NULL OR birth_date IS NULL")))
for name, _, clean in CLAIM_TABLES:
    add(Check(f"NULL_KEYS_{name.upper()}", "nulls", clean,
              "claim_id, segment, member_id, paid_amount always present", "error",
              _count_sql(clean, "claim_id IS NULL OR segment IS NULL OR member_id IS NULL OR paid_amount IS NULL")))
    add(Check(f"NULL_DATES_{name.upper()}", "nulls", clean,
              "Every missing date is explained by an orphan segment", "error",
              _count_sql(clean, "(from_date IS NULL OR thru_date IS NULL) AND NOT orphan_segment", "paid_amount"),
              reference="DECISIONS #14"))
add(Check("NULL_KEYS_RX", "nulls", "clean.rx_fills",
          "fill_id, member_id, service_date, total_cost always present", "error",
          _count_sql("clean.rx_fills", "fill_id IS NULL OR member_id IS NULL OR service_date IS NULL OR total_cost IS NULL")))
add(Check("NULL_CODES_BENEFICIARY", "nulls", "clean.beneficiary",
          "Every ESRD / chronic-condition code mapped to true/false (no unknown codes)", "error",
          _count_sql("clean.beneficiary", " OR ".join(f"{c} IS NULL" for c in [
              "has_esrd", "has_alzheimers", "has_heart_failure", "has_chronic_kidney", "has_cancer",
              "has_copd", "has_depression", "has_diabetes", "has_ischemic_heart",
              "has_osteoporosis", "has_arthritis", "has_stroke_tia"])),
          reference="Profiling #9, #10"))

# 4. Impossible dates ---------------------------------------------------------
LIFE = "(SELECT member_id, MAX(birth_date) AS birth_date, MAX(death_date) AS death_date FROM clean.beneficiary GROUP BY 1)"
for name, _, clean in CLAIM_TABLES:
    add(Check(f"DATE_ORDER_{name.upper()}", "impossible_dates", clean,
              "Claim through date is not before from date", "error",
              _count_sql(clean, "thru_date < from_date", "paid_amount")))
    add(Check(f"DATE_RANGE_{name.upper()}", "impossible_dates", clean,
              "Claim year is within 2008-2010", "error",
              _count_sql(clean, "claim_year NOT BETWEEN 2008 AND 2010", "paid_amount")))
    add(Check(f"DATE_AFTER_DEATH_{name.upper()}", "impossible_dates", clean,
              "No service after the member's death", "error",
              f"""SELECT COUNT(*) FILTER (WHERE c.from_date > l.death_date) AS violations,
                         COUNT(*) AS total,
                         SUM(c.paid_amount) FILTER (WHERE c.from_date > l.death_date) AS amount,
                         NULL AS detail
                  FROM {clean} c JOIN {LIFE} l USING (member_id)"""))
    add(Check(f"DATE_BEFORE_BIRTH_{name.upper()}", "impossible_dates", clean,
              "No service before the member's birth", "error",
              f"""SELECT COUNT(*) FILTER (WHERE c.from_date < l.birth_date) AS violations,
                         COUNT(*) AS total, NULL AS amount, NULL AS detail
                  FROM {clean} c JOIN {LIFE} l USING (member_id)"""))
add(Check("DATE_DISCHARGE_INPATIENT", "impossible_dates", "clean.inpatient",
          "Discharge date is not before admission date", "error",
          _count_sql("clean.inpatient", "discharge_date < admit_date", "paid_amount")))
add(Check("DATE_AFTER_DEATH_RX", "impossible_dates", "clean.rx_fills",
          "No prescription filled after the member's death", "error",
          f"""SELECT COUNT(*) FILTER (WHERE r.service_date > l.death_date) AS violations,
                     COUNT(*) AS total,
                     SUM(r.total_cost) FILTER (WHERE r.service_date > l.death_date) AS amount,
                     NULL AS detail
              FROM clean.rx_fills r JOIN {LIFE} l USING (member_id)"""))
add(Check("DATE_RANGE_RX", "impossible_dates", "clean.rx_fills",
          "Fill year is within 2008-2010", "error",
          _count_sql("clean.rx_fills", "fill_year NOT BETWEEN 2008 AND 2010", "total_cost")))
add(Check("DATE_DEATH_BEFORE_BIRTH", "impossible_dates", "clean.beneficiary",
          "Death date is not before birth date", "error",
          _count_sql("clean.beneficiary", "death_date < birth_date")))
add(Check("AGE_RANGE", "impossible_dates", "clean.beneficiary",
          "Age in year is between 0 and 120", "error",
          _count_sql("clean.beneficiary", "age_in_year NOT BETWEEN 0 AND 120")))

# 5. Orphaned keys ------------------------------------------------------------
for name, _, clean in CLAIM_TABLES + [("rx_fills", None, "clean.rx_fills")]:
    amt = "total_cost" if name == "rx_fills" else "paid_amount"
    year = "fill_year" if name == "rx_fills" else "claim_year"
    add(Check(f"ORPHAN_MEMBER_{name.upper()}", "orphaned_keys", clean,
              "Every row belongs to a known member", "error",
              _count_sql(clean, "member_id NOT IN (SELECT member_id FROM clean.beneficiary)", amt),
              reference="DECISIONS #4, #8"))
    add(Check(f"ORPHAN_MEMBER_YEAR_{name.upper()}", "orphaned_keys", clean,
              "Member has a beneficiary row for the year of service", "error",
              f"""SELECT COUNT(*) FILTER (WHERE b.member_id IS NULL AND c.{year} IS NOT NULL) AS violations,
                         COUNT(*) AS total,
                         SUM(c.{amt}) FILTER (WHERE b.member_id IS NULL AND c.{year} IS NOT NULL) AS amount,
                         NULL AS detail
                  FROM {clean} c LEFT JOIN clean.beneficiary b
                    ON b.member_id = c.member_id AND b.year = c.{year}"""))
for name, _, clean in CLAIM_TABLES:
    add(Check(f"ORPHAN_SEGMENT_{name.upper()}", "orphaned_keys", clean,
              "Segment-2 rows whose claim has no segment 1 (dates and year unknown)", "warn",
              _count_sql(clean, "orphan_segment", "paid_amount"),
              fail_above_pct=1.0, reference="DECISIONS #14"))

# 6. Known value issues (flags from profiling) --------------------------------
for name, _, clean in CLAIM_TABLES:
    add(Check(f"VAL_NEGATIVE_PAID_{name.upper()}", "values", clean,
              "Negative payments (likely adjustments; kept and flagged)", "warn",
              _count_sql(clean, "is_adjustment", "paid_amount"),
              fail_above_pct=5.0, reference="DECISIONS #11"))
    add(Check(f"VAL_ZERO_PAID_{name.upper()}", "values", clean,
              "Zero-payment claims (kept and flagged)", "warn",
              _count_sql(clean, "is_zero_paid"),
              fail_above_pct=10.0, reference="DECISIONS #11"))
add(Check("VAL_DX_PLACEHOLDER_OUTPATIENT", "values", "clean.outpatient",
          "Primary diagnosis was the placeholder 'OTHER'", "warn",
          _count_sql("clean.outpatient", "primary_dx_placeholder"),
          fail_above_pct=2.0, reference="Profiling #8"))
add(Check("VAL_DX_PLACEHOLDER_INPATIENT", "values", "clean.inpatient",
          "Primary diagnosis was the placeholder 'OTHER'", "warn",
          _count_sql("clean.inpatient", "primary_dx_placeholder"),
          fail_above_pct=2.0, reference="Profiling #8"))
add(Check("VAL_DRUG_PLACEHOLDER_RX", "values", "clean.rx_fills",
          "Drug code was the placeholder 'OTHER'", "warn",
          _count_sql("clean.rx_fills", "drug_code_placeholder", "total_cost"),
          fail_above_pct=1.0, reference="Profiling #8"))
add(Check("VAL_RX_COST_INCONSISTENT", "values", "clean.rx_fills",
          "Member paid more than the total drug cost (impossible)", "warn",
          _count_sql("clean.rx_fills", "rx_cost_inconsistent", "total_cost"),
          fail_above_pct=10.0, reference="Profiling #11"))
add(Check("VAL_RX_NOTHING_DISPENSED", "values", "clean.rx_fills",
          "Quantity or days supply is zero", "warn",
          _count_sql("clean.rx_fills", "rx_nothing_dispensed", "total_cost"),
          fail_above_pct=10.0, reference="Profiling #12"))
add(Check("VAL_NEGATIVE_RX", "values", "clean.rx_fills",
          "No negative drug costs or member payments", "error",
          _count_sql("clean.rx_fills", "total_cost < 0 OR member_paid < 0")))
add(Check("VAL_COVERAGE_MONTHS", "values", "clean.beneficiary",
          "Coverage months are between 0 and 12", "error",
          _count_sql("clean.beneficiary", " OR ".join(
              f"{c} NOT BETWEEN 0 AND 12" for c in ["part_a_months", "part_b_months", "hmo_months", "part_d_months"]))))

# 7. Outliers and top-coding (context, never fatal) ---------------------------
for name, _, clean in CLAIM_TABLES:
    add(Check(f"OUTLIER_PAID_{name.upper()}", "outliers", clean,
              "High-cost claims (log-scale Tukey fence; positive payments)", "info",
              _outlier_sql(clean, "paid_amount", "paid_amount > 0"), reference="Profiling #7"))
    add(Check(f"TOPCODE_PAID_{name.upper()}", "outliers", clean,
              "Rows at exactly the maximum payment (evidence of a cap)", "info",
              _at_max_sql(clean, "paid_amount"), reference="Profiling #7"))
add(Check("OUTLIER_COST_RX", "outliers", "clean.rx_fills",
          "High-cost fills (log-scale Tukey fence; positive costs)", "info",
          _outlier_sql("clean.rx_fills", "total_cost", "total_cost > 0"), reference="Profiling #7"))
add(Check("TOPCODE_COST_RX", "outliers", "clean.rx_fills",
          "Rows at exactly the maximum drug cost (evidence of a cap)", "info",
          _at_max_sql("clean.rx_fills", "total_cost"), reference="Profiling #7"))

# Guard: IDs must be unique, or history and the report get confusing.
assert len({c.id for c in CHECKS}) == len(CHECKS), "duplicate check id"
