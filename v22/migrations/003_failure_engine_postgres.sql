CREATE TABLE IF NOT EXISTS brain_failure_events(
 failure_id UUID PRIMARY KEY,
 idempotency_key TEXT NOT NULL UNIQUE,
 cycle_id UUID NOT NULL REFERENCES brain_cycles(cycle_id),
 asset_id TEXT,
 stage TEXT NOT NULL,
 component TEXT NOT NULL,
 error_type TEXT NOT NULL,
 message TEXT NOT NULL,
 severity TEXT NOT NULL,
 retryable BOOLEAN NOT NULL DEFAULT FALSE,
 fingerprint TEXT NOT NULL,
 occurred_at TIMESTAMPTZ NOT NULL,
 details_json JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS ix_failure_cycle_time ON brain_failure_events(cycle_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_failure_stage_time ON brain_failure_events(stage, occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_failure_fingerprint ON brain_failure_events(fingerprint);
