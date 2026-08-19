from __future__ import annotations
from collections import defaultdict,deque
from datetime import datetime,timedelta,timezone
from .models import BookState,TradeFlow,LabSignal
UTC=timezone.utc

class MicrostructureEngine:
    def __init__(self,config):
        self.config=config;self.books={};self.trades=defaultdict(lambda:deque(maxlen=5000));self.last_signal={}
    def on_book(self,b:BookState): self.books[b.asset_id]=b
    def on_trade(self,t:TradeFlow):
        q=self.trades[t.asset_id];q.append(t);cut=t.event_time-timedelta(seconds=60)
        while q and q[0].event_time<cut:q.popleft()
        return self.evaluate(t.asset_id,t.event_time,t.price)
    def evaluate(self,asset,now,price):
        book=self.books.get(asset);q=self.trades[asset]
        if not book or len(q)<self.config.min_trade_count:return None
        buy=sum(x.price*x.size for x in q if x.side=="BUY");sell=sum(x.price*x.size for x in q if x.side=="SELL");tot=buy+sell
        share=buy/tot if tot else .5;imb=book.imbalance
        direction=None;kind=None
        if share>=self.config.flow_threshold and imb>=self.config.imbalance_threshold:
            direction="LONG";kind="FLOW_BOOK_ALIGNMENT"
        elif share<=1-self.config.flow_threshold and imb<=1-self.config.imbalance_threshold:
            direction="SHORT";kind="FLOW_BOOK_ALIGNMENT"
        if not direction:return None
        key=(asset,direction);last=self.last_signal.get(key)
        if last and (now-last).total_seconds()<self.config.signal_cooldown_seconds:return None
        self.last_signal[key]=now
        return LabSignal(asset,now,kind,direction,price,book.spread_bps,imb,share,
                         {"window_seconds":60,"trades":len(q),"buy_notional":buy,"sell_notional":sell,
                          "bid_depth_top_levels":book.bid_depth,"ask_depth_top_levels":book.ask_depth})
