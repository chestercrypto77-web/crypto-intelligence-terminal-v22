from __future__ import annotations
from datetime import datetime, timezone
import json, uuid
from typing import Any, Iterable

from v22.storage import Database
from .models import MinuteBar, TimeframeState, SignalEvent

UTC=timezone.utc

def _iso(v: datetime | None) -> str | None:
    return v.astimezone(UTC).isoformat() if v else None

def _json(v: Any) -> str:
    return json.dumps(v,sort_keys=True,separators=(",",":"))

class RealtimeRepository:
    def __init__(self,db: Database):
        self.db=db
    @property
    def ph(self): return "?" if self.db.kind=="sqlite" else "%s"
    def _sql(self,sqlite_sql,postgres_sql): return sqlite_sql if self.db.kind=="sqlite" else postgres_sql
    def _bool(self,v: bool): return 1 if self.db.kind=="sqlite" and v else v

    def create_session(self,session_id: str,instance_id: str,version: str,primary: str,secondary: str|None,universe: Iterable[str],started_at: datetime):
        sql=self._sql(
            "INSERT INTO realtime_runtime_sessions(session_id,instance_id,version,status,primary_provider,secondary_provider,universe_json,started_at,last_heartbeat_at,metrics_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
            "INSERT INTO realtime_runtime_sessions(session_id,instance_id,version,status,primary_provider,secondary_provider,universe_json,started_at,last_heartbeat_at,metrics_json) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s::jsonb)")
        self.db.execute(sql,(session_id,instance_id,version,"STARTING",primary,secondary,_json(list(universe)),_iso(started_at),_iso(started_at),"{}"))

    def heartbeat(self,session_id: str,status: str,when: datetime,metrics: dict[str,Any]):
        sql=self._sql(
            "UPDATE realtime_runtime_sessions SET status=?,last_heartbeat_at=?,metrics_json=? WHERE session_id=?",
            "UPDATE realtime_runtime_sessions SET status=%s,last_heartbeat_at=%s,metrics_json=%s::jsonb WHERE session_id=%s")
        self.db.execute(sql,(status,_iso(when),_json(metrics),session_id))

    def stop_session(self,session_id: str,when: datetime,reason: str):
        sql=self._sql("UPDATE realtime_runtime_sessions SET status='STOPPED',stopped_at=?,stop_reason=?,last_heartbeat_at=? WHERE session_id=?",
                      "UPDATE realtime_runtime_sessions SET status='STOPPED',stopped_at=%s,stop_reason=%s,last_heartbeat_at=%s WHERE session_id=%s")
        self.db.execute(sql,(_iso(when),reason,_iso(when),session_id))

    def upsert_provider_health(self,session_id: str,provider: str,state: dict[str,Any],when: datetime):
        values=(session_id,provider,state.get("status","UNKNOWN"),_iso(state.get("connected_at")),_iso(state.get("last_message_at")),
                _iso(state.get("last_event_at")),int(state.get("reconnects",0)),int(state.get("scheduled_reconnects",0)),
                int(state.get("messages",0)),float(state.get("max_message_gap_seconds",0)),int(state.get("errors",0)),state.get("last_error"),_iso(when))
        sql=self._sql(
            "INSERT INTO realtime_provider_health(session_id,provider,status,connected_at,last_message_at,last_event_at,reconnects,scheduled_reconnects,messages,max_message_gap_seconds,errors,last_error,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(session_id,provider) DO UPDATE SET status=excluded.status,connected_at=excluded.connected_at,last_message_at=excluded.last_message_at,last_event_at=excluded.last_event_at,reconnects=excluded.reconnects,scheduled_reconnects=excluded.scheduled_reconnects,messages=excluded.messages,max_message_gap_seconds=excluded.max_message_gap_seconds,errors=excluded.errors,last_error=excluded.last_error,updated_at=excluded.updated_at",
            "INSERT INTO realtime_provider_health(session_id,provider,status,connected_at,last_message_at,last_event_at,reconnects,scheduled_reconnects,messages,max_message_gap_seconds,errors,last_error,updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(session_id,provider) DO UPDATE SET status=EXCLUDED.status,connected_at=EXCLUDED.connected_at,last_message_at=EXCLUDED.last_message_at,last_event_at=EXCLUDED.last_event_at,reconnects=EXCLUDED.reconnects,scheduled_reconnects=EXCLUDED.scheduled_reconnects,messages=EXCLUDED.messages,max_message_gap_seconds=EXCLUDED.max_message_gap_seconds,errors=EXCLUDED.errors,last_error=EXCLUDED.last_error,updated_at=EXCLUDED.updated_at")
        self.db.execute(sql,values)

    def upsert_asset_health(self,session_id: str,asset: str,state: dict[str,Any],when: datetime):
        vals=(session_id,asset,state.get("active_provider"),_iso(state.get("primary_last_message_at")),_iso(state.get("secondary_last_message_at")),
              _iso(state.get("last_trade_at")),_iso(state.get("last_bar_close_at")),int(state.get("expected_minutes",0)),int(state.get("live_minutes",0)),
              float(state.get("coverage_pct",0)),float(state.get("max_message_gap_seconds",0)),float(state.get("max_gap_seconds",0)),int(state.get("failovers",0)),state.get("status","UNKNOWN"),_iso(when))
        sql=self._sql(
            "INSERT INTO realtime_asset_health(session_id,asset_id,active_provider,primary_last_message_at,secondary_last_message_at,last_trade_at,last_bar_close_at,expected_minutes,live_minutes,coverage_pct,max_message_gap_seconds,max_gap_seconds,failovers,status,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(session_id,asset_id) DO UPDATE SET active_provider=excluded.active_provider,primary_last_message_at=excluded.primary_last_message_at,secondary_last_message_at=excluded.secondary_last_message_at,last_trade_at=excluded.last_trade_at,last_bar_close_at=excluded.last_bar_close_at,expected_minutes=excluded.expected_minutes,live_minutes=excluded.live_minutes,coverage_pct=excluded.coverage_pct,max_message_gap_seconds=excluded.max_message_gap_seconds,max_gap_seconds=excluded.max_gap_seconds,failovers=excluded.failovers,status=excluded.status,updated_at=excluded.updated_at",
            "INSERT INTO realtime_asset_health(session_id,asset_id,active_provider,primary_last_message_at,secondary_last_message_at,last_trade_at,last_bar_close_at,expected_minutes,live_minutes,coverage_pct,max_message_gap_seconds,max_gap_seconds,failovers,status,updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(session_id,asset_id) DO UPDATE SET active_provider=EXCLUDED.active_provider,primary_last_message_at=EXCLUDED.primary_last_message_at,secondary_last_message_at=EXCLUDED.secondary_last_message_at,last_trade_at=EXCLUDED.last_trade_at,last_bar_close_at=EXCLUDED.last_bar_close_at,expected_minutes=EXCLUDED.expected_minutes,live_minutes=EXCLUDED.live_minutes,coverage_pct=EXCLUDED.coverage_pct,max_message_gap_seconds=EXCLUDED.max_message_gap_seconds,max_gap_seconds=EXCLUDED.max_gap_seconds,failovers=EXCLUDED.failovers,status=EXCLUDED.status,updated_at=EXCLUDED.updated_at")
        self.db.execute(sql,vals)

    def upsert_bar(self,bar: MinuteBar):
        vals=(bar.asset_id,_iso(bar.bucket_start),bar.provider,bar.provenance,self._bool(bar.decision_eligible),bar.open,bar.high,bar.low,bar.close,
              bar.base_volume,bar.quote_volume,bar.signed_quote_volume,bar.trades,_iso(bar.first_event_at),_iso(bar.last_event_at),bar.source_latency_ms_avg)
        sql=self._sql(
            "INSERT INTO realtime_bars_1m(asset_id,bucket_start,provider,provenance,decision_eligible,open,high,low,close,base_volume,quote_volume,signed_quote_volume,trades,first_event_at,last_event_at,source_latency_ms_avg) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(asset_id,bucket_start) DO UPDATE SET provider=excluded.provider,provenance=excluded.provenance,decision_eligible=excluded.decision_eligible,open=excluded.open,high=excluded.high,low=excluded.low,close=excluded.close,base_volume=excluded.base_volume,quote_volume=excluded.quote_volume,signed_quote_volume=excluded.signed_quote_volume,trades=excluded.trades,first_event_at=excluded.first_event_at,last_event_at=excluded.last_event_at,source_latency_ms_avg=excluded.source_latency_ms_avg",
            "INSERT INTO realtime_bars_1m(asset_id,bucket_start,provider,provenance,decision_eligible,open,high,low,close,base_volume,quote_volume,signed_quote_volume,trades,first_event_at,last_event_at,source_latency_ms_avg) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(asset_id,bucket_start) DO UPDATE SET provider=EXCLUDED.provider,provenance=EXCLUDED.provenance,decision_eligible=EXCLUDED.decision_eligible,open=EXCLUDED.open,high=EXCLUDED.high,low=EXCLUDED.low,close=EXCLUDED.close,base_volume=EXCLUDED.base_volume,quote_volume=EXCLUDED.quote_volume,signed_quote_volume=EXCLUDED.signed_quote_volume,trades=EXCLUDED.trades,first_event_at=EXCLUDED.first_event_at,last_event_at=EXCLUDED.last_event_at,source_latency_ms_avg=EXCLUDED.source_latency_ms_avg")
        self.db.execute(sql,vals)

    def upsert_state(self,s: TimeframeState):
        vals=(s.asset_id,s.timeframe,_iso(s.measured_at),s.window_minutes,s.change_pct,s.quote_volume,s.signed_quote_volume,s.flow_share,
              s.participation_ratio,s.direction,s.volume_flow,s.coverage_pct,s.provenance,self._bool(s.decision_eligible),_json(s.metadata))
        sql=self._sql(
            "INSERT INTO realtime_timeframe_state(asset_id,timeframe,measured_at,window_minutes,change_pct,quote_volume,signed_quote_volume,flow_share,participation_ratio,direction,volume_flow,coverage_pct,provenance,decision_eligible,metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(asset_id,timeframe,measured_at) DO UPDATE SET change_pct=excluded.change_pct,quote_volume=excluded.quote_volume,signed_quote_volume=excluded.signed_quote_volume,flow_share=excluded.flow_share,participation_ratio=excluded.participation_ratio,direction=excluded.direction,volume_flow=excluded.volume_flow,coverage_pct=excluded.coverage_pct,provenance=excluded.provenance,decision_eligible=excluded.decision_eligible,metadata_json=excluded.metadata_json",
            "INSERT INTO realtime_timeframe_state(asset_id,timeframe,measured_at,window_minutes,change_pct,quote_volume,signed_quote_volume,flow_share,participation_ratio,direction,volume_flow,coverage_pct,provenance,decision_eligible,metadata_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT(asset_id,timeframe,measured_at) DO UPDATE SET change_pct=EXCLUDED.change_pct,quote_volume=EXCLUDED.quote_volume,signed_quote_volume=EXCLUDED.signed_quote_volume,flow_share=EXCLUDED.flow_share,participation_ratio=EXCLUDED.participation_ratio,direction=EXCLUDED.direction,volume_flow=EXCLUDED.volume_flow,coverage_pct=EXCLUDED.coverage_pct,provenance=EXCLUDED.provenance,decision_eligible=EXCLUDED.decision_eligible,metadata_json=EXCLUDED.metadata_json")
        self.db.execute(sql,vals)

    def insert_signal(self,session_id: str,s: SignalEvent):
        sql=self._sql(
            "INSERT INTO realtime_signal_events(event_id,session_id,asset_id,event_type,event_time,provider,provenance,decision_eligible,value,threshold,evidence_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            "INSERT INTO realtime_signal_events(event_id,session_id,asset_id,event_type,event_time,provider,provenance,decision_eligible,value,threshold,evidence_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)")
        self.db.execute(sql,(str(uuid.uuid4()),session_id,s.asset_id,s.event_type,_iso(s.event_time),s.provider,s.provenance,self._bool(s.decision_eligible),s.value,s.threshold,_json(s.evidence)))

    def insert_gap(self,session_id: str,gap: dict[str,Any]):
        sql=self._sql(
            "INSERT INTO realtime_gap_events(gap_id,session_id,asset_id,provider,gap_start,gap_end,duration_seconds,reason,recovered_by,decision_eligible) VALUES (?,?,?,?,?,?,?,?,?,?)",
            "INSERT INTO realtime_gap_events(gap_id,session_id,asset_id,provider,gap_start,gap_end,duration_seconds,reason,recovered_by,decision_eligible) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)")
        self.db.execute(sql,(str(uuid.uuid4()),session_id,gap.get("asset_id"),gap.get("provider"),_iso(gap["gap_start"]),_iso(gap.get("gap_end")),gap.get("duration_seconds"),gap["reason"],gap.get("recovered_by"),self._bool(False)))

    def load_recent_bars(self,assets: Iterable[str],limit_per_asset: int=300) -> list[MinuteBar]:
        result=[]; ph=self.ph
        for asset in assets:
            rows=self.db.query(f"SELECT * FROM realtime_bars_1m WHERE asset_id={ph} ORDER BY bucket_start DESC LIMIT {int(limit_per_asset)}",(asset,))
            for r in reversed(rows):
                def dt(v): return datetime.fromisoformat(str(v).replace("Z","+00:00")) if v else None
                result.append(MinuteBar(asset_id=r["asset_id"],bucket_start=dt(r["bucket_start"]),provider=r["provider"],provenance=r["provenance"],
                    open=float(r["open"]),high=float(r["high"]),low=float(r["low"]),close=float(r["close"]),base_volume=float(r["base_volume"]),
                    quote_volume=float(r["quote_volume"]),signed_quote_volume=float(r["signed_quote_volume"]),trades=int(r["trades"]),
                    first_event_at=dt(r.get("first_event_at")),last_event_at=dt(r.get("last_event_at")),source_latency_ms_avg=r.get("source_latency_ms_avg"),decision_eligible=bool(r["decision_eligible"])))
        return result
