from __future__ import annotations
from datetime import datetime,timedelta,timezone

from v22.realtime.config import RealtimeConfig
from v22.realtime.engine import RealtimeMarketEngine
from v22.realtime.models import TradeEvent,ReferencePriceEvent,MinuteBar
from v22.realtime.repository import RealtimeRepository
from v22.storage import Database

UTC=timezone.utc

def cfg(**kw):
    base=dict(universe=("BTC",),kraken_enabled=True,provider_stale_seconds=10,asset_stale_seconds=10,
              event_window_seconds=60,price_move_event_pct=.4,flow_imbalance_event_share=.65,
              flow_event_min_trades=3,event_cooldown_seconds=60,decision_min_coverage_pct=95)
    base.update(kw);return RealtimeConfig(**base)

def trade(provider,asset,t,price,qty=1,side="BUY",tid="1"):
    return TradeEvent(provider,asset,t,t+timedelta(milliseconds=25),price,qty,side,tid)

def test_primary_stream_builds_causal_minute_bar_and_5m_state():
    e=RealtimeMarketEngine(cfg())
    start=datetime(2026,8,19,0,0,tzinfo=UTC)
    for minute in range(5):
        t=start+timedelta(minutes=minute,seconds=5)
        ev=trade("BINANCE","BTC",t,100+minute,1,"BUY",str(minute))
        closed,_,info=e.on_trade(ev)
        for b in closed:e.accept_closed_bar(b)
        bars,_=e.flush_due(start+timedelta(minutes=minute+1,seconds=1))
        for b in bars:e.accept_closed_bar(b)
    assert len(e.history["BTC"])==5
    states=e.derive_states("BTC",start+timedelta(minutes=5))
    five=next(s for s in states if s.timeframe=="5m")
    assert five.coverage_pct==100
    assert five.decision_eligible is True
    assert five.provenance=="LIVE_DERIVED"
    assert five.change_pct>0

def test_idle_minute_is_derived_only_when_live_reference_is_fresh():
    e=RealtimeMarketEngine(cfg())
    t=datetime(2026,8,19,0,0,30,tzinfo=UTC)
    e.on_reference(ReferencePriceEvent("BINANCE","BTC",t,t,100.0))
    bars,gaps=e.flush_due(datetime(2026,8,19,0,1,1,tzinfo=UTC))
    assert len(bars)==1 and not gaps
    assert bars[0].provenance=="LIVE_DERIVED_IDLE"
    assert bars[0].trades==0 and bars[0].decision_eligible

def test_stale_feed_creates_real_gap_not_fake_bar():
    e=RealtimeMarketEngine(cfg(asset_stale_seconds=5))
    old=datetime(2026,8,19,0,0,0,tzinfo=UTC)
    e.on_reference(ReferencePriceEvent("BINANCE","BTC",old,old,100.0))
    bars,gaps=e.flush_due(datetime(2026,8,19,0,2,1,tzinfo=UTC))
    assert not bars and gaps
    assert gaps[0]["reason"]=="NO_FRESH_LIVE_REFERENCE"
    assert e.expected_minutes["BTC"]==1 and e.live_minutes["BTC"]==0

def test_secondary_is_ignored_while_primary_fresh_then_fails_over_and_fails_back():
    e=RealtimeMarketEngine(cfg())
    t=datetime(2026,8,19,0,0,tzinfo=UTC)
    e.on_reference(ReferencePriceEvent("BINANCE","BTC",t,t,100))
    closed,sig,info=e.on_trade(trade("KRAKEN","BTC",t+timedelta(seconds=2),101,tid="k1"))
    assert not info["accepted"] and e.active_provider["BTC"]=="BINANCE"
    closed,sig,info=e.on_trade(trade("KRAKEN","BTC",t+timedelta(seconds=25),102,tid="k2"))
    assert info["accepted"] and e.active_provider["BTC"]=="KRAKEN" and e.failovers["BTC"]==1
    closed,sig,info=e.on_trade(trade("BINANCE","BTC",t+timedelta(seconds=26),103,tid="b1"))
    assert info["accepted"] and e.active_provider["BTC"]=="BINANCE"

def test_intraminute_objective_signal_fires_without_waiting_for_scheduler():
    e=RealtimeMarketEngine(cfg(price_move_event_pct=.4,flow_event_min_trades=99))
    t=datetime(2026,8,19,0,0,tzinfo=UTC)
    allsig=[]
    for i,p in enumerate([100,100.1,100.5]):
        _,sig,_=e.on_trade(trade("BINANCE","BTC",t+timedelta(seconds=i*10),p,tid=str(i)))
        allsig.extend(sig)
    assert any(s.event_type=="PRICE_MOVE_60S" for s in allsig)
    assert all(s.decision_eligible for s in allsig)

def test_sqlite_realtime_persistence_is_upsert_safe(tmp_path):
    db=Database(f"sqlite:///{tmp_path/'brain.db'}");db.migrate();repo=RealtimeRepository(db)
    t=datetime(2026,8,19,0,0,tzinfo=UTC);sid="00000000-0000-0000-0000-000000000013"
    repo.create_session(sid,"test","22.13","BINANCE","KRAKEN",("BTC",),t)
    bar=MinuteBar("BTC",t,"BINANCE","LIVE_STREAM",100,101,99,100.5,2,200,50,3,t,t+timedelta(seconds=40),20,True)
    repo.upsert_bar(bar);repo.upsert_bar(bar)
    rows=db.query("SELECT * FROM realtime_bars_1m")
    assert len(rows)==1 and rows[0]["provenance"]=="LIVE_STREAM"
    repo.heartbeat(sid,"LIVE",t,{"bars":1})
    assert db.query("SELECT status FROM realtime_runtime_sessions")[0]["status"]=="LIVE"

def test_midminute_provider_transition_is_not_decision_eligible():
    e=RealtimeMarketEngine(cfg())
    t=datetime(2026,8,19,0,0,tzinfo=UTC)
    e.on_reference(ReferencePriceEvent("BINANCE","BTC",t,t,100))
    e.on_trade(trade("BINANCE","BTC",t+timedelta(seconds=1),100,tid="b1"))
    # Force the primary stale, accept Kraken in the same minute.
    _,_,info=e.on_trade(trade("KRAKEN","BTC",t+timedelta(seconds=30),101,tid="k1"))
    assert info["accepted"]
    bars,_=e.flush_due(t+timedelta(minutes=1,seconds=1))
    assert bars[0].provenance=="LIVE_MULTI_PROVIDER_TRANSITION"
    assert bars[0].decision_eligible is False
