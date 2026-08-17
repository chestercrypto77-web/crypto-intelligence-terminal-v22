from __future__ import annotations
from dataclasses import dataclass
import os

@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///data/v22_local.db")
    mode: str = os.getenv("V22_MODE", "shadow").lower()
    poll_seconds: float = float(os.getenv("V22_POLL_SECONDS", "1"))
    one_minute_seconds: int = int(os.getenv("V22_1M_SECONDS", "60"))
    five_minute_seconds: int = int(os.getenv("V22_5M_SECONDS", "300"))
    fifteen_minute_seconds: int = int(os.getenv("V22_15M_SECONDS", "900"))
    learning_seconds: int = int(os.getenv("V22_LEARNING_SECONDS", "3600"))
    watchdog_seconds: int = int(os.getenv("V22_WATCHDOG_SECONDS", "30"))
    stale_factor: float = float(os.getenv("V22_STALE_FACTOR", "2.2"))
    instance_id: str = os.getenv("RENDER_INSTANCE_ID") or os.getenv("HOSTNAME") or "local"
    v21_bridge_enabled: bool = os.getenv("V22_V21_BRIDGE", "1") == "1"

SETTINGS = Settings()
