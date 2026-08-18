from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from v22.contracts import CycleType
from .sources import CollectionBatch, CollectedAsset, CollectedMetric


class LiveSourceError(RuntimeError):
    pass


class RateLimited(LiveSourceError):
    def __init__(self, message: str, retry_after: str | None = None):
        super().__init__(message)
        self.retry_after = retry_after


VALID_TIERS = {"A", "B", "C"}
VALID_MICRO_DEPTHS = {"FULL", "SCREEN"}


@dataclass(frozen=True)
class LiveAssetSpec:
    asset_id: str
    market_symbol: str
    tier: str = "A"
    micro_depth: str = "FULL"

    def __post_init__(self) -> None:
        if not self.asset_id.strip() or not self.market_symbol.strip():
            raise ValueError("asset_id and market_symbol are required")
        if self.tier.upper() not in VALID_TIERS:
            raise ValueError(f"unsupported observation tier: {self.tier}")
        if self.micro_depth.upper() not in VALID_MICRO_DEPTHS:
            raise ValueError(f"unsupported micro observation depth: {self.micro_depth}")


DEFAULT_ASSETS = (
    "BTC", "ETH", "SOL", "XRP", "BNB", "ADA", "DOGE", "LINK",
    "AVAX", "TRX", "DOT", "SUI", "HBAR", "ONDO", "COTI", "ZIL",
)


def _default_specs() -> tuple[LiveAssetSpec, ...]:
    raw = os.getenv("V22_LIVE_ASSETS", ",".join(DEFAULT_ASSETS))
    result = []
    for token in raw.split(","):
        asset = token.strip().upper()
        if asset:
            result.append(LiveAssetSpec(asset, f"{asset}USDT", "A", "FULL"))
    return tuple(result)


def load_asset_specs(root: Path) -> tuple[LiveAssetSpec, ...]:
    path = Path(root) / "config" / "v22_live_assets.json"
    if not path.exists():
        return _default_specs()
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("assets", []) if isinstance(payload, dict) else []
    out = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or row.get("enabled", True) is False:
            continue
        asset = str(row.get("asset_id") or "").strip().upper()
        pair = str(row.get("binance_symbol") or f"{asset}USDT").strip().upper()
        tier = str(row.get("tier") or "A").strip().upper()
        depth = str(row.get("micro_depth") or "FULL").strip().upper()
        if not asset or not pair:
            continue
        if asset in seen:
            raise ValueError(f"duplicate live asset_id in config: {asset}")
        seen.add(asset)
        out.append(LiveAssetSpec(asset, pair, tier, depth))
    return tuple(out) or _default_specs()


