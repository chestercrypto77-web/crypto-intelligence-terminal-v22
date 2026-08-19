from __future__ import annotations
import asyncio,json
from datetime import datetime,timezone
from v22.hyperliquid_lab.config import HyperliquidLabConfig
from v22.hyperliquid_lab.engine import MicrostructureEngine
from v22.hyperliquid_lab.models import BookState,TradeFlow
from v22.hyperliquid_lab.provider import HyperliquidMainnetProvider
UTC=timezone.utc
async def _noop(*a):pass
def test_hyperliquid_trade_and_book_parser():
    c=HyperliquidLabConfig(universe=("BTC",)); trades=[];books=[]
    async def t(x):trades.append(x)
    async def b(x):books.append(x)
    p=HyperliquidMainnetProvider(c,t,b,_noop)
    asyncio.run(p._handle(json.dumps({"channel":"trades","data":[{"coin":"BTC","side":"B","px":"100","sz":"2","time":1700000000000,"tid":7}]})))
    asyncio.run(p._handle(json.dumps({"channel":"l2Book","data":{"coin":"BTC","time":1700000000000,"levels":[[{"px":"99","sz":"5","n":1}],[{"px":"101","sz":"3","n":1}]]}})))
    assert trades[0].side=="BUY" and trades[0].price==100
    assert books[0].imbalance==0.625
def test_microstructure_alignment_is_objective_and_cooldown():
    c=HyperliquidLabConfig(universe=("BTC",),min_trade_count=12,flow_threshold=.65,imbalance_threshold=.62)
    e=MicrostructureEngine(c);now=datetime.now(UTC)
    e.on_book(BookState("BTC",now,now,99,101,200,10,2,10/12))
    sig=None
    for i in range(12):
        sig=e.on_trade(TradeFlow("BTC",now,now,100,1,"BUY",str(i))) or sig
    assert sig and sig.direction=="LONG" and sig.signal_type=="FLOW_BOOK_ALIGNMENT"
    assert 0 <= sig.buy_flow_share <= 1
def test_execution_gate_closed_by_default():
    from v22.hyperliquid_lab.execution import HyperliquidTestnetExecutor
    ex=HyperliquidTestnetExecutor(HyperliquidLabConfig())
    assert ex.readiness().configured is False
    try:ex.submit()
    except RuntimeError:pass
    else:assert False
