-- Phase 2 dimensional schema for synthetic credit-risk data.
-- Applied by the pipeline when loading DuckDB (step 11).
-- Analytical tables (risk scores, snapshots, validation) arrive in later phases.

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
