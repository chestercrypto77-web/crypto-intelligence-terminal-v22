CREATE TABLE IF NOT EXISTS brain_cycles(
 cycle_id TEXT PRIMARY KEY,
 cycle_key TEXT NOT NULL UNIQUE,
 cycle_type TEXT NOT NULL,
 scheduled_at TEXT NOT NULL,
 started_at TEXT,
 completed_at TEXT,
 workflow_id TEXT,
 status TEXT NOT NULL,
 expected_assets INTEGER NOT NULL DEFAULT 0,
 analysed_assets INTEGER NOT NULL DEFAULT 0,
 error TEXT,
 provenance_json TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_brain_cycles_type_time ON brain_cycles(cycle_type, scheduled_at DESC);
CREATE INDEX IF NOT EXISTS ix_brain_cycles_status ON brain_cycles(status, scheduled_at DESC);

CREATE TABLE IF NOT EXISTS evidence_records(
 evidence_id TEXT PRIMARY KEY,
 idempotency_key TEXT NOT NULL UNIQUE,
 cycle_id TEXT NOT NULL REFERENCES brain_cycles(cycle_id),
 asset_id TEXT NOT NULL,
 metric TEXT NOT NULL,
 value_json TEXT NOT NULL,
 unit TEXT,
 source TEXT NOT NULL,
 source_timestamp TEXT NOT NULL,
 retrieved_at TEXT NOT NULL,
 quality TEXT NOT NULL,
 raw_reference TEXT,
 metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_evidence_cycle_asset ON evidence_records(cycle_id, asset_id);
CREATE INDEX IF NOT EXISTS ix_evidence_asset_metric_time ON evidence_records(asset_id, metric, source_timestamp DESC);

CREATE TABLE IF NOT EXISTS observation_records(
 observation_id TEXT PRIMARY KEY,
 idempotency_key TEXT NOT NULL UNIQUE,
 cycle_id TEXT NOT NULL REFERENCES brain_cycles(cycle_id),
 asset_id TEXT NOT NULL,
 metric TEXT NOT NULL,
 value_json TEXT NOT NULL,
 observed_at TEXT NOT NULL,
 calculation TEXT NOT NULL,
 quality TEXT NOT NULL,
 evidence_ids_json TEXT NOT NULL DEFAULT '[]',
 metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_observation_cycle_asset ON observation_records(cycle_id, asset_id);
CREATE INDEX IF NOT EXISTS ix_observation_asset_metric_time ON observation_records(asset_id, metric, observed_at DESC);

CREATE TABLE IF NOT EXISTS cycle_asset_coverage(
 cycle_id TEXT NOT NULL REFERENCES brain_cycles(cycle_id),
 asset_id TEXT NOT NULL,
 expected INTEGER NOT NULL DEFAULT 1,
 evidence_collected INTEGER NOT NULL DEFAULT 0,
 deterministic_completed INTEGER NOT NULL DEFAULT 0,
 ai_requested INTEGER NOT NULL DEFAULT 0,
 ai_completed INTEGER NOT NULL DEFAULT 0,
 quality TEXT NOT NULL,
 failure_reason TEXT,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(cycle_id, asset_id)
);

CREATE TABLE IF NOT EXISTS specialist_findings(
 finding_id TEXT PRIMARY KEY,
 cycle_id TEXT NOT NULL REFERENCES brain_cycles(cycle_id),
 specialist TEXT NOT NULL,
 claim TEXT NOT NULL,
 anomaly_level TEXT NOT NULL,
 evidence_ids_json TEXT NOT NULL,
 supporting_factors_json TEXT NOT NULL DEFAULT '[]',
 contradicting_factors_json TEXT NOT NULL DEFAULT '[]',
 uncertainties_json TEXT NOT NULL DEFAULT '[]',
 created_at TEXT NOT NULL,
 provenance_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_findings_cycle ON specialist_findings(cycle_id, specialist);

CREATE TABLE IF NOT EXISTS synthesis_records(
 synthesis_id TEXT PRIMARY KEY,
 cycle_id TEXT NOT NULL REFERENCES brain_cycles(cycle_id),
 summary TEXT NOT NULL,
 finding_ids_json TEXT NOT NULL,
 disagreements_json TEXT NOT NULL DEFAULT '[]',
 created_at TEXT NOT NULL,
 provenance_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS episodes(
 episode_id TEXT PRIMARY KEY,
 cycle_id TEXT REFERENCES brain_cycles(cycle_id),
 asset_id TEXT,
 episode_type TEXT NOT NULL,
 description TEXT,
 opened_at TEXT NOT NULL,
 closed_at TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_episode_asset_time ON episodes(asset_id, opened_at DESC);

CREATE TABLE IF NOT EXISTS episode_outcomes(
 outcome_id TEXT PRIMARY KEY,
 episode_id TEXT NOT NULL REFERENCES episodes(episode_id),
 horizon TEXT NOT NULL,
 measured_at TEXT NOT NULL,
 metrics_json TEXT NOT NULL,
 source TEXT NOT NULL,
 UNIQUE(episode_id, horizon, source)
);

CREATE TABLE IF NOT EXISTS ai_calls(
 call_id TEXT PRIMARY KEY,
 cycle_id TEXT NOT NULL REFERENCES brain_cycles(cycle_id),
 specialist TEXT NOT NULL,
 provider TEXT NOT NULL,
 model TEXT NOT NULL,
 invoked_at TEXT NOT NULL,
 completed_at TEXT,
 reason TEXT NOT NULL,
 status TEXT NOT NULL,
 protected_data_check INTEGER NOT NULL,
 input_tokens INTEGER,
 output_tokens INTEGER,
 error TEXT
);
CREATE INDEX IF NOT EXISTS ix_ai_calls_cycle ON ai_calls(cycle_id, invoked_at DESC);

CREATE TABLE IF NOT EXISTS semantic_memory_queue(
 memory_id TEXT PRIMARY KEY,
 memory_type TEXT NOT NULL,
 source_id TEXT NOT NULL,
 text_content TEXT NOT NULL,
 embedding_provider TEXT,
 embedding_model TEXT,
 embedding_json TEXT,
 embedded_at TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(memory_type, source_id)
);
