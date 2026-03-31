-- =============================================================================
-- SME Financial Distress – AlloyDB initialisation script
-- Run once against your AlloyDB database (sme_demo).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Schema
-- ---------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS sme_risk;

-- ---------------------------------------------------------------------------
-- 2. Base table  (distress_label is a GENERATED column – rubric item #2)
-- ---------------------------------------------------------------------------
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
    -- Custom derived column (custom schema modification for the assignment).
    distress_label text GENERATED ALWAYS AS (
        CASE WHEN financial_distress = 1 THEN 'Distressed' ELSE 'Stable' END
    ) STORED
);

-- ---------------------------------------------------------------------------
-- 3. Indexes on common filter / group-by columns
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_sme_sector
    ON sme_risk.sme_financial (industry_sector);

CREATE INDEX IF NOT EXISTS idx_sme_revenue
    ON sme_risk.sme_financial (annual_revenue_category);

CREATE INDEX IF NOT EXISTS idx_sme_digital_finance
    ON sme_risk.sme_financial (uses_digital_finance);

CREATE INDEX IF NOT EXISTS idx_sme_distress
    ON sme_risk.sme_financial (financial_distress);

-- ---------------------------------------------------------------------------
-- 4. Analytical view (custom schema object)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW sme_risk.vw_distress_rate_by_segment AS
SELECT
    industry_sector,
    sme_size_category,
    annual_revenue_category,
    COUNT(*)                        AS total_smes,
    AVG(financial_distress::numeric) AS distress_rate
FROM sme_risk.sme_financial
GROUP BY industry_sector, sme_size_category, annual_revenue_category;

-- ---------------------------------------------------------------------------
-- 5. ML extensions  (AlloyDB google_ml_integration + pgvector)
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS google_ml_integration CASCADE;
CREATE EXTENSION IF NOT EXISTS vector;

GRANT EXECUTE ON FUNCTION embedding TO postgres;

-- Register the text-embedding model once (fill in YOUR_PROJECT_ID):
CALL google_ml.create_model(
   model_id => 'gemini-3-flash-preview',
   model_request_url => 'https://aiplatform.googleapis.com/v1/projects/<<YOUR_PROJECT_ID>>/locations/global/publishers/google/models/gemini-3-flash-preview:generateContent',
   model_qualified_name => 'gemini-3-flash-preview',
   model_provider => 'google',
   model_type => 'llm',
   model_auth_type => 'alloydb_service_agent_iam'
);
--replace <<YOUR_PROJECT_ID>> with your project id.

-- ---------------------------------------------------------------------------
-- 6. Semantic query cache
--    Stores past NL questions with their pgvector embedding so future
--    similar questions can be served from cache instead of Gemini.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sme_risk.query_cache (
    id                 bigserial    PRIMARY KEY,
    question           text         NOT NULL,
    question_embedding vector(768),
    generated_sql      text         NOT NULL,
    hit_count          int          DEFAULT 1,
    created_at         timestamptz  DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cache_embedding
    ON sme_risk.query_cache
    USING ivfflat (question_embedding vector_cosine_ops)
    WITH (lists = 10);

-- Done.
-- Next step: load data via:  python scripts/setup_schema.py --csv /path/to/file.csv
