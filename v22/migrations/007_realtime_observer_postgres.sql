CREATE TABLE IF NOT EXISTS realtime_runtime_sessions(
 session_id UUID PRIMARY KEY,
 instance_id TEXT NOT NULL,
 version TEXT NOT NULL,
 status TEXT NOT NULL,
 primary_provider TEXT NOT NULL,
 secondary_provider TEXT,
 universe_json JSONB NOT NULL DEFAULT '[]'::jsonb,
 started_at TIMESTAMPTZ NOT NULL,
 last_heartbeat_at TIMESTAMPTZ NOT NULL,
 stopped_at TIMESTAMPTZ,
 stop_reason TEXT,
 metrics_json JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS ix_realtime_runtime_heartbeat ON realtime_runtime_sessions(last_heartbeat_at DESC);

CREATE TABLE IF NOT EXISTS realtime_provider_health(
 session_id UUID NOT NULL REFERENCES realtime_runtime_sessions(session_id),
 provider TEXT NOT NULL,
 status TEXT NOT NULL,
 connected_at TIMESTAMPTZ,
 last_message_at TIMESTAMPTZ,
 last_event_at TIMESTAMPTZ,
 reconnects INTEGER NOT NULL DEFAULT 0,
 scheduled_reconnects INTEGER NOT NULL DEFAULT 0,
 messages BIGINT NOT NULL DEFAULT 0,
 max_message_gap_seconds DOUBLE PRECISION NOT NULL DEFAULT 0,
 errors INTEGER NOT NULL DEFAULT 0,
 last_error TEXT,
 updated_at TIMESTAMPTZ NOT NULL,
 PRIMARY KEY(session_id,provider)
);

CREATE TABLE IF NOT EXISTS realtime_asset_health(
 session_id UUID NOT NULL REFERENCES realtime_runtime_sessions(session_id),
 asset_id TEXT NOT NULL,
 active_provider TEXT,
 primary_last_message_at TIMESTAMPTZ,
 secondary_last_message_at TIMESTAMPTZ,
 last_trade_at TIMESTAMPTZ,
 last_bar_close_at TIMESTAMPTZ,
 expected_minutes INTEGER NOT NULL DEFAULT 0,
 live_minutes INTEGER NOT NULL DEFAULT 0,
 coverage_pct DOUBLE PRECISION NOT NULL DEFAULT 0,
 max_message_gap_seconds DOUBLE PRECISION NOT NULL DEFAULT 0,
 max_gap_seconds DOUBLE PRECISION NOT NULL DEFAULT 0,
 failovers INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL DEFAULT 'STARTING',
 updated_at TIMESTAMPTZ NOT NULL,
 PRIMARY KEY(session_id,asset_id)
);
CREATE INDEX IF NOT EXISTS ix_realtime_asset_health_update ON realtime_asset_health(updated_at DESC);

CREATE TABLE IF NOT EXISTS realtime_bars_1m(
 asset_id TEXT NOT NULL,
 bucket_start TIMESTAMPTZ NOT NULL,
 provider TEXT NOT NULL,
 provenance TEXT NOT NULL,
 decision_eligible BOOLEAN NOT NULL DEFAULT TRUE,
 open DOUBLE PRECISION NOT NULL,
 high DOUBLE PRECISION NOT NULL,
 low DOUBLE PRECISION NOT NULL,
 close DOUBLE PRECISION NOT NULL,
 base_volume DOUBLE PRECISION NOT NULL DEFAULT 0,
 quote_volume DOUBLE PRECISION NOT NULL DEFAULT 0,
 signed_quote_volume DOUBLE PRECISION NOT NULL DEFAULT 0,
 trades INTEGER NOT NULL DEFAULT 0,
 first_event_at TIMESTAMPTZ,
 last_event_at TIMESTAMPTZ,
 source_latency_ms_avg DOUBLE PRECISION,
 written_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(asset_id,bucket_start)
);
CREATE INDEX IF NOT EXISTS ix_realtime_bars_time ON realtime_bars_1m(bucket_start DESC);

CREATE TABLE IF NOT EXISTS realtime_timeframe_state(
 asset_id TEXT NOT NULL,
 timeframe TEXT NOT NULL,
 measured_at TIMESTAMPTZ NOT NULL,
 window_minutes INTEGER NOT NULL,
 change_pct DOUBLE PRECISION NOT NULL,
 quote_volume DOUBLE PRECISION NOT NULL,
 signed_quote_volume DOUBLE PRECISION NOT NULL,
 flow_share DOUBLE PRECISION NOT NULL,
 participation_ratio DOUBLE PRECISION,
 direction TEXT NOT NULL,
 volume_flow TEXT NOT NULL,
 coverage_pct DOUBLE PRECISION NOT NULL,
 provenance TEXT NOT NULL,
 decision_eligible BOOLEAN NOT NULL,
 metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
 PRIMARY KEY(asset_id,timeframe,measured_at)
);
CREATE INDEX IF NOT EXISTS ix_realtime_state_time ON realtime_timeframe_state(measured_at DESC,timeframe);

CREATE TABLE IF NOT EXISTS realtime_signal_events(
 event_id UUID PRIMARY KEY,
 session_id UUID NOT NULL REFERENCES realtime_runtime_sessions(session_id),
 asset_id TEXT NOT NULL,
 event_type TEXT NOT NULL,
 event_time TIMESTAMPTZ NOT NULL,
 provider TEXT NOT NULL,
 provenance TEXT NOT NULL,
 decision_eligible BOOLEAN NOT NULL,
 value DOUBLE PRECISION NOT NULL,
 threshold DOUBLE PRECISION NOT NULL,
 evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS ix_realtime_signal_time ON realtime_signal_events(event_time DESC,asset_id);

CREATE TABLE IF NOT EXISTS realtime_gap_events(
 gap_id UUID PRIMARY KEY,
 session_id UUID NOT NULL REFERENCES realtime_runtime_sessions(session_id),
 asset_id TEXT,
 provider TEXT,
 gap_start TIMESTAMPTZ NOT NULL,
 gap_end TIMESTAMPTZ,
 duration_seconds DOUBLE PRECISION,
 reason TEXT NOT NULL,
 recovered_by TEXT,
 decision_eligible BOOLEAN NOT NULL DEFAULT FALSE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_realtime_gap_time ON realtime_gap_events(gap_start DESC);
