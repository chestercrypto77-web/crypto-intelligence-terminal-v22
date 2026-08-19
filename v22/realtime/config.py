from __future__ import annotations
from dataclasses import dataclass
import os

DEFAULT_UNIVERSE = ("BTC","ETH","SOL","XRP","LINK","COTI")
DEFAULT_BINANCE = {
    "BTC":"btcusdt","ETH":"ethusdt","SOL":"solusdt","XRP":"xrpusdt","LINK":"linkusdt","COTI":"cotiusdt"
}
DEFAULT_KRAKEN = {
    "BTC":"BTC/USD","ETH":"ETH/USD","SOL":"SOL/USD","XRP":"XRP/USD","LINK":"LINK/USD"
}


def _csv(name: str, default: tuple[str,...]) -> tuple[str,...]:
    raw=os.getenv(name,"").strip()
    if not raw:return default
    return tuple(x.strip().upper() for x in raw.split(",") if x.strip())


def _bool(name: str, default: bool) -> bool:
    raw=os.getenv(name,"").strip().lower()
    if not raw:return default
    return raw in {"1","true","yes","on"}


@dataclass(frozen=True)
class RealtimeConfig:
    universe: tuple[str,...] = DEFAULT_UNIVERSE
    primary_provider: str = "BINANCE"
    secondary_provider: str = "KRAKEN"
    kraken_enabled: bool = True
    provider_stale_seconds: float = 12.0
    asset_stale_seconds: float = 20.0
    health_stale_seconds: float = 30.0
    heartbeat_seconds: float = 10.0
    flush_tick_seconds: float = 1.0
    scheduled_reconnect_seconds: float = 23*3600 + 45*60
    event_window_seconds: float = 60.0
    price_move_event_pct: float = 0.40
    flow_imbalance_event_share: float = 0.65
    flow_event_min_trades: int = 20
    event_cooldown_seconds: float = 60.0
    decision_min_coverage_pct: float = 95.0
    port: int = 8080
    poc_mode: bool = True
    binance_ws_base: str = "wss://stream.binance.com:443"
    kraken_ws_url: str = "wss://ws.kraken.com/v2"

    @classmethod
    def from_env(cls) -> "RealtimeConfig":
        return cls(
            universe=_csv("REALTIME_UNIVERSE", DEFAULT_UNIVERSE),
            kraken_enabled=_bool("KRAKEN_ENABLED", True),
            provider_stale_seconds=float(os.getenv("PROVIDER_STALE_SECONDS","12")),
            asset_stale_seconds=float(os.getenv("ASSET_STALE_SECONDS","20")),
            health_stale_seconds=float(os.getenv("HEALTH_STALE_SECONDS","30")),
            heartbeat_seconds=float(os.getenv("HEARTBEAT_SECONDS","10")),
            flush_tick_seconds=float(os.getenv("FLUSH_TICK_SECONDS","1")),
            scheduled_reconnect_seconds=float(os.getenv("SCHEDULED_RECONNECT_SECONDS",str(23*3600+45*60))),
            event_window_seconds=float(os.getenv("EVENT_WINDOW_SECONDS","60")),
            price_move_event_pct=float(os.getenv("EVENT_PRICE_MOVE_PCT","0.40")),
            flow_imbalance_event_share=float(os.getenv("EVENT_FLOW_SHARE","0.65")),
            flow_event_min_trades=int(os.getenv("EVENT_FLOW_MIN_TRADES","20")),
            event_cooldown_seconds=float(os.getenv("EVENT_COOLDOWN_SECONDS","60")),
            decision_min_coverage_pct=float(os.getenv("DECISION_MIN_COVERAGE_PCT","95")),
            port=int(os.getenv("PORT","8080")),
            poc_mode=_bool("REALTIME_POC_MODE", True),
            binance_ws_base=os.getenv("BINANCE_WS_BASE","wss://stream.binance.com:443").rstrip("/"),
            kraken_ws_url=os.getenv("KRAKEN_WS_URL","wss://ws.kraken.com/v2"),
        )

    def binance_symbol(self, asset: str) -> str | None:
        override=os.getenv(f"BINANCE_SYMBOL_{asset.upper()}","").strip().lower()
        return override or DEFAULT_BINANCE.get(asset.upper())

    def kraken_symbol(self, asset: str) -> str | None:
        override=os.getenv(f"KRAKEN_SYMBOL_{asset.upper()}","").strip()
        return override or DEFAULT_KRAKEN.get(asset.upper())
