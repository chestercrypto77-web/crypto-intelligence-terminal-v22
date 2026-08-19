from __future__ import annotations
import asyncio, json, random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable, Any

import websockets

from .config import RealtimeConfig
from .models import TradeEvent, ReferencePriceEvent

UTC=timezone.utc
TradeCallback=Callable[[TradeEvent],Awaitable[None]]
ReferenceCallback=Callable[[ReferencePriceEvent],Awaitable[None]]
MessageCallback=Callable[[str,datetime,str|None],Awaitable[None]]

@dataclass
class ProviderStats:
    provider: str
    status: str="STARTING"
    connected_at: datetime|None=None
    last_message_at: datetime|None=None
    last_event_at: datetime|None=None
    reconnects: int=0
    scheduled_reconnects: int=0
    messages: int=0
    max_message_gap_seconds: float=0.0
    errors: int=0
    last_error: str|None=None

    def as_dict(self) -> dict[str,Any]:
        return self.__dict__.copy()

class BinanceProvider:
    NAME="BINANCE"
    BASE_PATH="/stream?streams="
    def __init__(self,config: RealtimeConfig,on_trade: TradeCallback,on_reference: ReferenceCallback,on_message: MessageCallback):
        self.config=config; self.on_trade=on_trade; self.on_reference=on_reference; self.on_message=on_message
        self.stats=ProviderStats(self.NAME); self._stop=False; self._seen_trade_ids={}
        self.symbol_to_asset={config.binance_symbol(a):a for a in config.universe if config.binance_symbol(a)}

    @property
    def url(self) -> str:
        streams=[]
        for sym in self.symbol_to_asset:
            streams += [f"{sym}@aggTrade",f"{sym}@miniTicker"]
        return self.config.binance_ws_base+self.BASE_PATH+"/".join(streams)

    async def stop(self): self._stop=True

    async def run(self):
        backoff=1.0; first=True
        while not self._stop:
            try:
                if not first:self.stats.reconnects+=1
                first=False; self.stats.status="CONNECTING"
                async with websockets.connect(self.url,ping_interval=None,close_timeout=5,max_queue=4096) as ws:
                    now=datetime.now(UTC); self.stats.status="CONNECTED";self.stats.connected_at=now;self.stats.last_error=None
                    backoff=1.0
                    try:
                        async with asyncio.timeout(self.config.scheduled_reconnect_seconds):
                            while not self._stop:
                                raw=await asyncio.wait_for(ws.recv(),timeout=max(30.0,self.config.health_stale_seconds))
                                await self._handle(raw)
                    except TimeoutError:
                        # Either the planned 23h45 rotation fired or the socket
                        # stopped delivering messages. Both cases require a fresh
                        # connection; only healthy long-lived connections count as
                        # scheduled rotations.
                        age=(datetime.now(UTC)-self.stats.connected_at).total_seconds() if self.stats.connected_at else 0
                        if age >= self.config.scheduled_reconnect_seconds-5:
                            self.stats.scheduled_reconnects+=1;self.stats.status="ROTATING"
                        else:
                            raise RuntimeError(f"Binance feed silent for {max(30.0,self.config.health_stale_seconds):.0f}s")
            except asyncio.CancelledError: raise
            except Exception as exc:
                self.stats.errors+=1;self.stats.last_error=f"{type(exc).__name__}: {exc}";self.stats.status="DISCONNECTED"
                await asyncio.sleep(backoff+random.random()*0.5);backoff=min(30.0,backoff*2.0)
        self.stats.status="STOPPED"

    async def _handle(self,raw):
        now=datetime.now(UTC); self.stats.messages+=1
        if self.stats.last_message_at:
            self.stats.max_message_gap_seconds=max(self.stats.max_message_gap_seconds,(now-self.stats.last_message_at).total_seconds())
        self.stats.last_message_at=now
        payload=json.loads(raw); data=payload.get("data",payload)
        event_type=data.get("e")
        symbol=str(data.get("s") or "").lower();asset=self.symbol_to_asset.get(symbol)
        await self.on_message(self.NAME,now,asset)
        if event_type=="serverShutdown":
            raise RuntimeError("Binance serverShutdown")
        if not asset:return
        if event_type=="aggTrade":
            trade_id=str(data.get("a"))
            key=(asset,trade_id)
            if self._seen_trade_ids.get(asset)==trade_id:return
            self._seen_trade_ids[asset]=trade_id
            event_ms=int(data.get("T") or data.get("E"));event_time=datetime.fromtimestamp(event_ms/1000.0,UTC)
            side="SELL" if bool(data.get("m")) else "BUY"
            ev=TradeEvent(self.NAME,asset,event_time,now,float(data["p"]),float(data["q"]),side,trade_id)
            self.stats.last_event_at=event_time;await self.on_trade(ev)
        elif event_type=="24hrMiniTicker":
            event_ms=int(data.get("E"));event_time=datetime.fromtimestamp(event_ms/1000.0,UTC)
            ev=ReferencePriceEvent(self.NAME,asset,event_time,now,float(data["c"]))
            self.stats.last_event_at=event_time;await self.on_reference(ev)

