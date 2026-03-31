"""
One-time AlloyDB AI natural language setup helpers.

These are called by scripts/setup_schema.py after data is loaded.
They are idempotent where possible (IF NOT EXISTS equivalents via try/except).
"""

from app.db import run_sql


def enable_extension() -> None:
    run_sql("CREATE EXTENSION IF NOT EXISTS google_ml_integration CASCADE;", fetch=False)
    run_sql("CREATE EXTENSION IF NOT EXISTS alloydb_ai_nl CASCADE;", fetch=False)


def create_nl_config(config_id: str = "sme_finance_cfg") -> None:
    try:
        run_sql(
            "SELECT alloydb_ai_nl.g_create_configuration(%(cid)s);",
            params={"cid": config_id},
            fetch=False,
        )
    except Exception:
        # Configuration already exists – safe to continue.
        pass

    run_sql(
        """
        SELECT alloydb_ai_nl.g_manage_configuration(
            operation            => 'register_schema',
            configuration_id_in  => %(cid)s,
            schema_names_in      => '{sme_risk}'
        );
        """,
        params={"cid": config_id},
        fetch=False,
    )


def add_domain_context(config_id: str = "sme_finance_cfg") -> None:
    contexts = [
        "In this dataset financial_distress is binary: 0 = Stable, 1 = Distressed.",
        "uses_digital_finance: 0 = does not use digital finance, 1 = uses digital finance.",
        "annual_revenue_category values are Low, Medium, High.",
        "liquidity_stability is a numeric score; higher scores indicate more stable liquidity.",
    ]
    for ctx in contexts:
        run_sql(
            """
            SELECT alloydb_ai_nl.g_manage_configuration(
                'add_general_context',
                %(cid)s,
                general_context_in => %(ctx)s
            );
            """,
            params={"cid": config_id, "ctx": f'{{{ctx}}}'},
            fetch=False,
        )


def apply_schema_context(config_id: str = "sme_finance_cfg") -> None:
    run_sql(
        "SELECT alloydb_ai_nl.generate_schema_context(%(cid)s);",
        params={"cid": config_id},
        fetch=False,
    )
    run_sql(
        "SELECT alloydb_ai_nl.apply_generated_schema_context(%(cid)s, TRUE);",
        params={"cid": config_id},
        fetch=False,
    )


def add_templates(config_id: str = "sme_finance_cfg") -> None:
    templates = [
        (
            "What is the distress rate by industry sector?",
            """
            SELECT industry_sector,
                   AVG(financial_distress::numeric) AS distress_rate,
                   COUNT(*)                          AS total_smes
            FROM   sme_risk.sme_financial
            GROUP  BY industry_sector
            ORDER  BY distress_rate DESC
            """,
        ),
        (
            "Compare distress rate for SMEs that use digital finance versus those that do not.",
            """
            SELECT uses_digital_finance,
                   AVG(financial_distress::numeric) AS distress_rate,
                   COUNT(*)                          AS total_smes
            FROM   sme_risk.sme_financial
            GROUP  BY uses_digital_finance
            ORDER  BY uses_digital_finance
            """,
        ),
        (
            "Which annual revenue category has the highest number of distressed SMEs?",
            """
            SELECT annual_revenue_category,
                   COUNT(*) FILTER (WHERE financial_distress = 1) AS distressed_count,
                   COUNT(*)                                        AS total_smes
            FROM   sme_risk.sme_financial
            GROUP  BY annual_revenue_category
            ORDER  BY distressed_count DESC
            """,
        ),
        (
            "What is the average liquidity stability score for distressed versus stable SMEs?",
            """
            SELECT distress_label,
                   AVG(liquidity_stability) AS avg_liquidity_stability,
                   COUNT(*)                 AS total_smes
            FROM   sme_risk.sme_financial
            GROUP  BY distress_label
            ORDER  BY distress_label
            """,
        ),
        (
            "Show distress rate grouped by SME size category and annual revenue category.",
            """
            SELECT sme_size_category,
                   annual_revenue_category,
                   AVG(financial_distress::numeric) AS distress_rate,
                   COUNT(*)                          AS total_smes
            FROM   sme_risk.sme_financial
            GROUP  BY sme_size_category, annual_revenue_category
            ORDER  BY distress_rate DESC
            """,
        ),
    ]
    for intent, sql in templates:
        run_sql(
            """
            SELECT alloydb_ai_nl.add_template(
                nl_config_id => %(cid)s,
                intent       => %(intent)s,
                sql          => %(sql)s,
                check_intent => TRUE
            );
            """,
            params={"cid": config_id, "intent": intent, "sql": sql},
            fetch=False,
        )


def create_value_index(config_id: str = "sme_finance_cfg") -> None:
    for col in (
        "sme_risk.sme_financial.annual_revenue_category",
        "sme_risk.sme_financial.distress_label",
    ):
        run_sql(
            """
            SELECT alloydb_ai_nl.associate_concept_type(
                column_names_in => %(col)s,
                concept_type_in => 'generic_entity_name',
                nl_config_id_in => %(cid)s
            );
            """,
            params={"col": col, "cid": config_id},
            fetch=False,
        )
    run_sql(
        "SELECT alloydb_ai_nl.create_value_index(nl_config_id_in => %(cid)s);",
        params={"cid": config_id},
        fetch=False,
    )


def refresh_value_index(config_id: str = "sme_finance_cfg") -> None:
    run_sql(
        "SELECT alloydb_ai_nl.refresh_value_index(nl_config_id_in => %(cid)s);",
        params={"cid": config_id},
        fetch=False,
    )
