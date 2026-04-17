"""Flask blueprints – all HTTP endpoints live here."""

import json
import logging
from flask import Blueprint, jsonify, render_template, request
from app.nl_query import ask
from app.db import run_sql

logger = logging.getLogger(__name__)

ui = Blueprint("ui", __name__)
bp = Blueprint("api", __name__, url_prefix="/api")

# Configuration
MAX_QUESTION_LENGTH = 1000


def _error_response(
    error: str, code: str = "UNKNOWN_ERROR", details: str = "", status_code: int = 500
):
    """Standardize error response format."""
    return (
        jsonify(
            {
                "error": error,
                "code": code,
                "details": details,
            }
        ),
        status_code,
    )


@ui.get("/")
def index():
    """Serve the single-page analytics dashboard."""
    return render_template("index.html")


@bp.get("/health")
def health():
    """Liveness probe for Cloud Run."""
    return jsonify({"status": "ok"})


@bp.get("/readiness")
def readiness():
    """Readiness probe – verifies DB connectivity and schema readiness.

    Returns 200 if ready, 503 if not ready.
    """
    try:
        # Quick connectivity check
        run_sql("SELECT 1;")

        # Verify schema exists
        run_sql(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='sme_risk' AND table_name='sme_financial' LIMIT 1;"
        )

        logger.info("Readiness check passed")
        return jsonify({"status": "ready"}), 200
    except Exception as exc:
        logger.error(f"Readiness check failed: {exc}")
        return jsonify({"status": "unavailable", "detail": str(exc)[:200]}), 503


@bp.post("/ask")
def ask_endpoint():
    """Accept a natural-language question and return SQL + results.

    Request body (JSON):
        { "question": "Which sectors have the highest distress rate?" }

    Response (JSON):
        {
            "question": str,
            "generated_sql": str,
            "results": [dict, ...],
            "cached": bool,
            "execution_time_ms": float,
            "total_time_ms": float
        }

    Error response:
        {
            "error": "Human-readable error message",
            "code": "ERROR_CODE",
            "details": "Technical details (optional)"
        }
    """
    # Validate request content type
    if not request.is_json and request.method == "POST":
        return _error_response(
            "Content-Type must be application/json", "INVALID_CONTENT_TYPE", "", 400
        )

    # Parse JSON body
    try:
        body = request.get_json(silent=True) or {}
    except Exception as exc:
        logger.warning(f"Failed to parse JSON: {exc}")
        return _error_response(
            "Invalid JSON in request body", "INVALID_JSON", str(exc), 400
        )

    # Validate and extract question
    question = (body.get("question") or "").strip()

    if not question:
        return _error_response(
            "Field 'question' is required",
            "MISSING_QUESTION",
            "Provide a non-empty question field",
            400,
        )

    if len(question) > MAX_QUESTION_LENGTH:
        return _error_response(
            f"Question exceeds max length of {MAX_QUESTION_LENGTH} characters",
            "QUESTION_TOO_LONG",
            f"Current length: {len(question)}",
            400,
        )

    try:
        logger.info(f"Processing question: {question[:100]}...")
        result = ask(question)
        logger.info(f"Successfully processed question")
        return jsonify(result), 200

    except ValueError as exc:
        error_msg = str(exc)
        logger.error(f"Query validation error: {error_msg}")
        return _error_response(error_msg, "QUERY_ERROR", "", 422)
    except Exception as exc:
        error_msg = str(exc)
        logger.error(f"Unexpected error: {error_msg}", exc_info=True)
        return _error_response(
            "Request processing failed", "INTERNAL_ERROR", error_msg[:200], 500
        )


@bp.get("/distress/summary")
def distress_summary():
    """Return summary stats: distress counts by label (Stable vs Distressed).

    Response:
        [ { "distress_label": str, "n": int }, ... ]
    """
    try:
        rows = run_sql(
            """
            SELECT distress_label, COUNT(*) AS n
            FROM   sme_risk.sme_financial
            GROUP  BY distress_label
            ORDER  BY distress_label;
            """
        )
        logger.info(f"Distress summary returned {len(rows or [])} rows")
        return jsonify(rows or []), 200
    except Exception as exc:
        logger.error(f"Distress summary endpoint failed: {exc}", exc_info=True)
        return _error_response(
            "Failed to retrieve distress summary", "QUERY_ERROR", str(exc)[:200], 500
        )


@bp.get("/distress/by-segment")
def distress_by_segment():
    """Return distress rate by sector, size, and revenue band (top 50).

    Response:
        [
            {
                "industry_sector": int,
                "sme_size_category": int,
                "annual_revenue_category": str,
                "total_smes": int,
                "distress_rate": float
            },
            ...
        ]
    """
    try:
        rows = run_sql(
            """
            SELECT industry_sector,
                   sme_size_category,
                   annual_revenue_category,
                   total_smes,
                   ROUND(distress_rate::numeric, 4) AS distress_rate
            FROM   sme_risk.vw_distress_rate_by_segment
            ORDER  BY distress_rate DESC
            LIMIT  50;
            """
        )
        logger.info(f"Distress by-segment returned {len(rows or [])} rows")
        return jsonify(rows or []), 200
    except Exception as exc:
        logger.error(f"Distress by-segment endpoint failed: {exc}", exc_info=True)
        return _error_response(
            "Failed to retrieve distress-rate segments",
            "QUERY_ERROR",
            str(exc)[:200],
            500,
        )


@bp.get("/cache/stats")
def cache_stats():
    """Return semantic query cache statistics for observability.

    Response:
        {
            "total_cached_queries": int,
            "total_hits": int,
            "avg_hits_per_query": float,
            "top_10_cached_questions": [{"question": str, "hit_count": int}, ...]
        }

    Note: Questions are truncated to first 100 chars for privacy.
    """
    try:
        # Summary stats
        summary = run_sql(
            """
            SELECT COUNT(*) AS total_cached_queries,
                   SUM(hit_count) AS total_hits,
                   AVG(hit_count) AS avg_hits_per_query
            FROM   sme_risk.query_cache;
            """
        )

        # Top cached questions
        top_queries = run_sql(
            """
            SELECT SUBSTRING(question, 1, 100) AS question,
                   hit_count
            FROM   sme_risk.query_cache
            ORDER  BY hit_count DESC
            LIMIT  10;
            """
        )

        result = {
            "total_cached_queries": summary[0]["total_cached_queries"] or 0,
            "total_hits": summary[0]["total_hits"] or 0,
            "avg_hits_per_query": float(summary[0]["avg_hits_per_query"] or 0),
            "top_10_cached_questions": top_queries or [],
        }

        logger.info(
            f"Cache stats retrieved; total_queries={result['total_cached_queries']}"
        )
        return jsonify(result), 200

    except Exception as exc:
        logger.error(f"Cache stats endpoint failed: {exc}", exc_info=True)
        return _error_response(
            "Failed to retrieve cache statistics", "QUERY_ERROR", str(exc)[:200], 500
        )
