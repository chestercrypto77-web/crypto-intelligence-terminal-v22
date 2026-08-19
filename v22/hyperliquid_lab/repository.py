from __future__ import annotations
import json,uuid
from datetime import datetime
from typing import Any
from .models import BookState,TradeFlow,LabSignal

def iso(v): return v.isoformat() if isinstance(v,datetime) else v
def js(v): return json.dumps(v,separators=(",",":"),default=str)

class HyperliquidLabRepository:
    def __init__(self,db): self.db=db; self.pg=db.is_postgres
    def sql(self,sq,pg): return pg if self.pg else sq
    def bool(self,v): return bool(v) if self.pg else int(bool(v))

    def create_session(self,sid,started,universe):
        q=self.sql("INSERT INTO hl_lab_sessions(session_id,status,started_at,last_heartbeat_at,universe_json,execution_mode) VALUES (?,?,?,?,?,?)",
                   "INSERT INTO hl_lab_sessions(session_id,status,started_at,last_heartbeat_at,universe_json,execution_mode) VALUES (%s,%s,%s,%s,%s::jsonb,%s)")
        self.db.execute(q,(sid,"LIVE",iso(started),iso(started),js(universe),"DISABLED"))

    def heartbeat(self,sid,when,metrics):
        q=self.sql("UPDATE hl_lab_sessions SET last_heartbeat_at=?,metrics_json=? WHERE session_id=?",
                   "UPDATE hl_lab_sessions SET last_heartbeat_at=%s,metrics_json=%s::jsonb WHERE session_id=%s")
        self.db.execute(q,(iso(when),js(metrics),sid))

    def provider(self,sid,state,when):
        vals=(sid,state["provider"],state["status"],iso(state.get("connected_at")),iso(state.get("last_message_at")),
              state["messages"],state["reconnects"],state["errors"],state["max_gap_seconds"],state.get("last_error"),iso(when))
        q=self.sql("""INSERT INTO hl_lab_provider_health(session_id,provider,status,connected_at,last_message_at,messages,reconnects,errors,max_gap_seconds,last_error,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(session_id,provider) DO UPDATE SET status=excluded.status,connected_at=excluded.connected_at,last_message_at=excluded.last_message_at,messages=excluded.messages,reconnects=excluded.reconnects,errors=excluded.errors,max_gap_seconds=excluded.max_gap_seconds,last_error=excluded.last_error,updated_at=excluded.updated_at""",
        """INSERT INTO hl_lab_provider_health(session_id,provider,status,connected_at,last_message_at,messages,reconnects,errors,max_gap_seconds,last_error,updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(session_id,provider) DO UPDATE SET status=EXCLUDED.status,connected_at=EXCLUDED.connected_at,last_message_at=EXCLUDED.last_message_at,messages=EXCLUDED.messages,reconnects=EXCLUDED.reconnects,errors=EXCLUDED.errors,max_gap_seconds=EXCLUDED.max_gap_seconds,last_error=EXCLUDED.last_error,updated_at=EXCLUDED.updated_at""")
        self.db.execute(q,vals)

    def trade(self,sid,t:TradeFlow):
        q=self.sql("INSERT OR IGNORE INTO hl_lab_trades(event_id,session_id,asset_id,event_time,received_at,price,size,side,trade_id) VALUES (?,?,?,?,?,?,?,?,?)",
                   "INSERT INTO hl_lab_trades(event_id,session_id,asset_id,event_time,received_at,price,size,side,trade_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(asset_id,event_time,trade_id) DO NOTHING")
        self.db.execute(q,(str(uuid.uuid4()),sid,t.asset_id,iso(t.event_time),iso(t.received_at),t.price,t.size,t.side,t.trade_id))

    def book(self,sid,b:BookState):
        q=self.sql("INSERT INTO hl_lab_books(snapshot_id,session_id,asset_id,event_time,received_at,best_bid,best_ask,spread_bps,bid_depth,ask_depth,imbalance) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   "INSERT INTO hl_lab_books(snapshot_id,session_id,asset_id,event_time,received_at,best_bid,best_ask,spread_bps,bid_depth,ask_depth,imbalance) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)")
        self.db.execute(q,(str(uuid.uuid4()),sid,b.asset_id,iso(b.event_time),iso(b.received_at),b.best_bid,b.best_ask,b.spread_bps,b.bid_depth,b.ask_depth,b.imbalance))

    def signal(self,sid,s:LabSignal):
        q=self.sql("INSERT INTO hl_lab_signals(signal_id,session_id,asset_id,event_time,signal_type,direction,price,spread_bps,book_imbalance,buy_flow_share,evidence_json,execution_eligible) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   "INSERT INTO hl_lab_signals(signal_id,session_id,asset_id,event_time,signal_type,direction,price,spread_bps,book_imbalance,buy_flow_share,evidence_json,execution_eligible) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)")
        self.db.execute(q,(str(uuid.uuid4()),sid,s.asset_id,iso(s.event_time),s.signal_type,s.direction,s.price,s.spread_bps,s.book_imbalance,s.buy_flow_share,js(s.evidence),self.bool(False)))
