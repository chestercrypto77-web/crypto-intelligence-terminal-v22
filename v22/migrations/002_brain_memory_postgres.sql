CREATE TABLE IF NOT EXISTS brain_cycles(
 cycle_id UUID PRIMARY KEY,
 cycle_key TEXT NOT NULL UNIQUE,
 cycle_type TEXT NOT NULL,
 scheduled_at TIMESTAMPTZ NOT NULL,
 started_at TIMESTAMPTZ,
 completed_at TIMESTAMPTZ,
 workflow_id TEXT,
 status TEXT NOT NULL,
 expected_assets INTEGER NOT NULL DEFAULT 0 CHECK(expected_assets >= 0),
 analysed_assets INTEGER NOT NULL DEFAULT 0 CHECK(analysed_assets >= 0),
 error TEXT,
 provenance_json JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_brain_cycles_type_time ON brain_cycles(cycle_type, scheduled_at DESC);
CREATE INDEX IF NOT EXISTS ix_brain_cycles_status ON brain_cycles(status, scheduled_at DESC);

CREATE TABLE IF NOT EXISTS evidence_records(
 evidence_id UUID PRIMARY KEY,
 idempotency_key TEXT NOT NULL UNIQUE,
 cycle_id UUID NOT NULL REFERENCES brain_cycles(cycle_id),
 asset_id TEXT NOT NULL,
 metric TEXT NOT NULL,
 value_json JSONB NOT NULL,
 unit TEXT,
 source TEXT NOT NULL,
 source_timestamp TIMESTAMPTZ NOT NULL,
 retrieved_at TIMESTAMPTZ NOT NULL,
 quality TEXT NOT NULL,
 raw_reference TEXT,
 metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS ix_evidence_cycle_asset ON evidence_records(cycle_id, asset_id);
CREATE INDEX IF NOT EXISTS ix_evidence_asset_metric_time ON evidence_records(asset_id, metric, source_timestamp DESC);

CREATE TABLE IF NOT EXISTS observation_records(
 observation_id UUID PRIMARY KEY,
 idempotency_key TEXT NOT NULL UNIQUE,
 cycle_id UUID NOT NULL REFERENCES brain_cycles(cycle_id),
 asset_id TEXT NOT NULL,
 metric TEXT NOT NULL,
 value_json JSONB NOT NULL,
 observed_at TIMESTAMPTZ NOT NULL,
 calculation TEXT NOT NULL,
 quality TEXT NOT NULL,
 evidence_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
 metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS ix_observation_cycle_asset ON observation_records(cycle_id, asset_id);
CREATE INDEX IF NOT EXISTS ix_observation_asset_metric_time ON observation_records(asset_id, metric, observed_at DESC);

CREATE TABLE IF NOT EXISTS cycle_asset_coverage(
 cycle_id UUID NOT NULL REFERENCES brain_cycles(cycle_id),
 asset_id TEXT NOT NULL,
 expected BOOLEAN NOT NULL DEFAULT TRUE,
 evidence_collected BOOLEAN NOT NULL DEFAULT FALSE,
 deterministic_completed BOOLEAN NOT NULL DEFAULT FALSE,
 ai_requested BOOLEAN NOT NULL DEFAULT FALSE,
 ai_completed BOOLEAN NOT NULL DEFAULT FALSE,
 quality TEXT NOT NULL,
 failure_reason TEXT,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(cycle_id, asset_id)
);

CREATE TABLE IF NOT EXISTS specialist_findings(
 finding_id UUID PRIMARY KEY,
 cycle_id UUID NOT NULL REFERENCES brain_cycles(cycle_id),
 specialist TEXT NOT NULL,
 claim TEXT NOT NULL,
 anomaly_level TEXT NOT NULL,
 evidence_ids_json JSONB NOT NULL,
 supporting_factors_json JSONB NOT NULL DEFAULT '[]'::jsonb,
 contradicting_factors_json JSONB NOT NULL DEFAULT '[]'::jsonb,
 uncertainties_json JSONB NOT NULL DEFAULT '[]'::jsonb,
 created_at TIMESTAMPTZ NOT NULL,
 provenance_json JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_findings_cycle ON specialist_findings(cycle_id, specialist);

CREATE TABLE IF NOT EXISTS synthesis_records(
 synthesis_id UUID PRIMARY KEY,
 cycle_id UUID NOT NULL REFERENCES brain_cycles(cycle_id),
 summary TEXT NOT NULL,
 finding_ids_json JSONB NOT NULL,
 disagreements_json JSONB NOT NULL DEFAULT '[]'::jsonb,
 created_at TIMESTAMPTZ NOT NULL,
 provenance_json JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS episodes(
 episode_id UUID PRIMARY KEY,
 cycle_id UUID REFERENCES brain_cycles(cycle_id),
 asset_id TEXT,
 episode_type TEXT NOT NULL,
 description TEXT,
 opened_at TIMESTAMPTZ NOT NULL,
 closed_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_episode_asset_time ON episodes(asset_id, opened_at DESC);

CREATE TABLE IF NOT EXISTS episode_outcomes(
 outcome_id UUID PRIMARY KEY,
 episode_id UUID NOT NULL REFERENCES episodes(episode_id),
 horizon TEXT NOT NULL,
 measured_at TIMESTAMPTZ NOT NULL,
 metrics_json JSONB NOT NULL,
 source TEXT NOT NULL,
 UNIQUE(episode_id, horizon, source)
);

CREATE TABLE IF NOT EXISTS ai_calls(
 call_id UUID PRIMARY KEY,
 cycle_id UUID NOT NULL REFERENCES brain_cycles(cycle_id),
 specialist TEXT NOT NULL,
 provider TEXT NOT NULL,
 model TEXT NOT NULL,
 invoked_at TIMESTAMPTZ NOT NULL,
 completed_at TIMESTAMPTZ,
 reason TEXT NOT NULL,
 status TEXT NOT NULL,
 protected_data_check BOOLEAN NOT NULL,
 input_tokens INTEGER,
 output_tokens INTEGER,
 error TEXT
);
CREATE INDEX IF NOT EXISTS ix_ai_calls_cycle ON ai_calls(cycle_id, invoked_at DESC);

-- Stage 1 deliberately stores semantic-memory candidates without vector indexes.
-- pgvector is introduced at the Episode/Semantic Retrieval stage after the
-- embedding provider and dimensionality are proven rather than guessed now.
CREATE TABLE IF NOT EXISTS semantic_memory_queue(
 memory_id UUID PRIMARY KEY,
 memory_type TEXT NOT NULL,
 source_id TEXT NOT NULL,
 text_content TEXT NOT NULL,
 embedding_provider TEXT,
 embedding_model TEXT,
 embedding_json JSONB,
 embedded_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(memory_type, source_id)
);
