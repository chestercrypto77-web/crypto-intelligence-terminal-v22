CREATE TABLE IF NOT EXISTS engine_heartbeats(
 id BIGSERIAL PRIMARY KEY, run_id TEXT NOT NULL, engine TEXT NOT NULL,
 instance_id TEXT NOT NULL, status TEXT NOT NULL, evidence_class TEXT NOT NULL DEFAULT 'LIVE',
 scheduled_for DOUBLE PRECISION, started_at DOUBLE PRECISION NOT NULL, completed_at DOUBLE PRECISION, duration_ms INTEGER,
 details_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_heartbeat_engine_time ON engine_heartbeats(engine, started_at DESC);

CREATE TABLE IF NOT EXISTS observation_runs(
 id BIGSERIAL PRIMARY KEY, run_id TEXT NOT NULL UNIQUE, engine TEXT NOT NULL,
 interval_seconds INTEGER NOT NULL, scheduled_for DOUBLE PRECISION NOT NULL, started_at DOUBLE PRECISION NOT NULL,
 completed_at DOUBLE PRECISION, status TEXT NOT NULL, evidence_class TEXT NOT NULL,
 assets_requested INTEGER NOT NULL DEFAULT 0, assets_analysed INTEGER NOT NULL DEFAULT 0,
 error TEXT, source TEXT NOT NULL DEFAULT 'V22'
);
CREATE INDEX IF NOT EXISTS ix_observation_engine_sched ON observation_runs(engine, scheduled_for DESC);

CREATE TABLE IF NOT EXISTS observation_gaps(
 id BIGSERIAL PRIMARY KEY, engine TEXT NOT NULL, interval_seconds INTEGER NOT NULL,
 gap_start DOUBLE PRECISION NOT NULL, gap_end DOUBLE PRECISION NOT NULL, missing_intervals INTEGER NOT NULL,
 recovery_status TEXT NOT NULL DEFAULT 'DETECTED', detected_at DOUBLE PRECISION NOT NULL, details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS system_incidents(
 id BIGSERIAL PRIMARY KEY, incident_key TEXT NOT NULL, severity TEXT NOT NULL,
 component TEXT NOT NULL, opened_at DOUBLE PRECISION NOT NULL, resolved_at DOUBLE PRECISION, status TEXT NOT NULL,
 message TEXT NOT NULL, details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS communication_receipts(
 id BIGSERIAL PRIMARY KEY, run_id TEXT NOT NULL, producer TEXT NOT NULL,
 consumer TEXT NOT NULL, produced_at DOUBLE PRECISION NOT NULL, consumed_at DOUBLE PRECISION NOT NULL,
 records_consumed INTEGER NOT NULL DEFAULT 0, source_ref TEXT, details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS v21_bridge_events(
 id BIGSERIAL PRIMARY KEY, imported_at DOUBLE PRECISION NOT NULL, source_file TEXT NOT NULL,
 source_timestamp TEXT, source_hash TEXT NOT NULL, record_count INTEGER NOT NULL DEFAULT 0,
 details_json TEXT NOT NULL DEFAULT '{}', UNIQUE(source_file, source_hash)
);

CREATE TABLE IF NOT EXISTS supervisor_state(
 key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at DOUBLE PRECISION NOT NULL
);
