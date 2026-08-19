from __future__ import annotations
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Iterable

from .config import RealtimeConfig
from .models import TradeEvent, ReferencePriceEvent, MutableMinuteBar, MinuteBar, TimeframeState, SignalEvent, floor_minute

UTC=timezone.utc
TIMEFRAMES={"1m":1,"5m":5,"15m":15,"1h":60,"4h":240}

class RealtimeMarketEngine:
    """Deterministic realtime aggregation with explicit provenance.

    No AI and no paper trading are invoked here. The engine's job is to retain
    causal live evidence with enough continuity metadata to decide later whether
    an observation was actually available in real time.
    """
    def __init__(self, config: RealtimeConfig):
        self.config=config
        self.current: dict[str,MutableMinuteBar]={}
        self.history: dict[str,deque[MinuteBar]]={a:deque(maxlen=520) for a in config.universe}
        self.reference_price: dict[str,float]={}
        self.reference_provider: dict[str,str]={}
        self.reference_time: dict[str,datetime]={}
        self.provider_last_message: dict[str,datetime]={}
        self.provider_max_message_gap: dict[str,float]=defaultdict(float)
        self.asset_provider_last_message: dict[tuple[str,str],datetime]={}
        self.asset_provider_max_message_gap: dict[tuple[str,str],float]=defaultdict(float)
        self.asset_last_trade: dict[str,datetime]={}
        self.active_provider: dict[str,str]={a:config.primary_provider for a in config.universe}
        self.failovers: dict[str,int]=defaultdict(int)
        self.max_gap_seconds: dict[str,float]=defaultdict(float)
        self.live_minutes: dict[str,int]=defaultdict(int)
        self.expected_minutes: dict[str,int]=defaultdict(int)
        self.last_closed_bucket: dict[str,datetime]={}
        self.rolling_trades: dict[str,deque[TradeEvent]]={a:deque() for a in config.universe}
        self.signal_cooldown: dict[tuple[str,str],datetime]={}
        self.late_events: int=0

    def prime(self,bars: Iterable[MinuteBar]) -> None:
        for bar in sorted(bars,key=lambda x:(x.asset_id,x.bucket_start)):
            if bar.asset_id not in self.history: continue
            self.history[bar.asset_id].append(bar)
            self.reference_price[bar.asset_id]=bar.close
            self.reference_provider[bar.asset_id]=bar.provider
            self.reference_time[bar.asset_id]=bar.bucket_start+timedelta(minutes=1)
            self.last_closed_bucket[bar.asset_id]=bar.bucket_start

    def note_provider_message(self,provider: str, when: datetime, asset: str | None=None) -> None:
        when=when.astimezone(UTC)
        prev=self.provider_last_message.get(provider)
        if prev:self.provider_max_message_gap[provider]=max(self.provider_max_message_gap[provider],(when-prev).total_seconds())
        self.provider_last_message[provider]=when
        if asset:
            key=(provider,asset);aprev=self.asset_provider_last_message.get(key)
            if aprev:self.asset_provider_max_message_gap[key]=max(self.asset_provider_max_message_gap[key],(when-aprev).total_seconds())
            self.asset_provider_last_message[key]=when

    def provider_fresh(self,provider: str, now: datetime) -> bool:
        seen=self.provider_last_message.get(provider)
        return bool(seen and (now-seen).total_seconds() <= self.config.provider_stale_seconds)

    def primary_asset_fresh(self,asset: str, now: datetime) -> bool:
        seen=self.asset_provider_last_message.get((self.config.primary_provider,asset))
        return bool(seen and (now-seen).total_seconds() <= self.config.asset_stale_seconds)

    def _accept_provider(self,asset: str,provider: str,now: datetime) -> tuple[bool,bool]:
        primary=self.config.primary_provider
        active=self.active_provider.get(asset,primary)
        if provider==primary:
            failback=active!=primary
            if failback:
                self.active_provider[asset]=primary
            return True,failback
        if provider!=self.config.secondary_provider:
            return False,False
        if self.primary_asset_fresh(asset,now) and self.provider_fresh(primary,now):
            return False,False
        if active!=provider:
            self.active_provider[asset]=provider
            self.failovers[asset]+=1
            return True,True
        return True,False

    def on_reference(self,event: ReferencePriceEvent) -> dict:
        self.note_provider_message(event.provider,event.received_at,event.asset_id)
        accept,changed=self._accept_provider(event.asset_id,event.provider,event.received_at)
        if accept:
            self.reference_price[event.asset_id]=event.price
            self.reference_provider[event.asset_id]=event.provider
            self.reference_time[event.asset_id]=event.event_time
        return {"accepted":accept,"provider_changed":changed,"active_provider":self.active_provider.get(event.asset_id)}

    def on_trade(self,event: TradeEvent) -> tuple[list[MinuteBar],list[SignalEvent],dict]:
        self.note_provider_message(event.provider,event.received_at,event.asset_id)
        accept,changed=self._accept_provider(event.asset_id,event.provider,event.received_at)
        if not accept:
            return [],[],{"accepted":False,"provider_changed":changed}
        self.reference_price[event.asset_id]=event.price
        self.reference_provider[event.asset_id]=event.provider
        self.reference_time[event.asset_id]=event.event_time
        self.asset_last_trade[event.asset_id]=event.event_time
        bucket=floor_minute(event.event_time)
        current=self.current.get(event.asset_id)
        closed=[]
        if current and bucket < current.bucket_start:
            self.late_events += 1
            return [],[],{"accepted":False,"late":True,"provider_changed":changed}
        if current and bucket > current.bucket_start:
            closed.append(current.freeze()); self.current.pop(event.asset_id,None)
            current=None
        if current is not None and current.provider != event.provider:
            # A failover/failback can occur mid-minute. Never pretend one exchange
            # produced a clean canonical bar if two providers contributed to it.
            # We retain the bar for continuity but mark the whole minute ineligible
            # for trading/learning decisions.
            current.provenance="LIVE_MULTI_PROVIDER_TRANSITION"
        if current is None:
            provenance="LIVE_STREAM" if event.provider==self.config.primary_provider else "LIVE_FAILOVER"
            current=MutableMinuteBar(
                asset_id=event.asset_id,bucket_start=bucket,provider=event.provider,provenance=provenance,
                open=event.price,high=event.price,low=event.price,close=event.price,
            )
            self.current[event.asset_id]=current
        current.add(event)
        signals=self._realtime_signals(event)
        return closed,signals,{"accepted":True,"provider_changed":changed,"active_provider":event.provider}

    def _realtime_signals(self,event: TradeEvent) -> list[SignalEvent]:
        dq=self.rolling_trades[event.asset_id]; dq.append(event)
        cutoff=event.received_at-timedelta(seconds=self.config.event_window_seconds)
        while dq and dq[0].received_at < cutoff: dq.popleft()
        if len(dq)<2:return []
        result=[]; first=dq[0]; last=dq[-1]
        change=((last.price/first.price)-1.0)*100.0 if first.price else 0.0
        total=sum(x.quote_value for x in dq); signed=sum(x.signed_quote_value for x in dq)
        flow=(signed/total) if total else 0.0
        now=event.received_at
        def ready(kind: str)->bool:
            prev=self.signal_cooldown.get((event.asset_id,kind))
            return prev is None or (now-prev).total_seconds() >= self.config.event_cooldown_seconds
        if abs(change)>=self.config.price_move_event_pct and ready("PRICE_MOVE_60S"):
            self.signal_cooldown[(event.asset_id,"PRICE_MOVE_60S")]=now
            result.append(SignalEvent(event.asset_id,"PRICE_MOVE_60S",event.event_time,event.provider,
                "LIVE_STREAM" if event.provider==self.config.primary_provider else "LIVE_FAILOVER",
                change,self.config.price_move_event_pct,
                {"window_seconds":self.config.event_window_seconds,"trades":len(dq),"start_price":first.price,"last_price":last.price}))
        if len(dq)>=self.config.flow_event_min_trades and abs(flow)>=self.config.flow_imbalance_event_share and ready("FLOW_IMBALANCE_60S"):
            self.signal_cooldown[(event.asset_id,"FLOW_IMBALANCE_60S")]=now
            result.append(SignalEvent(event.asset_id,"FLOW_IMBALANCE_60S",event.event_time,event.provider,
                "LIVE_STREAM" if event.provider==self.config.primary_provider else "LIVE_FAILOVER",
                flow,self.config.flow_imbalance_event_share,
                {"window_seconds":self.config.event_window_seconds,"trades":len(dq),"quote_volume":total,"signed_quote_volume":signed}))
        return result

    def flush_due(self,now: datetime) -> tuple[list[MinuteBar],list[dict]]:
        """Close bars once wall clock moves to the next minute.

        A minute with no trades can still be represented as LIVE_DERIVED_IDLE if
        an asset-specific live reference stream stayed fresh. If the feed itself
        was stale we leave a real hole and report a gap rather than fabricate data.
        """
        now=now.astimezone(UTC); current_bucket=floor_minute(now)
        closed=[]; gaps=[]
        for asset in self.config.universe:
            cur=self.current.get(asset)
            if cur and cur.bucket_start < current_bucket:
                closed.append(cur.freeze()); self.current.pop(asset,None)
                continue
            last=self.last_closed_bucket.get(asset)
            target=(last+timedelta(minutes=1)) if last else (current_bucket-timedelta(minutes=1))
            # Don't emit current minute; only fully elapsed minute buckets.
            if target >= current_bucket:
                continue
            price=self.reference_price.get(asset)
            ref_time=self.reference_time.get(asset)
            active=self.active_provider.get(asset,self.config.primary_provider)
            ref_fresh=bool(price and ref_time and (now-ref_time).total_seconds() <= max(70.0,self.config.asset_stale_seconds))
            if ref_fresh:
                prov="LIVE_DERIVED_IDLE" if active==self.config.primary_provider else "LIVE_FAILOVER"
                closed.append(MinuteBar(asset,target,active,prov,price,price,price,price,0.0,0.0,0.0,0,None,None,None,True))
            else:
                self.expected_minutes[asset]+=1
                gap_start=target; gap_end=target+timedelta(minutes=1)
                duration=60.0
                self.max_gap_seconds[asset]=max(self.max_gap_seconds[asset],duration)
                gaps.append({"asset_id":asset,"provider":active,"gap_start":gap_start,"gap_end":gap_end,
                    "duration_seconds":duration,"reason":"NO_FRESH_LIVE_REFERENCE","recovered_by":None})
                self.last_closed_bucket[asset]=target
        return closed,gaps

    def accept_closed_bar(self,bar: MinuteBar) -> list[TimeframeState]:
        hist=self.history[bar.asset_id]
        is_new_bucket = not hist or hist[-1].bucket_start < bar.bucket_start
        # Upsert/retry safety in memory.
        if hist and hist[-1].bucket_start==bar.bucket_start:
            hist[-1]=bar
        elif not hist or hist[-1].bucket_start < bar.bucket_start:
            hist.append(bar)
        self.last_closed_bucket[bar.asset_id]=bar.bucket_start
        if is_new_bucket:
            self.expected_minutes[bar.asset_id]+=1
            self.live_minutes[bar.asset_id]+=1
        if len(hist)>=2:
            gap=(hist[-1].bucket_start-hist[-2].bucket_start).total_seconds()-60.0
            if gap>0:self.max_gap_seconds[bar.asset_id]=max(self.max_gap_seconds[bar.asset_id],gap)
        return self.derive_states(bar.asset_id,bar.bucket_start+timedelta(minutes=1))

    def derive_states(self,asset: str,measured_at: datetime) -> list[TimeframeState]:
        bars=list(self.history[asset]); result=[]
        for tf,minutes in TIMEFRAMES.items():
            if not bars:continue
            start=measured_at-timedelta(minutes=minutes)
            window=[b for b in bars if start <= b.bucket_start < measured_at]
            expected=minutes; coverage=100.0*len(window)/expected
            if not window:continue
            first=window[0]; last=window[-1]
            change=((last.close/first.open)-1.0)*100.0 if first.open else 0.0
            qv=sum(b.quote_volume for b in window); sv=sum(b.signed_quote_volume for b in window)
            flow_share=(sv/qv) if qv else 0.0
            prev_start=start-timedelta(minutes=minutes)
            prev=[b for b in bars if prev_start <= b.bucket_start < start]
            prev_qv=sum(b.quote_volume for b in prev)
            participation=(qv/prev_qv) if prev_qv>0 else None
            direction="UP" if change>0.05 else ("DOWN" if change < -0.05 else "FLAT")
            volume_flow="UP" if flow_share>0.05 else ("DOWN" if flow_share < -0.05 else "BALANCED")
            live_only=all(b.decision_eligible and b.provenance.startswith("LIVE") for b in window)
            contiguous=(len(window)==expected and all(
                (window[i].bucket_start-window[i-1].bucket_start).total_seconds()==60 for i in range(1,len(window))
            ))
            eligible=live_only and contiguous and coverage>=self.config.decision_min_coverage_pct
            provenance="LIVE_DERIVED" if live_only else "MIXED_OR_BACKFILLED"
            result.append(TimeframeState(asset,tf,measured_at,minutes,change,qv,sv,flow_share,participation,
                direction,volume_flow,coverage,provenance,eligible,
                {"bars":len(window),"expected_bars":expected,"contiguous":contiguous,"last_provider":last.provider}))
        return result

    def coverage_pct(self,asset: str) -> float:
        expected=max(1,self.expected_minutes[asset])
        return min(100.0,100.0*self.live_minutes[asset]/expected)
