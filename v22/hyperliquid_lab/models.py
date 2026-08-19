from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class BookState:
    asset_id:str; event_time:datetime; received_at:datetime
    best_bid:float; best_ask:float; spread_bps:float
    bid_depth:float; ask_depth:float; imbalance:float

@dataclass(frozen=True)
class TradeFlow:
    asset_id:str; event_time:datetime; received_at:datetime
    price:float; size:float; side:str; trade_id:str

@dataclass(frozen=True)
class LabSignal:
    asset_id:str; event_time:datetime; signal_type:str; direction:str
    price:float; spread_bps:float|None; book_imbalance:float|None
    buy_flow_share:float|None; evidence:dict
