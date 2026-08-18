from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import time

from v22.contracts import CycleType
from v22.core import DeterministicBrainCore, LiveAssetSpec, LiveEvidenceCollector
from v22.storage import BrainRepository, Database

UTC = timezone.utc


class ConcurrentFakeBinance:
    def __init__(self, delay: float = 0.002):
        self.delay = delay
        self.calls: list[tuple[str, str]] = []
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

    def get_json(self, path, params):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.calls.append((params["symbol"], params["interval"]))
        try:
            time.sleep(self.delay)
            interval = params["interval"]
            step = {"1m": 60_000, "5m": 300_000, "15m": 900_000}[interval]
            end = int(params["endTime"])
            limit = int(params["limit"])
            start = end - limit * step
            rows = []
            for i in range(limit):
                open_ms = start + i * step
                close_ms = open_ms + step - 1
                base = 100.0 + i * 0.1
                vol = 1000.0 + (i % 11) * 10.0
                rows.append([open_ms, str(base), str(base + 1), str(base - 1), str(base + .25), str(vol), close_ms, "0", 1, "0", "0", "0"])
            return rows
        finally:
            with self.lock:
                self.active -= 1


def _hundred_specs() -> tuple[LiveAssetSpec, ...]:
    specs = []
    for i in range(100):
        tier = "A" if i < 20 else "B" if i < 60 else "C"
        depth = "FULL" if tier == "A" else "SCREEN"
        specs.append(LiveAssetSpec(f"T{i:03d}", f"T{i:03d}USDT", tier, depth))
    return tuple(specs)


def test_100_asset_collection_is_bounded_concurrent_and_ordered(tmp_path: Path):
    at = datetime(2026, 8, 18, 2, 30, tzinfo=UTC)
    http = ConcurrentFakeBinance()
    specs = _hundred_specs()
    collector = LiveEvidenceCollector(
        tmp_path, http_client=http, asset_specs=specs, max_workers=8, batch_size=8
    )
    batch = collector.collect(CycleType.MICRO_5M, at)

    assert len(batch.assets) == 100
    assert batch.requested_assets == tuple(s.asset_id for s in specs)
    assert tuple(a.asset_id for a in batch.assets) == batch.requested_assets
    assert not batch.unavailable_assets
    assert 1 < http.max_active <= 8
    # 20 FULL assets use 1m+5m (40 calls); 80 SCREEN assets use one 5m call.
    assert len(http.calls) == 120
    assert batch.source_health["tier_counts"] == {"A": 20, "B": 40, "C": 40}
    assert batch.source_health["depth_counts"] == {"FULL": 20, "SCREEN": 80}


def test_screen_depth_uses_one_request_and_no_fake_1m_observations(tmp_path: Path):
    at = datetime(2026, 8, 18, 2, 30, tzinfo=UTC)
    http = ConcurrentFakeBinance(delay=0)
    spec = LiveAssetSpec("SCREEN1", "SCREEN1USDT", "B", "SCREEN")
    collector = LiveEvidenceCollector(tmp_path, http_client=http, asset_specs=(spec,), max_workers=4)
    batch = collector.collect(CycleType.MICRO_5M, at)

    assert http.calls == [("SCREEN1USDT", "5m")]
    asset = batch.assets[0]
    assert asset.metadata["observation_tier"] == "B"
    assert asset.metadata["observation_depth"] == "SCREEN"
    assert "relative_volume_1m" not in {m.name for m in asset.metrics}

    db = Database(f"sqlite:///{tmp_path/'screen.db'}")
    db.migrate()
    result = DeterministicBrainCore(BrainRepository(db), collector).run(CycleType.MICRO_5M, at)
    assert result.status == "COMPLETED"
    assert result.analysed_assets == 1
    rows = db.query("SELECT metric,metadata_json FROM observation_records WHERE cycle_id=? ORDER BY metric", (result.cycle_id,))
    metrics = {r["metric"] for r in rows}
    assert "screen_momentum_5m" in metrics
    assert "volume_flow_5m" in metrics
    assert "volume_flow_1m" not in metrics
    for row in rows:
        metadata = json.loads(row["metadata_json"])
        assert metadata["observation_tier"] == "B"
        assert metadata["observation_depth"] == "SCREEN"


def test_100_asset_tiered_pipeline_completes_with_truthful_coverage(tmp_path: Path):
    at = datetime(2026, 8, 18, 2, 30, tzinfo=UTC)
    http = ConcurrentFakeBinance(delay=0)
    collector = LiveEvidenceCollector(
        tmp_path, http_client=http, asset_specs=_hundred_specs(), max_workers=8, batch_size=8
    )
    db = Database(f"sqlite:///{tmp_path/'hundred.db'}")
    db.migrate()
    result = DeterministicBrainCore(BrainRepository(db), collector).run(
        CycleType.MICRO_5M, at, soft_deadline_seconds=210
    )
    assert result.status == "COMPLETED"
    assert result.expected_assets == 100
    assert result.analysed_assets == 100
    assert int(db.scalar("SELECT COUNT(*) FROM cycle_asset_coverage WHERE cycle_id=? AND deterministic_completed=1", (result.cycle_id,))) == 100
    assert int(db.scalar("SELECT COUNT(*) FROM ai_calls")) == 0


def test_current_config_remains_full_depth_core_universe(tmp_path: Path):
    # Build a tiny config to verify default/backward-compatible policy semantics.
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "v22_live_assets.json").write_text(json.dumps({
        "assets": [
            {"asset_id": "BTC", "binance_symbol": "BTCUSDT"},
            {"asset_id": "ETH", "binance_symbol": "ETHUSDT", "tier": "A", "micro_depth": "FULL"},
        ]
    }))
    from v22.core.live_sources import load_asset_specs
    specs = load_asset_specs(tmp_path)
    assert [(x.asset_id, x.tier, x.micro_depth) for x in specs] == [
        ("BTC", "A", "FULL"), ("ETH", "A", "FULL")
    ]
