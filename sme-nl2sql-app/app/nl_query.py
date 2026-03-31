"""Natural-language to SQL execution layer."""

from app.db import run_sql

NL_CONFIG = "sme_finance_cfg"


def generate_sql(question: str) -> str:
    """Ask AlloyDB AI NL to translate *question* into a SQL string."""
    rows = run_sql(
        """
        SELECT alloydb_ai_nl.get_sql(
            nl_config_id => %(cfg)s,
            nl_question  => %(q)s
        ) ->> 'sql' AS generated_sql;
        """,
        params={"cfg": NL_CONFIG, "q": question},
    )
    if not rows or not rows[0].get("generated_sql"):
        raise ValueError("AlloyDB AI NL returned no SQL for the provided question.")
    return rows[0]["generated_sql"]


def ask(question: str) -> dict:
    """
    Convert *question* to SQL, execute it, and return a dict with:
        {
            "question":      str,
            "generated_sql": str,
            "results":       list[dict],
        }
    Raises ValueError if NL generation fails.
    Raises psycopg.Error if generated SQL is invalid.
    """
    sql = generate_sql(question)
    results = run_sql(sql) or []
    return {
        "question": question,
        "generated_sql": sql,
        "results": results,
    }
