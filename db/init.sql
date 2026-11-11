-- gostrag initial schema
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS users (
    user_id      BIGINT PRIMARY KEY,
    username     TEXT,
    role         TEXT NOT NULL DEFAULT 'expert',
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS usage_daily (
    user_id      BIGINT NOT NULL REFERENCES users(user_id),
    day          DATE NOT NULL,
    questions    INTEGER NOT NULL DEFAULT 0,
    tokens_in    BIGINT NOT NULL DEFAULT 0,
    tokens_out   BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day)
);

CREATE TABLE IF NOT EXISTS qa_log (
    id           BIGSERIAL PRIMARY KEY,
    user_id      BIGINT NOT NULL REFERENCES users(user_id),
    question     TEXT NOT NULL,
    answer       TEXT,
    citations    JSONB,
    model        TEXT,
    refused      BOOLEAN NOT NULL DEFAULT FALSE,
    latency_ms   INTEGER,
    tokens_in    BIGINT,
    tokens_out   BIGINT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_qa_log_user_created ON qa_log (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS product_versions (
    id           SERIAL PRIMARY KEY,
    version      TEXT NOT NULL UNIQUE,
    git_commit   TEXT NOT NULL,
    git_tag      TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_reports (
    id            BIGSERIAL PRIMARY KEY,
    user_id       BIGINT NOT NULL REFERENCES users(user_id),
    version_id    INTEGER NOT NULL REFERENCES product_versions(id),
    report_hash   TEXT NOT NULL,
    md_path       TEXT NOT NULL,
    json_path     TEXT NOT NULL,
    coverage      NUMERIC(5,4),
    compliance    NUMERIC(5,4),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, version_id)
);

CREATE TABLE IF NOT EXISTS gost_requirements (
    id           SERIAL PRIMARY KEY,
    gost         TEXT NOT NULL,
    clause       TEXT NOT NULL,
    requirement  TEXT NOT NULL,
    modality     TEXT NOT NULL,
    category     TEXT NOT NULL,
    UNIQUE (gost, clause, requirement)
);

CREATE TABLE IF NOT EXISTS audit_findings (
    id             BIGSERIAL PRIMARY KEY,
    report_id      BIGINT NOT NULL REFERENCES audit_reports(id) ON DELETE CASCADE,
    requirement_id INTEGER NOT NULL REFERENCES gost_requirements(id),
    status         TEXT NOT NULL,
    evidence       TEXT,
    confidence     NUMERIC(4,3),
    severity       TEXT
);
