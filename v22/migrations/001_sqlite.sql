PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS engine_heartbeats(
 id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, engine TEXT NOT NULL,
 instance_id TEXT NOT NULL, status TEXT NOT NULL, evidence_class TEXT NOT NULL DEFAULT 'LIVE',
 scheduled_for REAL, started_at REAL NOT NULL, completed_at REAL, duration_ms INTEGER,
 details_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_heartbeat_engine_time ON engine_heartbeats(engine, started_at DESC);

CREATE TABLE IF NOT EXISTS observation_runs(
 id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL UNIQUE, engine TEXT NOT NULL,
 interval_seconds INTEGER NOT NULL, scheduled_for REAL NOT NULL, started_at REAL NOT NULL,
 completed_at REAL, status TEXT NOT NULL, evidence_class TEXT NOT NULL,
 assets_requested INTEGER NOT NULL DEFAULT 0, assets_analysed INTEGER NOT NULL DEFAULT 0,
 error TEXT, source TEXT NOT NULL DEFAULT 'V22'
);
CREATE INDEX IF NOT EXISTS ix_observation_engine_sched ON observation_runs(engine, scheduled_for DESC);

CREATE TABLE IF NOT EXISTS observation_gaps(
 id INTEGER PRIMARY KEY AUTOINCREMENT, engine TEXT NOT NULL, interval_seconds INTEGER NOT NULL,
 gap_start REAL NOT NULL, gap_end REAL NOT NULL, missing_intervals INTEGER NOT NULL,
 recovery_status TEXT NOT NULL DEFAULT 'DETECTED', detected_at REAL NOT NULL, details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS system_incidents(
 id INTEGER PRIMARY KEY AUTOINCREMENT, incident_key TEXT NOT NULL, severity TEXT NOT NULL,
 component TEXT NOT NULL, opened_at REAL NOT NULL, resolved_at REAL, status TEXT NOT NULL,
 message TEXT NOT NULL, details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS communication_receipts(
 id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, producer TEXT NOT NULL,
 consumer TEXT NOT NULL, produced_at REAL NOT NULL, consumed_at REAL NOT NULL,
 records_consumed INTEGER NOT NULL DEFAULT 0, source_ref TEXT, details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS v21_bridge_events(
 id INTEGER PRIMARY KEY AUTOINCREMENT, imported_at REAL NOT NULL, source_file TEXT NOT NULL,
 source_timestamp TEXT, source_hash TEXT NOT NULL, record_count INTEGER NOT NULL DEFAULT 0,
 details_json TEXT NOT NULL DEFAULT '{}', UNIQUE(source_file, source_hash)
);

CREATE TABLE IF NOT EXISTS supervisor_state(
 key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at REAL NOT NULL
);
