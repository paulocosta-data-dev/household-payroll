CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS mart;

CREATE TABLE IF NOT EXISTS raw.ingestion_run (
    run_id VARCHAR PRIMARY KEY,
    source_name VARCHAR NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    status VARCHAR NOT NULL
        CHECK (status IN ('running', 'succeeded', 'failed')),
    row_count INTEGER NOT NULL DEFAULT 0,
    error_message VARCHAR
);

CREATE TABLE IF NOT EXISTS raw.form_submission (
    source_record_key VARCHAR PRIMARY KEY,
    author_id VARCHAR NOT NULL,
    submitted_at_text VARCHAR NOT NULL,
    work_date_text VARCHAR NOT NULL,
    start_time_text VARCHAR NOT NULL,
    end_time_text VARCHAR NOT NULL,
    break_minutes_text VARCHAR NOT NULL,
    notes VARCHAR,
    content_hash VARCHAR NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,
    ingestion_run_id VARCHAR NOT NULL
        REFERENCES raw.ingestion_run(run_id)
);

CREATE TABLE IF NOT EXISTS core.work_submission (
    submission_id VARCHAR PRIMARY KEY,
    source_record_key VARCHAR NOT NULL UNIQUE,
    author_id VARCHAR NOT NULL
        CHECK (author_id IN ('employer', 'worker')),
    submitted_at TIMESTAMPTZ NOT NULL,
    work_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    break_minutes INTEGER NOT NULL
        CHECK (break_minutes >= 0),
    worked_minutes INTEGER NOT NULL
        CHECK (worked_minutes >= 0),
    notes VARCHAR,
    ingested_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS core.rate_version (
    rate_id VARCHAR PRIMARY KEY,
    valid_from DATE NOT NULL,
    valid_to DATE,
    hourly_rate_cents INTEGER NOT NULL
        CHECK (hourly_rate_cents > 0),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE TABLE IF NOT EXISTS core.work_approval (
    approval_id VARCHAR PRIMARY KEY,
    work_date DATE NOT NULL,
    approved_start_time TIME NOT NULL,
    approved_end_time TIME NOT NULL,
    approved_break_minutes INTEGER NOT NULL
        CHECK (approved_break_minutes >= 0),
    approved_minutes INTEGER NOT NULL
        CHECK (approved_minutes >= 0),
    status VARCHAR NOT NULL
        CHECK (status IN ('approved', 'rejected', 'superseded')),
    decided_at TIMESTAMPTZ NOT NULL,
    reason VARCHAR NOT NULL,
    supersedes_approval_id VARCHAR
        REFERENCES core.work_approval(approval_id)
);

CREATE TABLE IF NOT EXISTS core.reconciliation (
    work_date DATE PRIMARY KEY,
    employer_submission_id VARCHAR,
    worker_submission_id VARCHAR,
    status VARCHAR NOT NULL
        CHECK (status IN (
            'employer_only',
            'worker_only',
            'matched',
            'divergent'
        )),
    start_time_matches BOOLEAN,
    end_time_matches BOOLEAN,
    break_matches BOOLEAN,
    duration_matches BOOLEAN
);

CREATE TABLE IF NOT EXISTS mart.payment_line (
    payment_line_id VARCHAR PRIMARY KEY,
    work_date DATE NOT NULL,
    approval_id VARCHAR NOT NULL,
    rate_id VARCHAR NOT NULL,
    approved_minutes INTEGER NOT NULL,
    hourly_rate_cents INTEGER NOT NULL,
    gross_amount_cents INTEGER NOT NULL,
    calculation_rule_version VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS mart.payment_summary (
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    approved_visits INTEGER NOT NULL,
    approved_minutes INTEGER NOT NULL,
    gross_amount_cents INTEGER NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (period_start, period_end)
);
