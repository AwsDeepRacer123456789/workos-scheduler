-- KernelQ: first durable job records for the control plane.
--
-- Why this table exists:
-- In-memory job stores disappear on restart. Postgres holds the authoritative
-- job row so APIs and workers can recover state, audit history, and coordinate
-- across processes after crashes or deploys.
--
-- payload JSONB:
-- Keeps flexible client/job inputs without schema churn for every new field.

CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    priority INTEGER NOT NULL,
    state TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,

    CONSTRAINT jobs_priority_non_negative CHECK (priority >= 0),
    CONSTRAINT jobs_retry_count_non_negative CHECK (retry_count >= 0),
    CONSTRAINT jobs_max_retries_non_negative CHECK (max_retries >= 0)
);

-- Filters like "all queued jobs" or dashboards grouped by lifecycle state.
CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs (state);

-- Multi-tenant fairness, quotas, and per-customer job listings.
CREATE INDEX IF NOT EXISTS idx_jobs_tenant_id ON jobs (tenant_id);

-- Scheduling policies that order work by importance within a queue or tenant.
CREATE INDEX IF NOT EXISTS idx_jobs_priority ON jobs (priority);

-- Typical admin/support query: what is waiting (or stuck) for one tenant?
CREATE INDEX IF NOT EXISTS idx_jobs_state_tenant ON jobs (state, tenant_id);

-- Pick highest-priority work among jobs in a given state (e.g. queued).
CREATE INDEX IF NOT EXISTS idx_jobs_state_priority ON jobs (state, priority);

COMMENT ON TABLE jobs IS
    'Durable KernelQ job rows: identity, tenant, scheduling hints, lifecycle state, and opaque payload.';

COMMENT ON COLUMN jobs.job_id IS 'Stable external identifier for the job.';
COMMENT ON COLUMN jobs.tenant_id IS 'Isolation boundary for fairness and access control.';
COMMENT ON COLUMN jobs.priority IS 'Scheduling urgency; higher usually means run sooner (policy-defined).';
COMMENT ON COLUMN jobs.state IS 'Current lifecycle state (matches application JobState values).';
COMMENT ON COLUMN jobs.payload IS 'JSON payload from clients or internal metadata; validated at API boundaries.';
COMMENT ON COLUMN jobs.created_at IS 'When the job row was first inserted.';
COMMENT ON COLUMN jobs.updated_at IS 'Last mutation time; update from app code on state changes.';
COMMENT ON COLUMN jobs.retry_count IS 'How many retries have been attempted after failures.';
COMMENT ON COLUMN jobs.max_retries IS 'Upper bound on retries before dead-letter or terminal failure.';
