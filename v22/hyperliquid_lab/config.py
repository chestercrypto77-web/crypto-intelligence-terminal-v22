from __future__ import annotations
from dataclasses import dataclass
import os

def _csv(name, default):
    raw=os.getenv(name,"").strip()
    return tuple(x.strip().upper() for x in raw.split(",") if x.strip()) if raw else default

@dataclass(frozen=True)
class HyperliquidLabConfig:
    universe: tuple[str,...]=("BTC","ETH","SOL","HYPE")
    mainnet_ws: str="wss://api.hyperliquid.xyz/ws"
    testnet_api: str="https://api.hyperliquid-testnet.xyz"
    heartbeat_seconds: float=10.0
    stale_seconds: float=20.0
    reconnect_max_seconds: float=30.0
    book_levels: int=5
    signal_cooldown_seconds: float=20.0
    # Objective laboratory thresholds, deliberately not confidence scores.
    imbalance_threshold: float=0.62
    flow_threshold: float=0.65
    min_trade_count: int=12
    execution_mode: str="DISABLED"

    @classmethod
    def from_env(cls):
        return cls(
            universe=_csv("HL_LAB_UNIVERSE",("BTC","ETH","SOL","HYPE")),
            mainnet_ws=os.getenv("HL_MAINNET_WS","wss://api.hyperliquid.xyz/ws"),
            testnet_api=os.getenv("HL_TESTNET_API","https://api.hyperliquid-testnet.xyz"),
            heartbeat_seconds=float(os.getenv("HL_HEARTBEAT_SECONDS","10")),
            stale_seconds=float(os.getenv("HL_STALE_SECONDS","20")),
            execution_mode=os.getenv("HL_EXECUTION_MODE","DISABLED").strip().upper(),
        )
