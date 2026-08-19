CREATE TABLE IF NOT EXISTS realtime_runtime_sessions(
 session_id TEXT PRIMARY KEY,
 instance_id TEXT NOT NULL,
 version TEXT NOT NULL,
 status TEXT NOT NULL,
 primary_provider TEXT NOT NULL,
 secondary_provider TEXT,
 universe_json TEXT NOT NULL DEFAULT '[]',
 started_at TEXT NOT NULL,
 last_heartbeat_at TEXT NOT NULL,
 stopped_at TEXT,
 stop_reason TEXT,
 metrics_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_realtime_runtime_heartbeat ON realtime_runtime_sessions(last_heartbeat_at DESC);

CREATE TABLE IF NOT EXISTS realtime_provider_health(
 session_id TEXT NOT NULL REFERENCES realtime_runtime_sessions(session_id),
 provider TEXT NOT NULL,
 status TEXT NOT NULL,
 connected_at TEXT,
 last_message_at TEXT,
 last_event_at TEXT,
 reconnects INTEGER NOT NULL DEFAULT 0,
 scheduled_reconnects INTEGER NOT NULL DEFAULT 0,
 messages INTEGER NOT NULL DEFAULT 0,
 max_message_gap_seconds REAL NOT NULL DEFAULT 0,
 errors INTEGER NOT NULL DEFAULT 0,
 last_error TEXT,
 updated_at TEXT NOT NULL,
 PRIMARY KEY(session_id,provider)
);

CREATE TABLE IF NOT EXISTS realtime_asset_health(
 session_id TEXT NOT NULL REFERENCES realtime_runtime_sessions(session_id),
 asset_id TEXT NOT NULL,
 active_provider TEXT,
 primary_last_message_at TEXT,
 secondary_last_message_at TEXT,
 last_trade_at TEXT,
 last_bar_close_at TEXT,
 expected_minutes INTEGER NOT NULL DEFAULT 0,
 live_minutes INTEGER NOT NULL DEFAULT 0,
 coverage_pct REAL NOT NULL DEFAULT 0,
 max_message_gap_seconds REAL NOT NULL DEFAULT 0,
 max_gap_seconds REAL NOT NULL DEFAULT 0,
 failovers INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL DEFAULT 'STARTING',
 updated_at TEXT NOT NULL,
 PRIMARY KEY(session_id,asset_id)
);
CREATE INDEX IF NOT EXISTS ix_realtime_asset_health_update ON realtime_asset_health(updated_at DESC);

CREATE TABLE IF NOT EXISTS realtime_bars_1m(
 asset_id TEXT NOT NULL,
 bucket_start TEXT NOT NULL,
 provider TEXT NOT NULL,
 provenance TEXT NOT NULL,
 decision_eligible INTEGER NOT NULL DEFAULT 1,
 open REAL NOT NULL,
 high REAL NOT NULL,
 low REAL NOT NULL,
 close REAL NOT NULL,
 base_volume REAL NOT NULL DEFAULT 0,
 quote_volume REAL NOT NULL DEFAULT 0,
 signed_quote_volume REAL NOT NULL DEFAULT 0,
 trades INTEGER NOT NULL DEFAULT 0,
 first_event_at TEXT,
 last_event_at TEXT,
 source_latency_ms_avg REAL,
 written_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(asset_id,bucket_start)
);
CREATE INDEX IF NOT EXISTS ix_realtime_bars_time ON realtime_bars_1m(bucket_start DESC);

CREATE TABLE IF NOT EXISTS realtime_timeframe_state(
 asset_id TEXT NOT NULL,
 timeframe TEXT NOT NULL,
 measured_at TEXT NOT NULL,
 window_minutes INTEGER NOT NULL,
 change_pct REAL NOT NULL,
 quote_volume REAL NOT NULL,
 signed_quote_volume REAL NOT NULL,
 flow_share REAL NOT NULL,
 participation_ratio REAL,
 direction TEXT NOT NULL,
 volume_flow TEXT NOT NULL,
 coverage_pct REAL NOT NULL,
 provenance TEXT NOT NULL,
 decision_eligible INTEGER NOT NULL,
 metadata_json TEXT NOT NULL DEFAULT '{}',
 PRIMARY KEY(asset_id,timeframe,measured_at)
);
CREATE INDEX IF NOT EXISTS ix_realtime_state_time ON realtime_timeframe_state(measured_at DESC,timeframe);

CREATE TABLE IF NOT EXISTS realtime_signal_events(
 event_id TEXT PRIMARY KEY,
 session_id TEXT NOT NULL REFERENCES realtime_runtime_sessions(session_id),
 asset_id TEXT NOT NULL,
 event_type TEXT NOT NULL,
 event_time TEXT NOT NULL,
 provider TEXT NOT NULL,
 provenance TEXT NOT NULL,
 decision_eligible INTEGER NOT NULL,
 value REAL NOT NULL,
 threshold REAL NOT NULL,
 evidence_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_realtime_signal_time ON realtime_signal_events(event_time DESC,asset_id);

CREATE TABLE IF NOT EXISTS realtime_gap_events(
 gap_id TEXT PRIMARY KEY,
 session_id TEXT NOT NULL REFERENCES realtime_runtime_sessions(session_id),
 asset_id TEXT,
 provider TEXT,
 gap_start TEXT NOT NULL,
 gap_end TEXT,
 duration_seconds REAL,
 reason TEXT NOT NULL,
 recovered_by TEXT,
 decision_eligible INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_realtime_gap_time ON realtime_gap_events(gap_start DESC);
