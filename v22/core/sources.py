from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

from v22.contracts import CycleType


def _utc(value: Any, fallback: datetime) -> datetime:
    if not value:
        return fallback.astimezone(timezone.utc)
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return fallback.astimezone(timezone.utc)


@dataclass(frozen=True)
class CollectedMetric:
    name: str
    value: Any
    source_timestamp: datetime
    unit: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CollectedAsset:
    asset_id: str
    source: str
    source_timestamp: datetime
    metrics: tuple[CollectedMetric, ...]
    raw_reference: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CollectionBatch:
    source_file: str
    generated_at: datetime
    requested_assets: tuple[str, ...]
    assets: tuple[CollectedAsset, ...]
    unavailable_assets: tuple[str, ...]
    source_health: Mapping[str, Any] = field(default_factory=dict)


class LegacySnapshotCollector:
    """Stage-2 adapter over the already-working V21/V22 observer outputs.

    This intentionally does *not* replace the existing network collectors yet.
    It converts their persisted snapshots into the strict V22 evidence contract.
    """

    def __init__(self, root: Path):
        self.root = Path(root)

    def _source_path(self, cycle_type: CycleType) -> Path:
        if cycle_type == CycleType.MICRO_5M:
            return self.root / "data" / "microstructure_latest.json"
        if cycle_type == CycleType.MARKET_15M:
            return self.root / "data" / "observer_latest.json"
        raise ValueError(f"Stage 2 collector does not support {cycle_type.value}")

    def collect(self, cycle_type: CycleType, scheduled_at: datetime) -> CollectionBatch:
        path = self._source_path(cycle_type)
        if not path.exists():
            raise FileNotFoundError(f"observer snapshot missing: {path}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"observer snapshot is invalid JSON: {path}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"observer snapshot must be an object: {path}")

        generated_at = _utc(payload.get("generated_at"), scheduled_at)
        health = payload.get("health") if isinstance(payload.get("health"), dict) else {}
        rows = payload.get("signals") if isinstance(payload.get("signals"), list) else []
        unavailable = tuple(str(x).upper() for x in (health.get("unavailable_assets") or []) if str(x).strip())

        requested = []
        assets = []
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "").upper().strip()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol); requested.append(symbol)
            if cycle_type == CycleType.MICRO_5M:
                assets.append(self._micro_asset(row, generated_at, path))
            else:
                assets.append(self._market_asset(row, generated_at, path))

        for symbol in unavailable:
            if symbol not in seen:
                requested.append(symbol); seen.add(symbol)

        assets_requested = health.get("assets_requested")
        try:
            assets_requested = int(assets_requested)
        except Exception:
            assets_requested = len(requested)
        # If the legacy snapshot tells us more assets were requested than it names,
        # create stable UNKNOWN placeholders so coverage cannot falsely look complete.
        while len(requested) < assets_requested:
            requested.append(f"UNKNOWN_{len(requested)+1}")

        return CollectionBatch(
            source_file=str(path.relative_to(self.root)),
            generated_at=generated_at,
            requested_assets=tuple(requested),
            assets=tuple(assets),
            unavailable_assets=unavailable,
            source_health=health,
        )

    def _metric(self, name: str, value: Any, ts: datetime, unit: str | None = None, **metadata: Any) -> CollectedMetric | None:
        if value is None:
            return None
        return CollectedMetric(name=name, value=value, source_timestamp=ts, unit=unit, metadata=metadata)

    def _market_asset(self, row: dict, fallback: datetime, path: Path) -> CollectedAsset:
        ts = _utc(row.get("candle_time") or row.get("recorded_at"), fallback)
        source = str(row.get("data_source") or "legacy 15m observer")
        specs = [
            ("price_usd", row.get("price"), "USD"),
            ("return_15m_pct", row.get("return_15m"), "%"),
            ("return_1h_pct", row.get("return_1h"), "%"),
            ("return_4h_pct", row.get("return_4h"), "%"),
            ("return_24h_pct", row.get("return_24h"), "%"),
            ("relative_volume", row.get("rvol"), "x"),
            ("relative_volume_delta", row.get("rvol_delta"), "x"),
            ("rsi", row.get("rsi"), None),
            ("rsi_delta", row.get("rsi_delta"), None),
            ("macd_histogram", row.get("macd_histogram"), None),
            ("macd_delta", row.get("macd_delta"), None),
            ("breakout", row.get("breakout"), None),
            ("breakdown", row.get("breakdown"), None),
        ]
        metrics = tuple(m for m in (self._metric(n, v, ts, u) for n, v, u in specs) if m is not None)
        return CollectedAsset(
            asset_id=str(row.get("symbol")).upper(), source=source, source_timestamp=ts,
            metrics=metrics, raw_reference=str(path.relative_to(self.root)),
            metadata={"legacy_signal": row.get("signal"), "legacy_lifecycle": row.get("lifecycle_state")},
        )

    def _micro_asset(self, row: dict, fallback: datetime, path: Path) -> CollectedAsset:
        one = row.get("one_minute") if isinstance(row.get("one_minute"), dict) else {}
        five = row.get("five_minute") if isinstance(row.get("five_minute"), dict) else {}
        ts = _utc(five.get("time") or one.get("time") or row.get("recorded_at"), fallback)
        source = str(row.get("data_source") or "legacy 1m/5m observer")
        specs = [
            ("price_usd", row.get("price"), "USD"),
            ("return_1m_5bar_pct", one.get("return_5bars"), "%"),
            ("return_5m_5bar_pct", five.get("return_5bars"), "%"),
            ("relative_volume_1m", one.get("rvol"), "x"),
            ("relative_volume_delta_1m", one.get("rvol_delta"), "x"),
            ("relative_volume_5m", five.get("rvol"), "x"),
            ("relative_volume_delta_5m", five.get("rvol_delta"), "x"),
            ("rsi_1m", one.get("rsi"), None),
            ("rsi_5m", five.get("rsi"), None),
            ("macd_1m", one.get("macd"), None),
            ("macd_5m", five.get("macd"), None),
            ("ema9_1m", one.get("ema9"), "USD"),
            ("ema21_1m", one.get("ema21"), "USD"),
            ("ema9_5m", five.get("ema9"), "USD"),
            ("ema21_5m", five.get("ema21"), "USD"),
            ("atr_1m_pct", one.get("atr_pct"), "%"),
            ("atr_5m_pct", five.get("atr_pct"), "%"),
            ("breakout_5m", five.get("breakout"), None),
            ("breakdown_5m", five.get("breakdown"), None),
        ]
        metrics = tuple(m for m in (self._metric(n, v, ts, u) for n, v, u in specs) if m is not None)
        return CollectedAsset(
            asset_id=str(row.get("symbol")).upper(), source=source, source_timestamp=ts,
            metrics=metrics, raw_reference=str(path.relative_to(self.root)),
            metadata={"legacy_role_signal": row.get("role_signal"), "legacy_state": row.get("state")},
        )
