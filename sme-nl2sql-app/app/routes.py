"""Flask blueprints – all HTTP endpoints live here."""

from flask import Blueprint, jsonify, request
from app.nl_query import ask
from app.db import run_sql

bp = Blueprint("api", __name__, url_prefix="/api")


@bp.get("/health")
def health():
    """Liveness probe for Cloud Run."""
    return jsonify({"status": "ok"})


@bp.get("/readiness")
def readiness():
    """Readiness probe – verifies DB connectivity."""
    try:
        run_sql("SELECT 1;")
        return jsonify({"status": "ready"})
    except Exception as exc:
        return jsonify({"status": "unavailable", "detail": str(exc)}), 503


@bp.post("/ask")
def ask_endpoint():
    """
    Accept a natural-language question and return:
        - the question
        - the AlloyDB-generated SQL
        - the query result rows

    Request body (JSON):
        { "question": "Which sectors have the highest distress rate?" }

    Response (JSON):
        {
            "question":      "...",
            "generated_sql": "SELECT ...",
            "results":       [ {...}, ... ]
        }
    """
    body = request.get_json(silent=True) or {}
    question = (body.get("question") or "").strip()
    if not question:
        return jsonify({"error": "Field 'question' is required."}), 400

    try:
        result = ask(question)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 422
    except Exception as exc:
        return jsonify({"error": "Query execution failed.", "detail": str(exc)}), 500


@bp.get("/distress/summary")
def distress_summary():
    """Pre-built summary: distress counts by label (for presentation demo)."""
    rows = run_sql(
        """
        SELECT distress_label, COUNT(*) AS n
        FROM   sme_risk.sme_financial
        GROUP  BY distress_label
        ORDER  BY distress_label;
        """
    )
    return jsonify(rows or [])


@bp.get("/distress/by-segment")
def distress_by_segment():
    """Pre-built view query: distress rate by sector, size, and revenue band."""
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
    return jsonify(rows or [])
