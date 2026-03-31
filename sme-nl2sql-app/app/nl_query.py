"""Natural-language to SQL via Vertex AI Gemini, executed against AlloyDB.

Cache layer: similar past questions are resolved in-database using
pgvector + AlloyDB google_ml_integration embedding() instead of calling Gemini.
"""

import os

import vertexai
from vertexai.generative_models import GenerativeModel

from app.db import run_sql

_SIMILARITY_THRESHOLD = float(os.environ.get("CACHE_SIMILARITY_THRESHOLD", "0.88"))
_EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-005")

_SCHEMA_CONTEXT = """
Table: sme_risk.sme_financial
  industry_sector (int), sme_size_category (int), sme_age (int), sme_type (int),
  annual_revenue_category (text: Low / Medium / High),
  financial_distress (int: 0 = Stable, 1 = Distressed),
  distress_label (text generated: Stable / Distressed),
  uses_digital_finance (int: 0 = no, 1 = yes),
  liquidity_stability (numeric, higher = more stable),
  literacy_accounting, literacy_budgeting, literacy_investment_evaluation,
  literacy_credit_knowledge, risk_awareness, risk_evaluation,
  risk_mitigation_strategies, risk_taking_willingness,
  assessment_data_driven, assessment_expert_consultation,
  assessment_scenario_analysis, assessment_internal_evaluation,
  decision_autonomy, decision_consultation, decision_financial_advisor,
  decision_strategic_alignment, decision_investment_choices,
  decision_loan_approval, decision_capital_allocation,
  decision_cashflow_management, analysis_accounting_tools,
  analysis_financial_ratios, analysis_forecasting, analysis_benchmarking
  (all numeric)

View: sme_risk.vw_distress_rate_by_segment
  industry_sector, sme_size_category, annual_revenue_category,
  total_smes (bigint), distress_rate (numeric)
"""

_PROMPT_TEMPLATE = """\
You are a PostgreSQL expert. Given the schema below, write a single valid \
SELECT query that answers the user's question.

Rules:
- Output ONLY the SQL statement, no explanation, no markdown, no code fences.
- Use fully qualified table names (sme_risk.sme_financial).
- Do not use LIMIT unless the question asks for top-N results.

Schema:
{schema}

Question: {question}
"""


def _cache_lookup(question: str) -> str | None:
    """Return cached SQL if a semantically similar question already exists."""
    rows = run_sql(
        """
        SELECT generated_sql,
               1 - (question_embedding <=> embedding(%(model)s, %(q)s)::vector)
                   AS similarity
        FROM   sme_risk.query_cache
        WHERE  question_embedding IS NOT NULL
        ORDER  BY question_embedding <=> embedding(%(model)s, %(q)s)::vector
        LIMIT  1
        """,
        params={"model": _EMBEDDING_MODEL, "q": question},
    )
    if rows and rows[0]["similarity"] >= _SIMILARITY_THRESHOLD:
        run_sql(
            """
            UPDATE sme_risk.query_cache
            SET    hit_count = hit_count + 1
            WHERE  generated_sql = %(sql)s
            """,
            params={"sql": rows[0]["generated_sql"]},
            fetch=False,
        )
        return rows[0]["generated_sql"]
    return None


def _cache_store(question: str, sql: str) -> None:
    """Persist a new question/SQL pair with its pgvector embedding."""
    run_sql(
        """
        INSERT INTO sme_risk.query_cache (question, question_embedding, generated_sql)
        VALUES (%(q)s, embedding(%(model)s, %(q)s)::vector, %(sql)s)
        """,
        params={"model": _EMBEDDING_MODEL, "q": question, "sql": sql},
        fetch=False,
    )


def _get_model() -> GenerativeModel:
    vertexai.init(
        project=os.environ["GCP_PROJECT"],
        location=os.environ.get("GCP_REGION", "us-central1"),
    )
    return GenerativeModel(os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"))


def generate_sql(question: str) -> str:
    """Ask Gemini to translate *question* into a SQL string."""
    prompt = _PROMPT_TEMPLATE.format(schema=_SCHEMA_CONTEXT, question=question)
    response = _get_model().generate_content(prompt)
    sql = response.text.strip().strip(";").strip()
    if not sql.upper().startswith("SELECT"):
        raise ValueError(f"Model returned non-SELECT output: {sql[:120]}")
    return sql


def ask(question: str) -> dict:
    """
    Convert *question* to SQL and execute it.  Checks the semantic cache first;
    only calls Gemini on a cache miss.  Returns:
        { "question": str, "generated_sql": str, "results": list[dict], "cached": bool }
    """
    cached_sql = _cache_lookup(question)
    if cached_sql:
        results = run_sql(cached_sql) or []
        return {
            "question": question,
            "generated_sql": cached_sql,
            "results": results,
            "cached": True,
        }

    sql = generate_sql(question)
    _cache_store(question, sql)
    results = run_sql(sql) or []
    return {
        "question": question,
        "generated_sql": sql,
        "results": results,
        "cached": False,
    }
