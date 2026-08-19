from __future__ import annotations
import asyncio,os,uuid
from datetime import datetime,timezone
from v22.storage import Database
from .config import HyperliquidLabConfig
from .provider import HyperliquidMainnetProvider
from .repository import HyperliquidLabRepository
from .engine import MicrostructureEngine
from .execution import HyperliquidTestnetExecutor
UTC=timezone.utc

class HyperliquidLabService:
    def __init__(self,database_url,config=None):
        self.config=config or HyperliquidLabConfig.from_env();self.db=Database(database_url)
        self.repo=HyperliquidLabRepository(self.db);self.engine=MicrostructureEngine(self.config)
        self.executor=HyperliquidTestnetExecutor(self.config);self.session_id=str(uuid.uuid4());self.started=datetime.now(UTC)
        self.q=asyncio.Queue(maxsize=20000);self.stop_event=asyncio.Event()
        self.provider=HyperliquidMainnetProvider(self.config,self.on_trade,self.on_book,self.on_status)
        self.metrics={"trades":0,"books":0,"signals":0,"db_errors":0,"persisted":0}
    async def initialise(self):
        await asyncio.to_thread(self.db.migrate);await asyncio.to_thread(self.repo.create_session,self.session_id,self.started,self.config.universe)
    async def on_status(self,s): await self.q.put(("provider",(s,datetime.now(UTC))))
    async def on_book(self,b):
        self.engine.on_book(b);self.metrics["books"]+=1;await self.q.put(("book",b))
    async def on_trade(self,t):
        self.metrics["trades"]+=1;await self.q.put(("trade",t));sig=self.engine.on_trade(t)
        if sig:self.metrics["signals"]+=1;await self.q.put(("signal",sig))
    def persist(self,items):
        with self.db.session():
            for kind,obj in items:
                if kind=="trade":self.repo.trade(self.session_id,obj)
                elif kind=="book":self.repo.book(self.session_id,obj)
                elif kind=="signal":self.repo.signal(self.session_id,obj)
                elif kind=="provider":
                    state,when=obj;self.repo.provider(self.session_id,state,when)
                elif kind=="heartbeat":self.repo.heartbeat(self.session_id,obj,self.metrics)
    async def writer(self):
        while not self.stop_event.is_set() or not self.q.empty():
            try:first=await asyncio.wait_for(self.q.get(),.5)
            except asyncio.TimeoutError:continue
            items=[first]
            while len(items)<500 and not self.q.empty():items.append(self.q.get_nowait())
            try:await asyncio.to_thread(self.persist,items);self.metrics["persisted"]+=len(items)
            except Exception:
                self.metrics["db_errors"]+=1
                for x in items:
                    try:self.q.put_nowait(x)
                    except asyncio.QueueFull:break
                await asyncio.sleep(1)
    async def heartbeat(self):
        while not self.stop_event.is_set():
            await self.q.put(("heartbeat",datetime.now(UTC)));await asyncio.sleep(self.config.heartbeat_seconds)
    async def run(self):
        await self.initialise()
        tasks=[asyncio.create_task(self.provider.run()),asyncio.create_task(self.writer()),asyncio.create_task(self.heartbeat())]
        try:await self.stop_event.wait()
        finally:
            await self.provider.stop()
            for t in tasks:t.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
