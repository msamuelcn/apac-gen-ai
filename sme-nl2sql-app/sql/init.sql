-- =============================================================================
-- SME Financial Distress NL2SQL – AlloyDB initialisation script
-- Run once against your AlloyDB database (sme_demo).
-- Order matters: schema → table → indexes → view → extensions → NL config.
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
-- 5. AlloyDB AI extensions
--    Requires: alloydb_ai_nl.enabled flag set on the instance beforehand.
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS google_ml_integration CASCADE;
CREATE EXTENSION IF NOT EXISTS alloydb_ai_nl        CASCADE;

-- ---------------------------------------------------------------------------
-- 6. Natural-language configuration
-- ---------------------------------------------------------------------------
SELECT alloydb_ai_nl.g_create_configuration('sme_finance_cfg');

SELECT alloydb_ai_nl.g_manage_configuration(
    operation            => 'register_schema',
    configuration_id_in  => 'sme_finance_cfg',
    schema_names_in      => '{sme_risk}'
);

-- ---------------------------------------------------------------------------
-- 7. Domain context (business rules for the LLM)
-- ---------------------------------------------------------------------------
SELECT alloydb_ai_nl.g_manage_configuration(
    'add_general_context',
    'sme_finance_cfg',
    general_context_in => '{"In this dataset financial_distress is binary: 0 = Stable, 1 = Distressed."}'
);

SELECT alloydb_ai_nl.g_manage_configuration(
    'add_general_context',
    'sme_finance_cfg',
    general_context_in => '{"uses_digital_finance: 0 = does not use digital finance, 1 = uses digital finance."}'
);

SELECT alloydb_ai_nl.g_manage_configuration(
    'add_general_context',
    'sme_finance_cfg',
    general_context_in => '{"annual_revenue_category values are Low, Medium, High."}'
);

SELECT alloydb_ai_nl.g_manage_configuration(
    'add_general_context',
    'sme_finance_cfg',
    general_context_in => '{"liquidity_stability is a numeric score; higher scores indicate more stable liquidity."}'
);

-- ---------------------------------------------------------------------------
-- 8. Schema context (run AFTER data is loaded for representative results)
-- ---------------------------------------------------------------------------
SELECT alloydb_ai_nl.generate_schema_context('sme_finance_cfg');
SELECT alloydb_ai_nl.apply_generated_schema_context('sme_finance_cfg', TRUE);

-- ---------------------------------------------------------------------------
-- 9. Query templates
-- ---------------------------------------------------------------------------
SELECT alloydb_ai_nl.add_template(
    nl_config_id => 'sme_finance_cfg',
    intent       => 'What is the distress rate by industry sector?',
    sql          => $$
        SELECT industry_sector,
               AVG(financial_distress::numeric) AS distress_rate,
               COUNT(*)                          AS total_smes
        FROM   sme_risk.sme_financial
        GROUP  BY industry_sector
        ORDER  BY distress_rate DESC
    $$,
    check_intent => TRUE
);

SELECT alloydb_ai_nl.add_template(
    nl_config_id => 'sme_finance_cfg',
    intent       => 'Compare distress rate for SMEs that use digital finance versus those that do not.',
    sql          => $$
        SELECT uses_digital_finance,
               AVG(financial_distress::numeric) AS distress_rate,
               COUNT(*)                          AS total_smes
        FROM   sme_risk.sme_financial
        GROUP  BY uses_digital_finance
        ORDER  BY uses_digital_finance
    $$,
    check_intent => TRUE
);

SELECT alloydb_ai_nl.add_template(
    nl_config_id => 'sme_finance_cfg',
    intent       => 'Which annual revenue category has the highest number of distressed SMEs?',
    sql          => $$
        SELECT annual_revenue_category,
               COUNT(*) FILTER (WHERE financial_distress = 1) AS distressed_count,
               COUNT(*)                                        AS total_smes
        FROM   sme_risk.sme_financial
        GROUP  BY annual_revenue_category
        ORDER  BY distressed_count DESC
    $$,
    check_intent => TRUE
);

SELECT alloydb_ai_nl.add_template(
    nl_config_id => 'sme_finance_cfg',
    intent       => 'What is the average liquidity stability score for distressed versus stable SMEs?',
    sql          => $$
        SELECT distress_label,
               AVG(liquidity_stability) AS avg_liquidity_stability,
               COUNT(*)                 AS total_smes
        FROM   sme_risk.sme_financial
        GROUP  BY distress_label
        ORDER  BY distress_label
    $$,
    check_intent => TRUE
);

SELECT alloydb_ai_nl.add_template(
    nl_config_id => 'sme_finance_cfg',
    intent       => 'Show distress rate grouped by SME size category and annual revenue category.',
    sql          => $$
        SELECT sme_size_category,
               annual_revenue_category,
               AVG(financial_distress::numeric) AS distress_rate,
               COUNT(*)                          AS total_smes
        FROM   sme_risk.sme_financial
        GROUP  BY sme_size_category, annual_revenue_category
        ORDER  BY distress_rate DESC
    $$,
    check_intent => TRUE
);

-- ---------------------------------------------------------------------------
-- 10. Concept types and value index
-- ---------------------------------------------------------------------------
SELECT alloydb_ai_nl.associate_concept_type(
    column_names_in => 'sme_risk.sme_financial.annual_revenue_category',
    concept_type_in => 'generic_entity_name',
    nl_config_id_in => 'sme_finance_cfg'
);

SELECT alloydb_ai_nl.associate_concept_type(
    column_names_in => 'sme_risk.sme_financial.distress_label',
    concept_type_in => 'generic_entity_name',
    nl_config_id_in => 'sme_finance_cfg'
);

SELECT alloydb_ai_nl.create_value_index(nl_config_id_in => 'sme_finance_cfg');

-- Done.
-- Next step: load data via scripts/setup_schema.py then refresh the value index:
--   SELECT alloydb_ai_nl.refresh_value_index(nl_config_id_in => 'sme_finance_cfg');
