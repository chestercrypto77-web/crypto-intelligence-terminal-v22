from __future__ import annotations

from datetime import datetime, timezone
import json
import uuid

from v22.storage import Database
from v22.trading import PaperCompetitionEngine, RiskPolicy


def _seed_market_cycle(db: Database, *, direction="UP", volume="UP", participation="ELEVATED", structure="BREAKOUT", price=100.0):
    cid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    db.execute("""INSERT INTO brain_cycles(cycle_id,cycle_key,cycle_type,scheduled_at,started_at,completed_at,status,expected_assets,analysed_assets,provenance_json)
                  VALUES (?,?,?,?,?,?,?,?,?,?)""",
               (cid, str(uuid.uuid4()), "MARKET_15M", now, now, now, "COMPLETED", 1, 1, "{}"))
    eid = str(uuid.uuid4())
    db.execute("""INSERT INTO evidence_records(evidence_id,idempotency_key,cycle_id,asset_id,metric,value_json,unit,source,source_timestamp,retrieved_at,quality,metadata_json)
                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
               (eid, str(uuid.uuid4()), cid, "BTC", "price_usd", json.dumps(price), "USD", "TEST", now, now, "GOOD", "{}"))
    for metric, value in [
        ("multi_timeframe_direction", direction),
        ("volume_flow", volume),
        ("volume_participation", participation),
        ("market_structure", structure),
    ]:
        db.execute("""INSERT INTO observation_records(observation_id,idempotency_key,cycle_id,asset_id,metric,value_json,observed_at,calculation,quality,evidence_ids_json,metadata_json)
                      VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                   (str(uuid.uuid4()), str(uuid.uuid4()), cid, "BTC", metric, json.dumps(value), now, "test_v1", "GOOD", json.dumps([eid]), "{}"))
    return cid


def test_fresh_equal_wallets_and_small_probe(tmp_path, monkeypatch):
    db = Database(f"sqlite:///{tmp_path/'brain.db'}")
    db.migrate()
    _seed_market_cycle(db)
    engine = PaperCompetitionEngine(db)
    monkeypatch.setattr(engine, "_fx_aud_per_usd", lambda: 1.4)
    result = engine.run_once()
    brains = db.query("SELECT * FROM paper_brains ORDER BY name")
    assert result["brains"] == 4
    assert len(brains) == 4
    positions = db.query("SELECT * FROM paper_positions WHERE status='OPEN'")
    assert positions
    for brain in brains:
        # Even after a first probe, every brain retains far more than the mandatory 70% reserve.
        assert float(brain["cash_aud"]) >= 98_000
    for pos in positions:
        assert float(pos["cost_basis_aud"]) <= 1_500.01


def test_never_average_down_and_total_cap_is_conservative(tmp_path, monkeypatch):
    db = Database(f"sqlite:///{tmp_path/'brain.db'}")
    db.migrate()
    _seed_market_cycle(db, price=100.0)
    engine = PaperCompetitionEngine(db)
    monkeypatch.setattr(engine, "_fx_aud_per_usd", lambda: 1.0)
    engine.run_once()
    first_count = len(db.query("SELECT * FROM paper_trades WHERE side='BUY'"))
    _seed_market_cycle(db, price=99.0)  # same bullish labels, worse price
    engine.run_once()
    assert len(db.query("SELECT * FROM paper_trades WHERE side='BUY'")) == first_count
    for brain in db.query("SELECT * FROM paper_brains"):
        assert float(brain["cash_aud"]) >= 70_000


def test_hard_stop_closes_and_learning_cannot_exceed_baseline(tmp_path, monkeypatch):
    db = Database(f"sqlite:///{tmp_path/'brain.db'}")
    db.migrate()
    _seed_market_cycle(db, price=100.0)
    engine = PaperCompetitionEngine(db, RiskPolicy(learning_min_closed_trades=1))
    monkeypatch.setattr(engine, "_fx_aud_per_usd", lambda: 1.0)
    engine.run_once()
    _seed_market_cycle(db, price=94.0, direction="DOWN", volume="DOWN", participation="NORMAL", structure="BREAKDOWN")
    engine.run_once()
    assert not db.query("SELECT * FROM paper_positions WHERE status='OPEN'")
    brains = db.query("SELECT * FROM paper_brains")
    assert all(float(b["risk_multiplier"]) <= 1.0 for b in brains)
    assert all(int(b["trades_closed"]) >= 1 for b in brains if b["strategy_key"] in ("BALANCED","TREND","BREAKOUT","FLOW"))


def test_policy_rejects_unsafe_overlap():
    try:
        RiskPolicy(max_deployed_fraction=0.5, min_cash_reserve_fraction=0.7)
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe capital overlap must be rejected")


def test_same_cycle_retry_cannot_duplicate_trade(tmp_path, monkeypatch):
    db = Database(f"sqlite:///{tmp_path/'brain.db'}")
    db.migrate()
    _seed_market_cycle(db, price=100.0)
    engine = PaperCompetitionEngine(db)
    monkeypatch.setattr(engine, "_fx_aud_per_usd", lambda: 1.0)
    engine.run_once()
    before = len(db.query("SELECT * FROM paper_trades"))
    engine.run_once()
    assert len(db.query("SELECT * FROM paper_trades")) == before


def test_asset_can_be_reopened_after_closed_trade(tmp_path, monkeypatch):
    db = Database(f"sqlite:///{tmp_path/'brain.db'}")
    db.migrate()
    engine = PaperCompetitionEngine(db)
    monkeypatch.setattr(engine, "_fx_aud_per_usd", lambda: 1.0)
    _seed_market_cycle(db, price=100.0); engine.run_once()
    _seed_market_cycle(db, price=94.0, direction="DOWN", volume="DOWN", participation="NORMAL", structure="BREAKDOWN"); engine.run_once()
    assert not db.query("SELECT * FROM paper_positions WHERE status='OPEN'")
    _seed_market_cycle(db, price=96.0); engine.run_once()
    assert db.query("SELECT * FROM paper_positions WHERE status='OPEN'")
