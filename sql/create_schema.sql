-- Dimensional + analytical schema for synthetic credit-risk data.
-- Applied by the pipeline when loading DuckDB.
-- Phase 2: dim_* / fact_* / pipeline_runs.
-- Phase 3: customer_snapshot, portfolio_monthly, executive_metrics.
-- Validation tables arrive in Phase 4.

CREATE TABLE IF NOT EXISTS dim_date (
    date_key INTEGER PRIMARY KEY,          -- YYYYMMDD
    full_date DATE NOT NULL,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,                -- 1–12
    month_name VARCHAR NOT NULL,
    quarter INTEGER NOT NULL,              -- 1–4
    is_month_end BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_customer (
    customer_id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    country VARCHAR NOT NULL,
    region VARCHAR NOT NULL,
    industry VARCHAR NOT NULL,
    annual_revenue DOUBLE,
    account_manager VARCHAR,
    collections_owner VARCHAR,
    status VARCHAR NOT NULL,               -- e.g. active, inactive, watchlist
    credit_insurance_status VARCHAR NOT NULL,  -- insured, uninsured, partial
    credit_limit DOUBLE NOT NULL,
    currency VARCHAR NOT NULL,              -- ISO 4217, e.g. GBP
    business_unit VARCHAR NOT NULL,
    created_date DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_invoice (
    invoice_id VARCHAR PRIMARY KEY,
    customer_id VARCHAR NOT NULL,
    invoice_date DATE NOT NULL,
    due_date DATE NOT NULL,
    invoice_amount DOUBLE NOT NULL,
    outstanding_amount DOUBLE NOT NULL,
    currency VARCHAR NOT NULL,
    dispute_flag BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR NOT NULL,               -- open, overdue, partial, paid, written_off
    FOREIGN KEY (customer_id) REFERENCES dim_customer (customer_id)
);

CREATE TABLE IF NOT EXISTS fact_payment (
    payment_id VARCHAR PRIMARY KEY,
    invoice_id VARCHAR NOT NULL,
    customer_id VARCHAR NOT NULL,
    payment_date DATE NOT NULL,
    payment_amount DOUBLE NOT NULL,
    FOREIGN KEY (invoice_id) REFERENCES fact_invoice (invoice_id),
    FOREIGN KEY (customer_id) REFERENCES dim_customer (customer_id)
);

CREATE TABLE IF NOT EXISTS fact_credit_decision (
    decision_id VARCHAR PRIMARY KEY,
    customer_id VARCHAR NOT NULL,
    decision_date DATE NOT NULL,
    previous_limit DOUBLE NOT NULL,
    new_limit DOUBLE NOT NULL,
    decision_type VARCHAR NOT NULL,        -- increase, decrease, new, review, hold
    decision_reason VARCHAR,
    FOREIGN KEY (customer_id) REFERENCES dim_customer (customer_id)
);

CREATE TABLE IF NOT EXISTS fact_claim (
    claim_id VARCHAR PRIMARY KEY,
    customer_id VARCHAR NOT NULL,
    invoice_id VARCHAR,                    -- optional link when claim is invoice-specific
    claim_date DATE NOT NULL,
    claim_amount DOUBLE NOT NULL,
    status VARCHAR NOT NULL,               -- submitted, approved, rejected, settled
    insurer VARCHAR,
    recovery_amount DOUBLE NOT NULL DEFAULT 0,
    FOREIGN KEY (customer_id) REFERENCES dim_customer (customer_id),
    FOREIGN KEY (invoice_id) REFERENCES fact_invoice (invoice_id)
);

-- Refresh metadata stub; Home reads latest status / finished_at when present.
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id VARCHAR PRIMARY KEY,
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    status VARCHAR NOT NULL,               -- running, success, failed
    random_seed INTEGER,
    customer_count INTEGER,
    notes VARCHAR
);

-- ---------------------------------------------------------------------------
-- Phase 3 analytical tables (point-in-time; no scoring logic in DDL)
-- ---------------------------------------------------------------------------

-- One row per customer per month-end as-of. Features are reconstructed at
-- as_of_date (payments/decisions/claims after as_of are excluded). Risk and
-- collections scores are demonstration-only; populated by pipeline analytics.
CREATE TABLE IF NOT EXISTS customer_snapshot (
    customer_id VARCHAR NOT NULL,
    as_of_date DATE NOT NULL,
    -- Denormalised dimensions (filter / join convenience)
    customer_name VARCHAR NOT NULL,
    country VARCHAR NOT NULL,
    region VARCHAR NOT NULL,
    industry VARCHAR NOT NULL,
    account_manager VARCHAR,
    collections_owner VARCHAR,
    status VARCHAR NOT NULL,
    credit_insurance_status VARCHAR NOT NULL,
    currency VARCHAR NOT NULL,
    business_unit VARCHAR NOT NULL,
    -- Point-in-time exposure
    outstanding_amount DOUBLE NOT NULL,
    overdue_amount DOUBLE NOT NULL,
    credit_limit DOUBLE NOT NULL,
    available_credit DOUBLE NOT NULL,
    utilisation DOUBLE NOT NULL,
    -- Behaviour / ageing
    oldest_days_past_due INTEGER NOT NULL,
    overdue_invoice_count INTEGER NOT NULL,
    dispute_balance DOUBLE NOT NULL,
    avg_days_to_pay DOUBLE,
    pct_invoices_paid_late DOUBLE,
    ageing_bucket VARCHAR NOT NULL,
    -- Demonstration risk score (0–100) + components
    risk_score DOUBLE NOT NULL,
    risk_category VARCHAR NOT NULL,        -- low, medium, high, critical
    risk_comp_ageing DOUBLE NOT NULL,
    risk_comp_utilisation DOUBLE NOT NULL,
    risk_comp_payment DOUBLE NOT NULL,
    risk_comp_overdue_ratio DOUBLE NOT NULL,
    risk_comp_dispute DOUBLE NOT NULL,
    -- Collections priority + components
    collection_priority_score DOUBLE NOT NULL,
    recommended_priority VARCHAR NOT NULL,
    recommended_action VARCHAR NOT NULL,
    coll_comp_risk DOUBLE NOT NULL,
    coll_comp_overdue DOUBLE NOT NULL,
    coll_comp_dpd DOUBLE NOT NULL,
    coll_comp_dispute DOUBLE NOT NULL,
    coll_comp_limit_breach DOUBLE NOT NULL,
    PRIMARY KEY (customer_id, as_of_date),
    FOREIGN KEY (customer_id) REFERENCES dim_customer (customer_id)
);

-- Pre-aggregated portfolio slices for charts (country, industry, etc.).
CREATE TABLE IF NOT EXISTS portfolio_monthly (
    as_of_date DATE NOT NULL,
    slice_type VARCHAR NOT NULL,           -- country, industry, risk_category,
                                           -- ageing_bucket, credit_insurance_status
    slice_value VARCHAR NOT NULL,
    customer_count INTEGER NOT NULL,
    outstanding_amount DOUBLE NOT NULL,
    overdue_amount DOUBLE NOT NULL,
    high_critical_exposure DOUBLE NOT NULL,
    PRIMARY KEY (as_of_date, slice_type, slice_value)
);

-- One row per month-end reporting date. Home reads total_exposure + reporting_date.
CREATE TABLE IF NOT EXISTS executive_metrics (
    reporting_date DATE PRIMARY KEY,
    total_exposure DOUBLE NOT NULL,
    overdue_exposure DOUBLE NOT NULL,
    pct_overdue DOUBLE NOT NULL,
    credit_limit_utilisation DOUBLE NOT NULL,
    claims_submitted DOUBLE NOT NULL,
    recoveries DOUBLE NOT NULL,
    customers_exceeding_limits INTEGER NOT NULL,
    mom_exposure_change DOUBLE,            -- null on first month-end
    mom_overdue_change DOUBLE,             -- null on first month-end
    high_critical_exposure DOUBLE NOT NULL,
    customer_count INTEGER NOT NULL,
    invoice_count INTEGER NOT NULL
);
