"""
One-off setup script: create schema objects and configure AlloyDB AI NL.

Run this once from Cloud Shell (or locally via the AlloyDB Auth Proxy)
AFTER setting the required environment variables and AFTER deploying the
sql/init.sql schema DDL:

    python scripts/setup_schema.py --csv /path/to/financial_dataset_SME.csv

Flags:
    --csv PATH      Path to the SME CSV file to load.
    --skip-load     Skip CSV loading (schema + NL setup only).
    --skip-nl       Skip AlloyDB AI NL setup (schema + load only).
    --refresh-only  Only refresh the value index (run after re-loading data).
"""

import argparse
import io
import os
import re
import sys

import pandas as pd

# Allow `python scripts/setup_schema.py` from the project root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db import get_pool, run_sql
from app.nl_setup import (
    add_domain_context,
    add_templates,
    apply_schema_context,
    create_nl_config,
    create_value_index,
    enable_extension,
    refresh_value_index,
)

# ---------------------------------------------------------------------------
# Schema DDL  (mirrors sql/init.sql – executed programmatically so the
# script is self-contained; safe to run multiple times due to IF NOT EXISTS)
# ---------------------------------------------------------------------------
_DDL = """
CREATE SCHEMA IF NOT EXISTS sme_risk;

CREATE TABLE IF NOT EXISTS sme_risk.sme_financial (
    has_financial_questions          text,
    sme_age                          int,
    sme_type                         int,
    industry_sector                  int,
    sme_size_category                int,
    literacy_accounting              numeric,
    literacy_budgeting               numeric,
    literacy_investment_evaluation   numeric,
    literacy_credit_knowledge        numeric,
    risk_awareness                   numeric,
    risk_evaluation                  numeric,
    risk_mitigation_strategies       numeric,
    risk_taking_willingness          numeric,
    assessment_data_driven           numeric,
    assessment_expert_consultation   numeric,
    assessment_scenario_analysis     numeric,
    assessment_internal_evaluation   numeric,
    decision_autonomy                numeric,
    decision_consultation            numeric,
    decision_financial_advisor       numeric,
    decision_strategic_alignment     numeric,
    decision_investment_choices      numeric,
    decision_loan_approval           numeric,
    decision_capital_allocation      numeric,
    decision_cashflow_management     numeric,
    analysis_accounting_tools        numeric,
    analysis_financial_ratios        numeric,
    analysis_forecasting             numeric,
    analysis_benchmarking            numeric,
    liquidity_stability              numeric,
    uses_digital_finance             int,
    annual_revenue_category          text,
    financial_distress               int,
    distress_label text GENERATED ALWAYS AS (
        CASE WHEN financial_distress = 1 THEN 'Distressed' ELSE 'Stable' END
    ) STORED
);

CREATE INDEX IF NOT EXISTS idx_sme_sector        ON sme_risk.sme_financial(industry_sector);
CREATE INDEX IF NOT EXISTS idx_sme_revenue       ON sme_risk.sme_financial(annual_revenue_category);
CREATE INDEX IF NOT EXISTS idx_sme_digital_finance ON sme_risk.sme_financial(uses_digital_finance);
CREATE INDEX IF NOT EXISTS idx_sme_distress      ON sme_risk.sme_financial(financial_distress);

CREATE OR REPLACE VIEW sme_risk.vw_distress_rate_by_segment AS
SELECT
    industry_sector,
    sme_size_category,
    annual_revenue_category,
    COUNT(*)                         AS total_smes,
    AVG(financial_distress::numeric) AS distress_rate
FROM sme_risk.sme_financial
GROUP BY industry_sector, sme_size_category, annual_revenue_category;
"""


def _normalize_col(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    return name.strip("_")


INT_COLS = [
    "sme_age",
    "sme_type",
    "industry_sector",
    "sme_size_category",
    "uses_digital_finance",
    "financial_distress",
]


def load_csv(csv_path: str) -> None:
    print(f"[load] Reading {csv_path} …")
    df_raw = pd.read_csv(csv_path)
    df = df_raw.rename(columns={c: _normalize_col(c) for c in df_raw.columns})
    for col in INT_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    # Exclude the generated column from the COPY target list.
    cols = [c for c in df.columns if c != "distress_label"]
    buf = io.StringIO()
    df[cols].to_csv(buf, index=False, header=False)
    buf.seek(0)

    copy_cols = ", ".join(cols)
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE sme_risk.sme_financial;")
            with cur.copy(
                f"COPY sme_risk.sme_financial ({copy_cols}) FROM STDIN WITH CSV"
            ) as copy:
                copy.write(buf.read())
        conn.commit()

    rows = run_sql("SELECT COUNT(*) AS n FROM sme_risk.sme_financial;")
    print(f"[load] Loaded {rows[0]['n']:,} rows.")


def setup_schema() -> None:
    print("[schema] Applying DDL …")
    run_sql(_DDL, fetch=False)
    print("[schema] Done.")


def setup_nl() -> None:
    print("[nl] Enabling extensions …")
    enable_extension()
    print("[nl] Creating NL config …")
    create_nl_config()
    print("[nl] Adding domain context …")
    add_domain_context()
    print("[nl] Applying schema context …")
    apply_schema_context()
    print("[nl] Adding query templates …")
    add_templates()
    print("[nl] Creating value index …")
    create_value_index()
    print("[nl] Done.")


def main() -> None:
    parser = argparse.ArgumentParser(description="AlloyDB SME demo setup")
    parser.add_argument("--csv", metavar="PATH", help="Path to SME CSV file")
    parser.add_argument("--skip-load", action="store_true")
    parser.add_argument("--skip-nl", action="store_true")
    parser.add_argument("--refresh-only", action="store_true")
    args = parser.parse_args()

    if args.refresh_only:
        print("[nl] Refreshing value index …")
        refresh_value_index()
        print("[nl] Done.")
        return

    setup_schema()

    if not args.skip_load:
        if not args.csv:
            parser.error("--csv is required unless --skip-load is set.")
        load_csv(args.csv)

    if not args.skip_nl:
        setup_nl()
        if not args.skip_load:
            print("[nl] Refreshing value index after data load …")
            refresh_value_index()

    print("\nSetup complete.")


if __name__ == "__main__":
    main()
