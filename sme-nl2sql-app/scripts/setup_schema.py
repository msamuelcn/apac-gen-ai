"""
One-off setup script: create schema objects and load CSV data into AlloyDB.

Run this once from Cloud Shell (or locally via the AlloyDB Auth Proxy):

    python scripts/setup_schema.py --csv /path/to/financial_dataset_SME.csv

Flags:
    --csv PATH     Path to the SME CSV file to load.
    --skip-load    Skip CSV loading (DDL only).
    --check-only   Validate env + DB connection, then exit.
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

_REQUIRED_ENV = [
    "ALLOYDB_HOST",
    "ALLOYDB_PORT",
    "ALLOYDB_DB",
    "ALLOYDB_USER",
    "ALLOYDB_PASSWORD",
    "ALLOYDB_SSLMODE",
]

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


def validate_env() -> None:
    missing = [key for key in _REQUIRED_ENV if not os.getenv(key)]
    if not missing:
        return

    print("Error: Missing required environment variables:")
    for key in missing:
        print(f"  - {key}")
    print(
        "\nSet them first (or source your .env) and retry.\n"
        "Required: ALLOYDB_HOST, ALLOYDB_PORT, ALLOYDB_DB, "
        "ALLOYDB_USER, ALLOYDB_PASSWORD, ALLOYDB_SSLMODE"
    )
    sys.exit(1)


def check_connection() -> None:
    host = os.getenv("ALLOYDB_HOST")
    port = os.getenv("ALLOYDB_PORT")
    db = os.getenv("ALLOYDB_DB")
    user = os.getenv("ALLOYDB_USER")
    sslmode = os.getenv("ALLOYDB_SSLMODE")
    print(
        f"[check] Connecting to {host}:{port} db={db} user={user} sslmode={sslmode} ..."
    )
    rows = run_sql("SELECT version() AS v;")
    print("[check] Connection successful.")
    print(f"[check] Database Version: {rows[0]['v']}")


def load_csv(csv_path: str) -> None:
    print(f"[load] Reading {csv_path} ...")
    df_raw = pd.read_csv(csv_path)
    df = df_raw.rename(columns={c: _normalize_col(c) for c in df_raw.columns})
    for col in INT_COLS:
        if col in df.columns:
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
    print("[schema] Applying DDL ...")
    run_sql(_DDL, fetch=False)
    print("[schema] Done.")


def main() -> None:
    parser = argparse.ArgumentParser(description="AlloyDB SME demo setup")
    parser.add_argument("--csv", metavar="PATH", help="Path to SME CSV file")
    parser.add_argument("--skip-load", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    try:
        validate_env()
        check_connection()

        if args.check_only:
            print("\nCheck complete. Exiting due to --check-only.")
            return

        setup_schema()

        if not args.skip_load:
            if not args.csv:
                parser.error("--csv is required unless --skip-load is set.")
            load_csv(args.csv)

        print("\nSetup complete.")
    except Exception as exc:
        if "couldn't get a connection" in str(exc).lower():
            print(
                "Connection timeout: could not get a DB connection in 30s.\n"
                "Check host/port reachability, AlloyDB Auth Proxy usage, and credentials."
            )
            sys.exit(1)
        print(f"Unexpected error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