class BinanceHttpClient:
    """No-key client for Binance's public market-data-only REST host."""

    def __init__(self, base_url: str = "https://data-api.binance.vision", timeout: float = 8.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def get_json(self, path: str, params: Mapping[str, Any]) -> Any:
        url = f"{self.base_url}{path}?{urlencode(params)}"
        req = Request(url, headers={"User-Agent": "v22-brain/22.9", "Accept": "application/json"})
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
        except HTTPError as exc:
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            if exc.code in {418, 429}:
                raise RateLimited(f"Binance market data rate limited: HTTP {exc.code}", retry_after) from exc
            raise LiveSourceError(f"Binance market data HTTP {exc.code}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise LiveSourceError(f"Binance market data unavailable: {type(exc).__name__}: {exc}") from exc
        try:
            return json.loads(body)
        except Exception as exc:
            raise LiveSourceError("Binance returned malformed JSON") from exc


def _f(x: Any) -> float:
    v = float(x)
    if not math.isfinite(v):
        raise ValueError("non-finite market value")
    return v


def _ema(values: Sequence[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (period + 1.0)
    out = [values[0]]
    for v in values[1:]:
        out.append(alpha * v + (1 - alpha) * out[-1])
    return out


def _rsi(values: Sequence[float], period: int = 14) -> float:
    if len(values) <= period:
        return 50.0
    diffs = [values[i] - values[i - 1] for i in range(1, len(values))][-period:]
    gains = sum(max(x, 0) for x in diffs) / period
    losses = sum(max(-x, 0) for x in diffs) / period
    if losses == 0:
        return 100.0 if gains > 0 else 50.0
    rs = gains / losses
    return 100.0 - (100.0 / (1.0 + rs))


def _macd_hist(values: Sequence[float]) -> float:
    e12, e26 = _ema(values, 12), _ema(values, 26)
    macd = [a - b for a, b in zip(e12, e26)]
    signal = _ema(macd, 9)
    return macd[-1] - signal[-1]


def _pct(a: float, b: float) -> float:
    return ((a / b) - 1.0) * 100.0 if b else 0.0


def _bars(payload: Any, scheduled_at: datetime) -> list[dict[str, float | int]]:
    if not isinstance(payload, list):
        raise LiveSourceError("Binance kline response must be a list")
    max_ms = int(scheduled_at.timestamp() * 1000)
    out = []
    for row in payload:
        if not isinstance(row, list) or len(row) < 7:
            continue
        try:
            close_ms = int(row[6])
            if close_ms > max_ms:
                continue
            out.append({
                "open_ms": int(row[0]), "open": _f(row[1]), "high": _f(row[2]),
                "low": _f(row[3]), "close": _f(row[4]), "volume": _f(row[5]),
                "close_ms": close_ms,
            })
        except Exception:
            continue
    if len(out) < 30:
        raise LiveSourceError(f"insufficient closed kline history ({len(out)} bars)")
    return out


def _metric(name: str, value: Any, ts: datetime, unit: str | None = None, **meta: Any) -> CollectedMetric:
    return CollectedMetric(name=name, value=value, source_timestamp=ts, unit=unit, metadata=meta)


def _rvol(bars: Sequence[dict[str, Any]]) -> tuple[float, float]:
    vols = [float(x["volume"]) for x in bars]
    current = vols[-1]
    baseline = sum(vols[-21:-1]) / max(1, len(vols[-21:-1]))
    prior_baseline = sum(vols[-22:-2]) / max(1, len(vols[-22:-2])) if len(vols) >= 22 else baseline
    current_r = current / baseline if baseline else 0.0
    prior_r = vols[-2] / prior_baseline if prior_baseline else 0.0
    return current_r, current_r - prior_r


def _atr_pct(bars: Sequence[dict[str, Any]], period: int = 14) -> float:
    window = bars[-period:]
    trs = []
    prev = None
    for b in window:
        h, l, c = float(b["high"]), float(b["low"]), float(b["close"])
        trs.append(h - l if prev is None else max(h - l, abs(h - prev), abs(l - prev)))
        prev = c
    close = float(window[-1]["close"])
    return (sum(trs) / len(trs)) / close * 100 if close else 0.0


def _structure(bars: Sequence[dict[str, Any]]) -> tuple[bool, bool]:
    if len(bars) < 21:
        return False, False
    last = float(bars[-1]["close"])
    prior = bars[-21:-1]
    return last > max(float(x["high"]) for x in prior), last < min(float(x["low"]) for x in prior)


class LiveEvidenceCollector:
    """Scalable no-key live market collector.

    V22.9 collects assets in bounded concurrent waves. One asset/provider failure is
    isolated; a provider rate-limit stops *future* waves rather than hammering the
    endpoint. Asset order is restored before returning so downstream idempotency and
    audit output remain deterministic.

    MICRO_5M supports two explicit depths:
      FULL   -> 1m + 5m evidence (current core universe behavior)
      SCREEN -> one 5m request and a smaller deterministic screening evidence set

    The current 16-token production universe stays Tier A / FULL by default. The
    tier/depth policy exists so a future 100+ token universe does not need 200 HTTP
    requests and heavyweight calculations every five minutes.
    """

    def __init__(
        self,
        root: Path,
        *,
        http_client: Any | None = None,
        asset_specs: Sequence[LiveAssetSpec] | None = None,
        max_workers: int | None = None,
        batch_size: int | None = None,
    ):
        self.root = Path(root)
        self.http = http_client or BinanceHttpClient(
            base_url=os.getenv("V22_BINANCE_MARKET_BASE_URL", "https://data-api.binance.vision"),
            timeout=float(os.getenv("V22_LIVE_HTTP_TIMEOUT_SECONDS", "8")),
        )
        self.asset_specs = tuple(asset_specs or load_asset_specs(self.root))
        ids = [x.asset_id for x in self.asset_specs]
        if len(ids) != len(set(ids)):
            raise ValueError("live asset specs must have unique asset_id values")
        workers = max_workers if max_workers is not None else int(os.getenv("V22_LIVE_MAX_WORKERS", "8"))
        self.max_workers = max(1, min(32, int(workers)))
        configured_batch = batch_size if batch_size is not None else int(os.getenv("V22_LIVE_BATCH_SIZE", str(self.max_workers)))
        self.batch_size = max(1, min(64, int(configured_batch)))

    def _fetch(self, spec: LiveAssetSpec, interval: str, limit: int, scheduled_at: datetime) -> list[dict[str, Any]]:
        payload = self.http.get_json("/api/v3/klines", {
            "symbol": spec.market_symbol, "interval": interval, "limit": limit,
            "endTime": int(scheduled_at.timestamp() * 1000),
        })
        return _bars(payload, scheduled_at)

    def _collect_one(self, spec: LiveAssetSpec, cycle_type: CycleType, scheduled_at: datetime) -> CollectedAsset:
        if cycle_type == CycleType.MARKET_15M:
            return self._market(spec, scheduled_at)
        if spec.micro_depth.upper() == "SCREEN":
            return self._micro_screen(spec, scheduled_at)
        return self._micro(spec, scheduled_at)

    def collect(self, cycle_type: CycleType, scheduled_at: datetime) -> CollectionBatch:
        if cycle_type not in {CycleType.MICRO_5M, CycleType.MARKET_15M}:
            raise ValueError(f"live collector does not support {cycle_type.value}")
        generated_at = datetime.now(timezone.utc)
        requested = tuple(x.asset_id for x in self.asset_specs)
        collected: dict[str, CollectedAsset] = {}
        errors: dict[str, str] = {}
        unavailable: set[str] = set()
        rate_limited = False

        # Submit one bounded wave at a time. This provides real concurrency without
        # dumping a 100-token universe onto the provider simultaneously. If any task
        # is rate-limited, later waves are never submitted.
        with ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="v22-market") as executor:
            for start in range(0, len(self.asset_specs), self.batch_size):
                wave = self.asset_specs[start:start + self.batch_size]
                futures = {executor.submit(self._collect_one, spec, cycle_type, scheduled_at): spec for spec in wave}
                wave_rate_limited = False
                for future in as_completed(futures):
                    spec = futures[future]
                    try:
                        collected[spec.asset_id] = future.result()
                    except RateLimited as exc:
                        unavailable.add(spec.asset_id)
                        errors[spec.asset_id] = str(exc)
                        wave_rate_limited = True
                    except Exception as exc:
                        unavailable.add(spec.asset_id)
                        errors[spec.asset_id] = f"{type(exc).__name__}: {exc}"
                if wave_rate_limited:
                    rate_limited = True
                    for spec in self.asset_specs[start + len(wave):]:
                        unavailable.add(spec.asset_id)
                        errors[spec.asset_id] = "skipped after provider rate limit"
                    break

        # Restore configured order regardless of thread completion order.
        assets = tuple(collected[spec.asset_id] for spec in self.asset_specs if spec.asset_id in collected)
        unavailable_ordered = tuple(spec.asset_id for spec in self.asset_specs if spec.asset_id in unavailable)
        tier_counts = Counter(spec.tier.upper() for spec in self.asset_specs)
        depth_counts = Counter((spec.micro_depth.upper() if cycle_type == CycleType.MICRO_5M else "FULL") for spec in self.asset_specs)
        return CollectionBatch(
            source_file="live://binance/klines",
            generated_at=generated_at,
            requested_assets=requested,
            assets=assets,
            unavailable_assets=unavailable_ordered,
            source_health={
                "provider": "binance-public-market-data",
                "requested": len(requested),
                "collected": len(assets),
                "unavailable": len(unavailable_ordered),
                "rate_limited": rate_limited,
                "errors": errors,
                "max_workers": self.max_workers,
                "batch_size": self.batch_size,
                "tier_counts": dict(tier_counts),
                "depth_counts": dict(depth_counts),
            },
        )

    @staticmethod
    def _meta(spec: LiveAssetSpec, depth: str) -> dict[str, Any]:
        return {
            "market_symbol": spec.market_symbol,
            "live": True,
            "observation_tier": spec.tier.upper(),
            "observation_depth": depth,
        }

    def _market(self, spec: LiveAssetSpec, at: datetime) -> CollectedAsset:
        b = self._fetch(spec, "15m", 110, at)
        closes = [float(x["close"]) for x in b]
        ts = datetime.fromtimestamp(int(b[-1]["close_ms"]) / 1000, timezone.utc)
        rvol, rvol_d = _rvol(b)
        breakout, breakdown = _structure(b)
        rsi_now = _rsi(closes)
        rsi_prev = _rsi(closes[:-1])
        macd_now = _macd_hist(closes)
        macd_prev = _macd_hist(closes[:-1])
        metrics = (
            _metric("price_usd", closes[-1], ts, "USD"),
            _metric("return_15m_pct", _pct(closes[-1], closes[-2]), ts, "%"),
            _metric("return_1h_pct", _pct(closes[-1], closes[-5]), ts, "%"),
            _metric("return_4h_pct", _pct(closes[-1], closes[-17]), ts, "%"),
            _metric("return_24h_pct", _pct(closes[-1], closes[-97]), ts, "%"),
            _metric("relative_volume", rvol, ts, "x"), _metric("relative_volume_delta", rvol_d, ts, "x"),
            _metric("rsi", rsi_now, ts), _metric("rsi_delta", rsi_now - rsi_prev, ts),
            _metric("macd_histogram", macd_now, ts), _metric("macd_delta", macd_now - macd_prev, ts),
            _metric("breakout", breakout, ts), _metric("breakdown", breakdown, ts),
        )
        return CollectedAsset(
            spec.asset_id, "Binance public 15m klines", ts, metrics,
            raw_reference=f"binance:{spec.market_symbol}:15m",
            metadata=self._meta(spec, "FULL"),
        )

    def _micro_screen(self, spec: LiveAssetSpec, at: datetime) -> CollectedAsset:
        five = self._fetch(spec, "5m", 60, at)
        c5 = [float(x["close"]) for x in five]
        ts = datetime.fromtimestamp(int(five[-1]["close_ms"]) / 1000, timezone.utc)
        rv5, rd5 = _rvol(five)
        bo, bd = _structure(five)
        metrics = (
            _metric("price_usd", c5[-1], ts, "USD"),
            _metric("return_5m_5bar_pct", _pct(c5[-1], c5[-6]), ts, "%"),
            _metric("relative_volume_5m", rv5, ts, "x"),
            _metric("relative_volume_delta_5m", rd5, ts, "x"),
            _metric("rsi_5m", _rsi(c5), ts),
            _metric("macd_5m", _macd_hist(c5), ts),
            _metric("atr_5m_pct", _atr_pct(five), ts, "%"),
            _metric("breakout_5m", bo, ts),
            _metric("breakdown_5m", bd, ts),
        )
        return CollectedAsset(
            spec.asset_id, "Binance public 5m screening klines", ts, metrics,
            raw_reference=f"binance:{spec.market_symbol}:5m:screen",
            metadata=self._meta(spec, "SCREEN"),
        )

    def _micro(self, spec: LiveAssetSpec, at: datetime) -> CollectedAsset:
        one = self._fetch(spec, "1m", 100, at)
        five = self._fetch(spec, "5m", 100, at)
        c1 = [float(x["close"]) for x in one]
        c5 = [float(x["close"]) for x in five]
        ts = datetime.fromtimestamp(min(int(one[-1]["close_ms"]), int(five[-1]["close_ms"])) / 1000, timezone.utc)
        rv1, rd1 = _rvol(one)
        rv5, rd5 = _rvol(five)
        bo, bd = _structure(five)
        e9_1, e21_1 = _ema(c1, 9)[-1], _ema(c1, 21)[-1]
        e9_5, e21_5 = _ema(c5, 9)[-1], _ema(c5, 21)[-1]
        metrics = (
            _metric("price_usd", c1[-1], ts, "USD"),
            _metric("return_1m_5bar_pct", _pct(c1[-1], c1[-6]), ts, "%"),
            _metric("return_5m_5bar_pct", _pct(c5[-1], c5[-6]), ts, "%"),
            _metric("relative_volume_1m", rv1, ts, "x"), _metric("relative_volume_delta_1m", rd1, ts, "x"),
            _metric("relative_volume_5m", rv5, ts, "x"), _metric("relative_volume_delta_5m", rd5, ts, "x"),
            _metric("rsi_1m", _rsi(c1), ts), _metric("rsi_5m", _rsi(c5), ts),
            _metric("macd_1m", _macd_hist(c1), ts), _metric("macd_5m", _macd_hist(c5), ts),
            _metric("ema9_1m", e9_1, ts, "USD"), _metric("ema21_1m", e21_1, ts, "USD"),
            _metric("ema9_5m", e9_5, ts, "USD"), _metric("ema21_5m", e21_5, ts, "USD"),
            _metric("atr_1m_pct", _atr_pct(one), ts, "%"), _metric("atr_5m_pct", _atr_pct(five), ts, "%"),
            _metric("breakout_5m", bo, ts), _metric("breakdown_5m", bd, ts),
        )
        return CollectedAsset(
            spec.asset_id, "Binance public 1m/5m klines", ts, metrics,
            raw_reference=f"binance:{spec.market_symbol}:1m+5m",
            metadata=self._meta(spec, "FULL"),
        )
