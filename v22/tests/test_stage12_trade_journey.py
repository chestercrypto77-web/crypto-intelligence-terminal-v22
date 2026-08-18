from __future__ import annotations
from datetime import datetime, timezone
import json, uuid
from v22.storage import Database
from v22.trading import PaperCompetitionEngine, RiskPolicy

def _seed(db, price=100.0, direction="UP", volume="UP", participation="ELEVATED", structure="BREAKOUT"):
    cid=str(uuid.uuid4()); now=datetime.now(timezone.utc).isoformat()
    db.execute("""INSERT INTO brain_cycles(cycle_id,cycle_key,cycle_type,scheduled_at,started_at,completed_at,status,expected_assets,analysed_assets,provenance_json)
                  VALUES (?,?,?,?,?,?,?,?,?,?)""",(cid,str(uuid.uuid4()),"MARKET_15M",now,now,now,"COMPLETED",1,1,"{}"))
    eid=str(uuid.uuid4())
    db.execute("""INSERT INTO evidence_records(evidence_id,idempotency_key,cycle_id,asset_id,metric,value_json,unit,source,source_timestamp,retrieved_at,quality,metadata_json)
                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",(eid,str(uuid.uuid4()),cid,"BTC","price_usd",json.dumps(price),"USD","TEST",now,now,"GOOD","{}"))
    for metric,value in [("multi_timeframe_direction",direction),("volume_flow",volume),("volume_participation",participation),("market_structure",structure)]:
        db.execute("""INSERT INTO observation_records(observation_id,idempotency_key,cycle_id,asset_id,metric,value_json,observed_at,calculation,quality,evidence_ids_json,metadata_json)
                      VALUES (?,?,?,?,?,?,?,?,?,?,?)""",(str(uuid.uuid4()),str(uuid.uuid4()),cid,"BTC",metric,json.dumps(value),now,"test","GOOD",json.dumps([eid]),"{}"))
    return cid

def test_trade_journey_records_marks_and_outcome(tmp_path, monkeypatch):
    db=Database(f"sqlite:///{tmp_path/'brain.db'}"); db.migrate()
    engine=PaperCompetitionEngine(db, RiskPolicy(learning_min_closed_trades=1))
    monkeypatch.setattr(engine,"_fx_aud_per_usd",lambda:1.0)
    _seed(db,100); engine.run_once()
    _seed(db,103); engine.run_once()
    assert db.query("SELECT * FROM paper_position_marks")
    _seed(db,94,direction="DOWN",volume="DOWN",participation="NORMAL",structure="BREAKDOWN"); engine.run_once()
    outcomes=db.query("SELECT * FROM paper_trade_outcomes")
    assert outcomes
    assert float(outcomes[0]["max_favourable_pct"]) >= 2.9
    assert float(outcomes[0]["max_adverse_pct"]) <= -5.9
    assert float(outcomes[0]["return_pct"]) < 0

def test_position_marks_are_idempotent_by_cycle(tmp_path, monkeypatch):
    db=Database(f"sqlite:///{tmp_path/'brain.db'}"); db.migrate()
    engine=PaperCompetitionEngine(db); monkeypatch.setattr(engine,"_fx_aud_per_usd",lambda:1.0)
    _seed(db,100); engine.run_once()
    cid=_seed(db,101); engine.run_once(); engine.run_once()
    marks=db.query("SELECT * FROM paper_position_marks WHERE cycle_id=?",(cid,))
    ids=[m["position_id"] for m in marks]
    assert len(ids)==len(set(ids))
