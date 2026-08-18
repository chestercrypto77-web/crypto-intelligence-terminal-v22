CREATE TABLE IF NOT EXISTS paper_competitions(
 competition_id TEXT PRIMARY KEY,
 reset_key TEXT NOT NULL UNIQUE,
 name TEXT NOT NULL,
 currency TEXT NOT NULL DEFAULT 'AUD',
 starting_cash_aud REAL NOT NULL CHECK(starting_cash_aud > 0),
 status TEXT NOT NULL DEFAULT 'ACTIVE',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS paper_brains(
 brain_id TEXT PRIMARY KEY,
 competition_id TEXT NOT NULL REFERENCES paper_competitions(competition_id),
 name TEXT NOT NULL,
 strategy_key TEXT NOT NULL,
 cash_aud REAL NOT NULL CHECK(cash_aud >= 0),
 realised_pnl_aud REAL NOT NULL DEFAULT 0,
 risk_multiplier REAL NOT NULL DEFAULT 1.0 CHECK(risk_multiplier >= 0.5 AND risk_multiplier <= 1.0),
 trades_closed INTEGER NOT NULL DEFAULT 0,
 wins INTEGER NOT NULL DEFAULT 0,
 losses INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(competition_id, strategy_key)
);

CREATE TABLE IF NOT EXISTS paper_positions(
 position_id TEXT PRIMARY KEY,
 brain_id TEXT NOT NULL REFERENCES paper_brains(brain_id),
 asset_id TEXT NOT NULL,
 quantity REAL NOT NULL CHECK(quantity >= 0),
 avg_entry_price_aud REAL NOT NULL CHECK(avg_entry_price_aud > 0),
 cost_basis_aud REAL NOT NULL CHECK(cost_basis_aud >= 0),
 opened_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'OPEN',
 add_count INTEGER NOT NULL DEFAULT 0,
 last_price_aud REAL,
 closed_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_paper_positions_brain_status ON paper_positions(brain_id,status);
CREATE UNIQUE INDEX IF NOT EXISTS ux_paper_one_open_asset ON paper_positions(brain_id,asset_id) WHERE status='OPEN';

CREATE TABLE IF NOT EXISTS paper_trade_decisions(
 decision_id TEXT PRIMARY KEY,
 brain_id TEXT NOT NULL REFERENCES paper_brains(brain_id),
 cycle_id TEXT REFERENCES brain_cycles(cycle_id),
 asset_id TEXT NOT NULL,
 action TEXT NOT NULL,
 reason TEXT NOT NULL,
 risk_approved INTEGER NOT NULL,
 requested_notional_aud REAL NOT NULL DEFAULT 0,
 approved_notional_aud REAL NOT NULL DEFAULT 0,
 price_aud REAL NOT NULL CHECK(price_aud > 0),
 fx_aud_per_usd REAL NOT NULL CHECK(fx_aud_per_usd > 0),
 observed_at TEXT NOT NULL,
 evidence_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_paper_decisions_brain_time ON paper_trade_decisions(brain_id,observed_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS ux_paper_decision_once ON paper_trade_decisions(brain_id,cycle_id,asset_id,action);

CREATE TABLE IF NOT EXISTS paper_trades(
 trade_id TEXT PRIMARY KEY,
 brain_id TEXT NOT NULL REFERENCES paper_brains(brain_id),
 position_id TEXT NOT NULL REFERENCES paper_positions(position_id),
 cycle_id TEXT REFERENCES brain_cycles(cycle_id),
 asset_id TEXT NOT NULL,
 side TEXT NOT NULL,
 quantity REAL NOT NULL CHECK(quantity > 0),
 price_aud REAL NOT NULL CHECK(price_aud > 0),
 notional_aud REAL NOT NULL CHECK(notional_aud > 0),
 executed_at TEXT NOT NULL,
 reason TEXT NOT NULL,
 cash_after_aud REAL NOT NULL CHECK(cash_after_aud >= 0)
);
CREATE INDEX IF NOT EXISTS ix_paper_trades_brain_time ON paper_trades(brain_id,executed_at DESC);

CREATE TABLE IF NOT EXISTS paper_lessons(
 lesson_id TEXT PRIMARY KEY,
 brain_id TEXT NOT NULL REFERENCES paper_brains(brain_id),
 lesson_key TEXT NOT NULL,
 sample_size INTEGER NOT NULL,
 wins INTEGER NOT NULL,
 losses INTEGER NOT NULL,
 win_rate REAL NOT NULL,
 avg_return_pct REAL NOT NULL,
 proposed_risk_multiplier REAL NOT NULL CHECK(proposed_risk_multiplier >= 0.5 AND proposed_risk_multiplier <= 1.0),
 previous_risk_multiplier REAL NOT NULL,
 state TEXT NOT NULL,
 reason TEXT NOT NULL,
 created_at TEXT NOT NULL,
 UNIQUE(brain_id, lesson_key)
);
CREATE INDEX IF NOT EXISTS ix_paper_lessons_brain_time ON paper_lessons(brain_id,created_at DESC);
