CREATE TABLE IF NOT EXISTS brain_failure_events(
 failure_id TEXT PRIMARY KEY,
 idempotency_key TEXT NOT NULL UNIQUE,
 cycle_id TEXT NOT NULL REFERENCES brain_cycles(cycle_id),
 asset_id TEXT,
 stage TEXT NOT NULL,
 component TEXT NOT NULL,
 error_type TEXT NOT NULL,
 message TEXT NOT NULL,
 severity TEXT NOT NULL,
 retryable INTEGER NOT NULL DEFAULT 0,
 fingerprint TEXT NOT NULL,
 occurred_at TEXT NOT NULL,
 details_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_failure_cycle_time ON brain_failure_events(cycle_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_failure_stage_time ON brain_failure_events(stage, occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_failure_fingerprint ON brain_failure_events(fingerprint);
