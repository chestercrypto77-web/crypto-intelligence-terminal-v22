from __future__ import annotations
import asyncio,json,random
from datetime import datetime,timezone
import websockets
from .models import BookState,TradeFlow

UTC=timezone.utc

class HyperliquidMainnetProvider:
    def __init__(self,config,on_trade,on_book,on_status):
        self.config=config;self.on_trade=on_trade;self.on_book=on_book;self.on_status=on_status
        self.stop_event=asyncio.Event()
        self.status="STARTING";self.connected_at=None;self.last_message_at=None
        self.messages=0;self.reconnects=0;self.errors=0;self.max_gap_seconds=0.0;self.last_error=None

    async def stop(self): self.stop_event.set()

    async def _subscribe(self,ws):
        for coin in self.config.universe:
            for sub in ({"type":"trades","coin":coin},{"type":"l2Book","coin":coin}):
                await ws.send(json.dumps({"method":"subscribe","subscription":sub}))

    async def run(self):
        backoff=1.0;first=True
        while not self.stop_event.is_set():
            try:
                if not first:self.reconnects+=1
                first=False;self.status="CONNECTING";await self.on_status(self.snapshot())
                async with websockets.connect(self.config.mainnet_ws,ping_interval=20,ping_timeout=20,close_timeout=5,max_queue=8192) as ws:
                    self.connected_at=datetime.now(UTC);self.status="CONNECTED";self.last_error=None;backoff=1.0
                    await self._subscribe(ws);await self.on_status(self.snapshot())
                    while not self.stop_event.is_set():
                        raw=await asyncio.wait_for(ws.recv(),timeout=max(30.0,self.config.stale_seconds*1.5))
                        await self._handle(raw)
            except asyncio.CancelledError: raise
            except Exception as exc:
                self.errors+=1;self.last_error=f"{type(exc).__name__}: {exc}";self.status="DISCONNECTED"
                await self.on_status(self.snapshot())
                await asyncio.sleep(backoff+random.random()*0.4);backoff=min(self.config.reconnect_max_seconds,backoff*2)
        self.status="STOPPED";await self.on_status(self.snapshot())

    def snapshot(self):
        return {"provider":"HYPERLIQUID_MAINNET","status":self.status,"connected_at":self.connected_at,
                "last_message_at":self.last_message_at,"messages":self.messages,"reconnects":self.reconnects,
                "errors":self.errors,"max_gap_seconds":self.max_gap_seconds,"last_error":self.last_error}

    async def _handle(self,raw):
        now=datetime.now(UTC)
        if self.last_message_at:self.max_gap_seconds=max(self.max_gap_seconds,(now-self.last_message_at).total_seconds())
        self.last_message_at=now;self.messages+=1
        msg=json.loads(raw);ch=msg.get("channel");data=msg.get("data")
        if ch=="trades":
            for t in data or []:
                # Hyperliquid side: A = aggressor sell/ask, B = aggressor buy/bid.
                side="BUY" if str(t.get("side")).upper()=="B" else "SELL"
                ev=TradeFlow(str(t["coin"]).upper(),datetime.fromtimestamp(int(t["time"])/1000,UTC),now,
                             float(t["px"]),float(t["sz"]),side,str(t.get("tid") or t.get("hash") or ""))
                await self.on_trade(ev)
        elif ch=="l2Book" and isinstance(data,dict):
            coin=str(data.get("coin") or "").upper(); levels=data.get("levels") or [[],[]]
            bids,asks=(levels+[[],[]])[:2]
            if not coin or not bids or not asks:return
            bid=float(bids[0]["px"]);ask=float(asks[0]["px"]);mid=(bid+ask)/2
            bd=sum(float(x["sz"]) for x in bids[:self.config.book_levels]);ad=sum(float(x["sz"]) for x in asks[:self.config.book_levels])
            imb=bd/(bd+ad) if bd+ad else .5
            ts=datetime.fromtimestamp(int(data.get("time") or int(now.timestamp()*1000))/1000,UTC)
            await self.on_book(BookState(coin,ts,now,bid,ask,((ask-bid)/mid*10000 if mid else 0),bd,ad,imb))
