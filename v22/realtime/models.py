from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

UTC=timezone.utc

def floor_minute(dt: datetime) -> datetime:
    return dt.astimezone(UTC).replace(second=0,microsecond=0)

@dataclass(frozen=True)
class TradeEvent:
    provider: str
    asset_id: str
    event_time: datetime
    received_at: datetime
    price: float
    quantity: float
    taker_side: str
    trade_id: str | None = None

    @property
    def quote_value(self) -> float:
        return self.price*self.quantity

    @property
    def signed_quote_value(self) -> float:
        return self.quote_value if self.taker_side.upper()=="BUY" else -self.quote_value

@dataclass(frozen=True)
class ReferencePriceEvent:
    provider: str
    asset_id: str
    event_time: datetime
    received_at: datetime
    price: float

@dataclass
class MutableMinuteBar:
    asset_id: str
    bucket_start: datetime
    provider: str
    provenance: str
    open: float
    high: float
    low: float
    close: float
    base_volume: float=0.0
    quote_volume: float=0.0
    signed_quote_volume: float=0.0
    trades: int=0
    first_event_at: datetime | None=None
    last_event_at: datetime | None=None
    latency_ms_total: float=0.0

    def add(self,event: TradeEvent) -> None:
        self.high=max(self.high,event.price); self.low=min(self.low,event.price); self.close=event.price
        self.base_volume += event.quantity; self.quote_volume += event.quote_value
        self.signed_quote_volume += event.signed_quote_value; self.trades += 1
        self.first_event_at=self.first_event_at or event.event_time; self.last_event_at=event.event_time
        self.latency_ms_total += max(0.0,(event.received_at-event.event_time).total_seconds()*1000.0)

    def freeze(self) -> "MinuteBar":
        return MinuteBar(
            asset_id=self.asset_id,bucket_start=self.bucket_start,provider=self.provider,provenance=self.provenance,
            open=self.open,high=self.high,low=self.low,close=self.close,base_volume=self.base_volume,
            quote_volume=self.quote_volume,signed_quote_volume=self.signed_quote_volume,trades=self.trades,
            first_event_at=self.first_event_at,last_event_at=self.last_event_at,
            source_latency_ms_avg=(self.latency_ms_total/self.trades if self.trades else None),
            decision_eligible=self.provenance in {"LIVE_STREAM","LIVE_DERIVED_IDLE","LIVE_FAILOVER"},
        )

@dataclass(frozen=True)
class MinuteBar:
    asset_id: str
    bucket_start: datetime
    provider: str
    provenance: str
    open: float
    high: float
    low: float
    close: float
    base_volume: float
    quote_volume: float
    signed_quote_volume: float
    trades: int
    first_event_at: datetime | None
    last_event_at: datetime | None
    source_latency_ms_avg: float | None
    decision_eligible: bool

@dataclass(frozen=True)
class TimeframeState:
    asset_id: str
    timeframe: str
    measured_at: datetime
    window_minutes: int
    change_pct: float
    quote_volume: float
    signed_quote_volume: float
    flow_share: float
    participation_ratio: float | None
    direction: str
    volume_flow: str
    coverage_pct: float
    provenance: str
    decision_eligible: bool
    metadata: dict[str,Any]

@dataclass(frozen=True)
class SignalEvent:
    asset_id: str
    event_type: str
    event_time: datetime
    provider: str
    provenance: str
    value: float
    threshold: float
    evidence: dict[str,Any]
    decision_eligible: bool=True
