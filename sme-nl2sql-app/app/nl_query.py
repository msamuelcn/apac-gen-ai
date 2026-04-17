"""Natural-language to SQL via Vertex AI Gemini, executed against AlloyDB.

Cache layer: similar past questions are resolved in-database using
pgvector + AlloyDB google_ml_integration embedding() instead of calling Gemini.
"""

import logging
import os
import time

import vertexai
from vertexai.generative_models import GenerativeModel
from google.api_core import exceptions as google_exceptions

from app.db import run_sql

logger = logging.getLogger(__name__)

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


def _cache_lookup(question: str) -> tuple[str | None, dict]:
    """Return cached SQL if a semantically similar question already exists.

    Returns:
        (cached_sql, metadata) where metadata contains timing and similarity info.
        cached_sql is None if no hit; metadata holds similarity score.
    """
    start_time = time.time()
    try:
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
        lookup_time_ms = (time.time() - start_time) * 1000

        if rows and rows[0]["similarity"] >= _SIMILARITY_THRESHOLD:
            similarity = rows[0]["similarity"]
            cached_sql = rows[0]["generated_sql"]
            logger.info(
                f"Cache hit (similarity={similarity:.3f}); "
                f"lookup_time={lookup_time_ms:.1f}ms"
            )
            run_sql(
                """
                UPDATE sme_risk.query_cache
                SET    hit_count = hit_count + 1
                WHERE  generated_sql = %(sql)s
                """,
                params={"sql": cached_sql},
                fetch=False,
            )
            return cached_sql, {
                "lookup_time_ms": lookup_time_ms,
                "similarity": similarity,
            }

        logger.info(
            f"Cache miss (best_similarity={rows[0]['similarity']:.3f}); "
            f"lookup_time={lookup_time_ms:.1f}ms"
        )
        return None, {"lookup_time_ms": lookup_time_ms, "similarity": None}
    except Exception as exc:
        lookup_time_ms = (time.time() - start_time) * 1000
        logger.warning(f"Cache lookup failed: {exc}; fallback to Gemini")
        return None, {"lookup_time_ms": lookup_time_ms, "similarity": None}


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


def generate_sql(question: str) -> tuple[str, dict]:
    """Ask Gemini to translate *question* into a SQL string.

    Returns:
        (sql_string, metadata) where metadata contains timing info.

    Raises:
        ValueError: If model returns non-SELECT or invalid response.
        google.api_core.exceptions.*: If Vertex AI API call fails.
    """
    start_time = time.time()
    logger.info("Calling Gemini for SQL generation...")

    try:
        prompt = _PROMPT_TEMPLATE.format(schema=_SCHEMA_CONTEXT, question=question)
        response = _get_model().generate_content(
            prompt,
            generation_config={"timeout": 30},
        )

        sql = response.text.strip().strip(";").strip()
        gemini_time_ms = (time.time() - start_time) * 1000

        if not sql.upper().startswith("SELECT"):
            logger.error(f"Gemini returned non-SELECT: {sql[:120]}")
            raise ValueError(f"Model generated invalid SQL (not SELECT): {sql[:100]}")

        logger.info(f"SQL generated successfully; time={gemini_time_ms:.1f}ms")
        return sql, {"gemini_time_ms": gemini_time_ms}

    except TimeoutError as exc:
        logger.error(f"Gemini timeout after 30s: {exc}")
        raise ValueError(
            "SQL generation timed out; please try a simpler question"
        ) from exc
    except google_exceptions.GoogleAPICallError as exc:
        logger.error(f"Vertex AI API error: {exc}")
        raise ValueError("Failed to generate SQL; please try again") from exc


def ask(question: str) -> dict:
    """Convert *question* to SQL and execute it.

    Checks the semantic cache first; only calls Gemini on a cache miss.

    Args:
        question: Natural language query from user.

    Returns:
        {
            "question": str,
            "generated_sql": str,
            "results": list[dict],
            "cached": bool,
            "execution_time_ms": float,
            "total_time_ms": float
        }

    Raises:
        ValueError: If SQL generation or execution fails.
    """
    start_time = time.time()
    logger.info(f"Processing question: {question[:80]}...")

    cached_sql, cache_meta = _cache_lookup(question)
    if cached_sql:
        exec_start = time.time()
        results = run_sql(cached_sql) or []
        exec_time_ms = (time.time() - exec_start) * 1000
        total_time_ms = (time.time() - start_time) * 1000

        response = {
            "question": question,
            "generated_sql": cached_sql,
            "results": results,
            "cached": True,
            "execution_time_ms": exec_time_ms,
            "total_time_ms": total_time_ms,
        }
        logger.info(
            f"Query completed (cached); result_count={len(results)}; "
            f"total_time={total_time_ms:.1f}ms"
        )
        return response

    sql, gemini_meta = generate_sql(question)

    try:
        _cache_store(question, sql)
    except Exception as exc:
        logger.warning(f"Failed to cache query: {exc}")

    exec_start = time.time()
    try:
        results = run_sql(sql) or []
    except Exception as exc:
        logger.error(f"SQL execution failed: {exc}")
        raise ValueError(f"Query execution failed: {str(exc)[:100]}") from exc

    exec_time_ms = (time.time() - exec_start) * 1000
    total_time_ms = (time.time() - start_time) * 1000

    response = {
        "question": question,
        "generated_sql": sql,
        "results": results,
        "cached": False,
        "execution_time_ms": exec_time_ms,
        "total_time_ms": total_time_ms,
    }
    logger.info(
        f"Query completed (generated); result_count={len(results)}; "
        f"gemini_time={gemini_meta.get('gemini_time_ms', 0):.1f}ms; "
        f"total_time={total_time_ms:.1f}ms"
    )
    return response
