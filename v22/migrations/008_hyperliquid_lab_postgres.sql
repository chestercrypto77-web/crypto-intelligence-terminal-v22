CREATE TABLE IF NOT EXISTS hl_lab_sessions(
 session_id UUID PRIMARY KEY,status TEXT NOT NULL,started_at TEXT NOT NULL,last_heartbeat_at TEXT NOT NULL,
 universe_json JSONB NOT NULL DEFAULT '[]',execution_mode TEXT NOT NULL DEFAULT 'DISABLED',metrics_json JSONB NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS hl_lab_provider_health(
 session_id UUID NOT NULL REFERENCES hl_lab_sessions(session_id),provider TEXT NOT NULL,status TEXT NOT NULL,
 connected_at TEXT,last_message_at TEXT,messages INTEGER NOT NULL DEFAULT 0,reconnects INTEGER NOT NULL DEFAULT 0,
 errors INTEGER NOT NULL DEFAULT 0,max_gap_seconds DOUBLE PRECISION NOT NULL DEFAULT 0,last_error TEXT,updated_at TEXT NOT NULL,
 PRIMARY KEY(session_id,provider));
CREATE TABLE IF NOT EXISTS hl_lab_trades(
 event_id UUID PRIMARY KEY,session_id UUID NOT NULL REFERENCES hl_lab_sessions(session_id),asset_id TEXT NOT NULL,
 event_time TEXT NOT NULL,received_at TEXT NOT NULL,price DOUBLE PRECISION NOT NULL,size DOUBLE PRECISION NOT NULL,side TEXT NOT NULL,trade_id TEXT NOT NULL,
 UNIQUE(asset_id,event_time,trade_id));
CREATE INDEX IF NOT EXISTS ix_hl_trades_asset_time ON hl_lab_trades(asset_id,event_time DESC);
CREATE TABLE IF NOT EXISTS hl_lab_books(
 snapshot_id UUID PRIMARY KEY,session_id UUID NOT NULL REFERENCES hl_lab_sessions(session_id),asset_id TEXT NOT NULL,
 event_time TEXT NOT NULL,received_at TEXT NOT NULL,best_bid DOUBLE PRECISION NOT NULL,best_ask DOUBLE PRECISION NOT NULL,spread_bps DOUBLE PRECISION NOT NULL,
 bid_depth DOUBLE PRECISION NOT NULL,ask_depth DOUBLE PRECISION NOT NULL,imbalance DOUBLE PRECISION NOT NULL);
CREATE INDEX IF NOT EXISTS ix_hl_books_asset_time ON hl_lab_books(asset_id,event_time DESC);
CREATE TABLE IF NOT EXISTS hl_lab_signals(
 signal_id UUID PRIMARY KEY,session_id UUID NOT NULL REFERENCES hl_lab_sessions(session_id),asset_id TEXT NOT NULL,event_time TEXT NOT NULL,
 signal_type TEXT NOT NULL,direction TEXT NOT NULL,price DOUBLE PRECISION NOT NULL,spread_bps DOUBLE PRECISION,book_imbalance DOUBLE PRECISION,buy_flow_share DOUBLE PRECISION,
 evidence_json JSONB NOT NULL DEFAULT '{}',execution_eligible INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_hl_signals_time ON hl_lab_signals(event_time DESC,asset_id);
