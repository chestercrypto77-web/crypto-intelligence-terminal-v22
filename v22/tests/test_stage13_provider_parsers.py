from __future__ import annotations
import asyncio,json

from v22.realtime.config import RealtimeConfig
from v22.realtime.providers import BinanceProvider, KrakenProvider

def test_binance_aggtrade_and_miniticker_parser():
    async def run():
        trades=[];refs=[];msgs=[]
        async def on_trade(x):trades.append(x)
        async def on_ref(x):refs.append(x)
        async def on_msg(p,t,a):msgs.append((p,a))
        p=BinanceProvider(RealtimeConfig(universe=("BTC",),kraken_enabled=False),on_trade,on_ref,on_msg)
        await p._handle(json.dumps({"stream":"btcusdt@aggTrade","data":{"e":"aggTrade","E":1787097601000,"s":"BTCUSDT","a":12,"p":"100.50","q":"0.25","T":1787097600990,"m":False}}))
        await p._handle(json.dumps({"stream":"btcusdt@miniTicker","data":{"e":"24hrMiniTicker","E":1787097602000,"s":"BTCUSDT","c":"101.25"}}))
        assert len(trades)==1 and trades[0].asset_id=="BTC" and trades[0].taker_side=="BUY"
        assert trades[0].price==100.5 and trades[0].quantity==0.25
        assert len(refs)==1 and refs[0].price==101.25
        assert p.stats.messages==2
    asyncio.run(run())

def test_kraken_trade_parser_uses_taker_side_and_symbol_mapping():
    async def run():
        trades=[];refs=[];msgs=[]
        async def on_trade(x):trades.append(x)
        async def on_ref(x):refs.append(x)
        async def on_msg(p,t,a):msgs.append((p,a))
        p=KrakenProvider(RealtimeConfig(universe=("BTC",),kraken_enabled=True),on_trade,on_ref,on_msg)
        await p._handle(json.dumps({"channel":"trade","type":"update","data":[{"symbol":"BTC/USD","side":"sell","qty":0.5,"price":100.0,"ord_type":"market","trade_id":42,"timestamp":"2026-08-19T00:00:00.123456Z"}]}))
        assert len(trades)==1 and trades[0].asset_id=="BTC" and trades[0].taker_side=="SELL"
        assert len(refs)==1 and refs[0].provider=="KRAKEN"
        assert p.stats.messages==1
    asyncio.run(run())