class KrakenProvider:
    NAME="KRAKEN"
    def __init__(self,config: RealtimeConfig,on_trade: TradeCallback,on_reference: ReferenceCallback,on_message: MessageCallback):
        self.config=config; self.on_trade=on_trade; self.on_reference=on_reference; self.on_message=on_message
        self.stats=ProviderStats(self.NAME);self._stop=False
        self.symbol_to_asset={config.kraken_symbol(a):a for a in config.universe if config.kraken_symbol(a)}

    async def stop(self): self._stop=True

    async def run(self):
        backoff=1.0; first=True
        while not self._stop:
            try:
                if not first:self.stats.reconnects+=1
                first=False;self.stats.status="CONNECTING"
                async with websockets.connect(self.config.kraken_ws_url,ping_interval=20,ping_timeout=20,close_timeout=5,max_queue=4096) as ws:
                    now=datetime.now(UTC);self.stats.status="CONNECTED";self.stats.connected_at=now;self.stats.last_error=None;backoff=1.0
                    request={"method":"subscribe","params":{"channel":"trade","symbol":list(self.symbol_to_asset),"snapshot":False},"req_id":1}
                    await ws.send(json.dumps(request))
                    while not self._stop:
                        try:
                            raw=await asyncio.wait_for(ws.recv(),timeout=max(45.0,self.config.health_stale_seconds*1.5))
                        except asyncio.TimeoutError as exc:
                            raise RuntimeError("Kraken feed silent beyond watchdog limit") from exc
                        await self._handle(raw)
            except asyncio.CancelledError: raise
            except Exception as exc:
                self.stats.errors+=1;self.stats.last_error=f"{type(exc).__name__}: {exc}";self.stats.status="DISCONNECTED"
                await asyncio.sleep(backoff+random.random()*0.5);backoff=min(30.0,backoff*2.0)
        self.stats.status="STOPPED"

    @staticmethod
    def _dt(v: str) -> datetime:
        return datetime.fromisoformat(v.replace("Z","+00:00")).astimezone(UTC)

    async def _handle(self,raw):
        now=datetime.now(UTC);self.stats.messages+=1
        if self.stats.last_message_at:
            self.stats.max_message_gap_seconds=max(self.stats.max_message_gap_seconds,(now-self.stats.last_message_at).total_seconds())
        self.stats.last_message_at=now
        msg=json.loads(raw)
        channel=msg.get("channel")
        # Heartbeat/status/subscription responses are provider liveness evidence.
        await self.on_message(self.NAME,now,None)
        if msg.get("method")=="subscribe" and msg.get("success") is False:
            raise RuntimeError(f"Kraken subscribe failed: {msg.get('error')}")
        if channel!="trade":return
        for item in msg.get("data") or []:
            symbol=item.get("symbol");asset=self.symbol_to_asset.get(symbol)
            if not asset:continue
            event_time=self._dt(item["timestamp"]);side=str(item.get("side") or "").upper()
            ev=TradeEvent(self.NAME,asset,event_time,now,float(item["price"]),float(item["qty"]),side,str(item.get("trade_id")))
            self.stats.last_event_at=event_time
            await self.on_message(self.NAME,now,asset)
            await self.on_reference(ReferencePriceEvent(self.NAME,asset,event_time,now,ev.price))
            await self.on_trade(ev)
