CREATE TABLE IF NOT EXISTS paper_position_marks(
 mark_id TEXT PRIMARY KEY,
 position_id TEXT NOT NULL REFERENCES paper_positions(position_id),
 brain_id TEXT NOT NULL REFERENCES paper_brains(brain_id),
 cycle_id TEXT REFERENCES brain_cycles(cycle_id),
 asset_id TEXT NOT NULL,
 price_aud REAL NOT NULL CHECK(price_aud > 0),
 return_pct REAL NOT NULL,
 marked_at TEXT NOT NULL,
 UNIQUE(position_id,cycle_id)
);
CREATE INDEX IF NOT EXISTS ix_paper_marks_position_time ON paper_position_marks(position_id,marked_at DESC);

CREATE TABLE IF NOT EXISTS paper_trade_outcomes(
 outcome_id TEXT PRIMARY KEY,
 position_id TEXT NOT NULL UNIQUE REFERENCES paper_positions(position_id),
 brain_id TEXT NOT NULL REFERENCES paper_brains(brain_id),
 asset_id TEXT NOT NULL,
 entry_price_aud REAL NOT NULL CHECK(entry_price_aud > 0),
 exit_price_aud REAL NOT NULL CHECK(exit_price_aud > 0),
 cost_basis_aud REAL NOT NULL CHECK(cost_basis_aud >= 0),
 proceeds_aud REAL NOT NULL CHECK(proceeds_aud >= 0),
 pnl_aud REAL NOT NULL,
 return_pct REAL NOT NULL,
 max_favourable_pct REAL NOT NULL,
 max_adverse_pct REAL NOT NULL,
 holding_minutes REAL NOT NULL CHECK(holding_minutes >= 0),
 entry_reason TEXT,
 exit_reason TEXT NOT NULL,
 entry_evidence_json TEXT NOT NULL DEFAULT '{}',
 opened_at TEXT NOT NULL,
 closed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_paper_outcomes_brain_time ON paper_trade_outcomes(brain_id,closed_at DESC);
