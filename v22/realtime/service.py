from __future__ import annotations
import asyncio, json, os, socket, uuid
from dataclasses import asdict
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from v22.storage import Database
from .config import RealtimeConfig
from .engine import RealtimeMarketEngine
from .models import TradeEvent, ReferencePriceEvent, MinuteBar, TimeframeState, SignalEvent
from .providers import BinanceProvider, KrakenProvider
from .repository import RealtimeRepository

UTC=timezone.utc
VERSION="22.13.0-realtime-poc"

class RealtimeObserverService:
    def __init__(self,database_url: str,config: RealtimeConfig|None=None):
        self.config=config or RealtimeConfig.from_env()
        self.db=Database(database_url)
        self.repo=RealtimeRepository(self.db)
        self.engine=RealtimeMarketEngine(self.config)
        self.session_id=str(uuid.uuid4())
        self.instance_id=os.getenv("RAILWAY_REPLICA_ID") or os.getenv("HOSTNAME") or socket.gethostname()
        self.started_at=datetime.now(UTC)
        self.stop_event=asyncio.Event()
        self.persist_queue: asyncio.Queue[tuple[str,Any]]=asyncio.Queue(maxsize=10000)
        self.tasks=[]
        self.http_server=None
        self.fatal_error: str|None=None
        self.db_last_success: datetime|None=None
        self.db_last_error: str|None=None
        self.metrics={"bars":0,"states":0,"signals":0,"gaps":0,"persisted":0,"db_errors":0,"db_latency_ms_last":None,"db_latency_ms_max":0.0}
        self.binance=BinanceProvider(self.config,self.on_trade,self.on_reference,self.on_provider_message)
        self.kraken=KrakenProvider(self.config,self.on_trade,self.on_reference,self.on_provider_message) if self.config.kraken_enabled else None

    async def initialise(self):
        await asyncio.to_thread(self.db.migrate)
        await asyncio.to_thread(self.repo.create_session,self.session_id,self.instance_id,VERSION,
            self.config.primary_provider,self.config.secondary_provider if self.kraken else None,self.config.universe,self.started_at)
        bars=await asyncio.to_thread(self.repo.load_recent_bars,self.config.universe,300)
        self.engine.prime(bars)
        self.db_last_success=datetime.now(UTC)

    async def on_provider_message(self,provider: str,when: datetime,asset: str|None):
        self.engine.note_provider_message(provider,when,asset)

    async def on_reference(self,event: ReferencePriceEvent):
        before=self.engine.active_provider.get(event.asset_id,self.config.primary_provider)
        info=self.engine.on_reference(event)
        after=info.get("active_provider")
        if info.get("provider_changed") and after!=before:
            await self.persist_queue.put(("gap",{
                "asset_id":event.asset_id,"provider":before,"gap_start":event.received_at,"gap_end":event.received_at,
                "duration_seconds":0.0,"reason":"PROVIDER_SWITCH","recovered_by":after,
            }))

    async def on_trade(self,event: TradeEvent):
        closed,signals,info=self.engine.on_trade(event)
        for bar in closed:
            await self._accept_bar(bar)
        for signal in signals:
            self.metrics["signals"]+=1;await self.persist_queue.put(("signal",signal))

    async def _accept_bar(self,bar: MinuteBar):
        states=self.engine.accept_closed_bar(bar)
        self.metrics["bars"]+=1;self.metrics["states"]+=len(states)
        await self.persist_queue.put(("bar",bar))
        for state in states: await self.persist_queue.put(("state",state))

    async def minute_flush_loop(self):
        while not self.stop_event.is_set():
            try:
                bars,gaps=self.engine.flush_due(datetime.now(UTC))
                for bar in bars: await self._accept_bar(bar)
                for gap in gaps:
                    self.metrics["gaps"]+=1;await self.persist_queue.put(("gap",gap))
            except Exception as exc:
                self.db_last_error=f"flush {type(exc).__name__}: {exc}"
            await asyncio.sleep(self.config.flush_tick_seconds)

    def _provider_dict(self,provider_obj) -> dict[str,Any]:
        return provider_obj.stats.as_dict() if provider_obj else {}

    def _asset_health(self,asset: str,now: datetime) -> dict[str,Any]:
        primary=self.engine.asset_provider_last_message.get((self.config.primary_provider,asset))
        secondary=self.engine.asset_provider_last_message.get((self.config.secondary_provider,asset))
        active=self.engine.active_provider.get(asset,self.config.primary_provider)
        active_seen=self.engine.asset_provider_last_message.get((active,asset))
        age=(now-active_seen).total_seconds() if active_seen else 1e9
        status="LIVE" if age<=self.config.asset_stale_seconds else "STALE"
        last_bucket=self.engine.last_closed_bucket.get(asset)
        return {
            "active_provider":active,"primary_last_message_at":primary,"secondary_last_message_at":secondary,
            "last_trade_at":self.engine.asset_last_trade.get(asset),
            "last_bar_close_at":last_bucket,
            "expected_minutes":self.engine.expected_minutes[asset],"live_minutes":self.engine.live_minutes[asset],
            "coverage_pct":self.engine.coverage_pct(asset),
            "max_message_gap_seconds":self.engine.asset_provider_max_message_gap.get((active,asset),0.0),
            "max_gap_seconds":self.engine.max_gap_seconds[asset],
            "failovers":self.engine.failovers[asset],"status":status,
        }

    def status_snapshot(self) -> dict[str,Any]:
        now=datetime.now(UTC);uptime=max(0.0,(now-self.started_at).total_seconds())
        providers={self.binance.NAME:self._provider_dict(self.binance)}
        if self.kraken:providers[self.kraken.NAME]=self._provider_dict(self.kraken)
        def serial(v):
            if isinstance(v,datetime):return v.isoformat()
            if isinstance(v,dict):return {k:serial(x) for k,x in v.items()}
            if isinstance(v,(list,tuple)):return [serial(x) for x in v]
            return v
        return serial({
            "version":VERSION,"session_id":self.session_id,"instance_id":self.instance_id,"poc_mode":self.config.poc_mode,
            "started_at":self.started_at,"uptime_seconds":uptime,"universe":self.config.universe,
            "providers":providers,"assets":{a:self._asset_health(a,now) for a in self.config.universe},
            "metrics":{**self.metrics,"late_events":self.engine.late_events,"failovers":sum(self.engine.failovers.values()),"queue_depth":self.persist_queue.qsize()},
            "db_last_success":self.db_last_success,"db_last_error":self.db_last_error,
        })

    def healthy(self) -> tuple[bool,str]:
        now=datetime.now(UTC)
        seen=self.engine.provider_last_message.get(self.config.primary_provider)
        if not seen:return False,"primary feed has not produced a message"
        if (now-seen).total_seconds()>self.config.health_stale_seconds:return False,"primary feed stale"
        if not self.db_last_success or (now-self.db_last_success).total_seconds()>max(30.0,self.config.heartbeat_seconds*3):return False,"database persistence stale"
        return True,"live"

    async def heartbeat_loop(self):
        while not self.stop_event.is_set():
            now=datetime.now(UTC);good,_=self.healthy();status="LIVE" if good else "DEGRADED"
            await self.persist_queue.put(("heartbeat",(status,now,self.status_snapshot()["metrics"])))
            await self.persist_queue.put(("provider_health",(self.binance.NAME,self._provider_dict(self.binance),now)))
            if self.kraken:await self.persist_queue.put(("provider_health",(self.kraken.NAME,self._provider_dict(self.kraken),now)))
            for asset in self.config.universe:
                await self.persist_queue.put(("asset_health",(asset,self._asset_health(asset,now),now)))
            await asyncio.sleep(self.config.heartbeat_seconds)

    def _persist_batch_sync(self,items: list[tuple[str,Any]]):
        with self.db.session():
            for kind,obj in items:
                if kind=="bar":self.repo.upsert_bar(obj)
                elif kind=="state":self.repo.upsert_state(obj)
                elif kind=="signal":self.repo.insert_signal(self.session_id,obj)
                elif kind=="gap":self.repo.insert_gap(self.session_id,obj)
                elif kind=="heartbeat":
                    status,when,metrics=obj;self.repo.heartbeat(self.session_id,status,when,metrics)
                elif kind=="provider_health":
                    provider,state,when=obj;self.repo.upsert_provider_health(self.session_id,provider,state,when)
                elif kind=="asset_health":
                    asset,state,when=obj;self.repo.upsert_asset_health(self.session_id,asset,state,when)

    async def writer_loop(self):
        while not self.stop_event.is_set() or not self.persist_queue.empty():
            items=[]
            try:
                first=await asyncio.wait_for(self.persist_queue.get(),timeout=0.5);items.append(first)
            except asyncio.TimeoutError:
                continue
            while len(items)<500 and not self.persist_queue.empty():items.append(self.persist_queue.get_nowait())
            t0=perf_counter()
            try:
                await asyncio.to_thread(self._persist_batch_sync,items)
                ms=(perf_counter()-t0)*1000.0;self.metrics["db_latency_ms_last"]=round(ms,2);self.metrics["db_latency_ms_max"]=max(self.metrics["db_latency_ms_max"],ms)
                self.metrics["persisted"]+=len(items);self.db_last_success=datetime.now(UTC);self.db_last_error=None
            except Exception as exc:
                self.metrics["db_errors"]+=1;self.db_last_error=f"{type(exc).__name__}: {exc}"
                # Put data back; preserving live evidence is more important than silently dropping it.
                for item in items:
                    try:self.persist_queue.put_nowait(item)
                    except asyncio.QueueFull:break
                await asyncio.sleep(2)
            finally:
                for _ in items:self.persist_queue.task_done()

    async def _http_client(self,reader: asyncio.StreamReader,writer: asyncio.StreamWriter):
        try:
            line=await asyncio.wait_for(reader.readline(),timeout=2)
            parts=line.decode("utf-8","ignore").split();path=parts[1] if len(parts)>1 else "/"
            while True:
                h=await reader.readline()
                if not h or h in {b"\r\n",b"\n"}:break
            healthy,reason=self.healthy()
            if path=="/health":
                code=200 if healthy else 503;payload={"status":"ok" if healthy else "degraded","reason":reason,"version":VERSION}
            elif path=="/status":code=200;payload=self.status_snapshot()
            else:code=200;payload={"service":"V22 realtime observer POC","health":"/health","status":"/status"}
            body=json.dumps(payload,separators=(",",":"),default=str).encode()
            phrase="OK" if code==200 else "Service Unavailable"
            writer.write(f"HTTP/1.1 {code} {phrase}\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()+body)
            await writer.drain()
        except Exception:pass
        finally:
            writer.close()
            try:await writer.wait_closed()
            except Exception:pass

    async def start_http(self):
        self.http_server=await asyncio.start_server(self._http_client,"0.0.0.0",self.config.port)
        async with self.http_server:await self.http_server.serve_forever()


    async def supervisor_loop(self):
        critical={"writer","binance","minute-flush","heartbeat","health-http"}
        if self.kraken:critical.add("kraken")
        while not self.stop_event.is_set():
            for task in list(self.tasks):
                if task.get_name() in critical and task.done():
                    if task.cancelled():
                        self.fatal_error=f"critical task {task.get_name()} cancelled unexpectedly"
                    else:
                        exc=task.exception()
                        self.fatal_error=f"critical task {task.get_name()} stopped: {type(exc).__name__}: {exc}" if exc else f"critical task {task.get_name()} stopped unexpectedly"
                    self.stop_event.set();return
            await asyncio.sleep(2)

    async def run(self):
        await self.initialise()
        self.tasks=[
            asyncio.create_task(self.writer_loop(),name="writer"),
            asyncio.create_task(self.binance.run(),name="binance"),
            asyncio.create_task(self.minute_flush_loop(),name="minute-flush"),
            asyncio.create_task(self.heartbeat_loop(),name="heartbeat"),
            asyncio.create_task(self.start_http(),name="health-http"),
        ]
        if self.kraken:self.tasks.append(asyncio.create_task(self.kraken.run(),name="kraken"))
        self.tasks.append(asyncio.create_task(self.supervisor_loop(),name="supervisor"))
        await self.stop_event.wait()
        reason=self.fatal_error or "stop requested"
        await self.shutdown(reason)
        if self.fatal_error:
            raise RuntimeError(self.fatal_error)

    async def shutdown(self,reason: str="shutdown"):
        if not self.stop_event.is_set():self.stop_event.set()
        await self.binance.stop()
        if self.kraken:await self.kraken.stop()
        # Providers/loops can stop immediately; writer gets a short drain window.
        for task in self.tasks:
            if task.get_name()!="writer":task.cancel()
        try:await asyncio.wait_for(self.persist_queue.join(),timeout=8)
        except Exception:pass
        for task in self.tasks:
            if task.get_name()=="writer":task.cancel()
        try:await asyncio.to_thread(self.repo.stop_session,self.session_id,datetime.now(UTC),reason)
        except Exception:pass
