"""Natural-language to SQL via Vertex AI Gemini, executed against AlloyDB."""

import os

import vertexai
from vertexai.generative_models import GenerativeModel

from app.db import run_sql

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
    Convert *question* to SQL via Gemini, execute it on AlloyDB, and return:
        { "question": str, "generated_sql": str, "results": list[dict] }
    """
    sql = generate_sql(question)
    results = run_sql(sql) or []
    return {"question": question, "generated_sql": sql, "results": results}
