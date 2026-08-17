from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile

import pytest

from v22.contracts import CycleType
from v22.core import DeterministicBrainCore, LegacySnapshotCollector
from v22.storage import BrainRepository, Database


NOW = datetime(2026, 8, 17, 5, 15, tzinfo=timezone.utc)


def setup_repo():
    td = tempfile.TemporaryDirectory()
    root = Path(td.name)
    (root / "data").mkdir()
    db = Database("sqlite:///" + str(root / "brain.db")); db.migrate()
    return td, root, db, BrainRepository(db)


def write_json(path: Path, payload: dict):
    path.write_text(json.dumps(payload), encoding="utf-8")


def market_row(symbol="BTC", ts=NOW, rvol=1.6, rvol_delta=0.4, breakout=False):
    return {
        "symbol": symbol, "name": symbol, "data_source": "fixture 15m",
        "candle_time": ts.isoformat(), "price": 65000,
        "return_15m": 0.5, "return_1h": 1.1, "return_4h": 2.3, "return_24h": 3.5,
        "rvol": rvol, "rvol_delta": rvol_delta, "rsi": 61, "rsi_delta": 3,
        "macd_histogram": 1.2, "macd_delta": 0.3, "breakout": breakout, "breakdown": False,
    }


def micro_row(symbol="ETH", ts=NOW, breakout=False):
    return {
        "symbol": symbol, "name": symbol, "data_source": "fixture 1m",
        "recorded_at": ts.isoformat(), "price": 3200,
        "one_minute": {"time": ts.isoformat(), "price": 3200, "ema9": 3180, "ema21": 3150, "rsi": 58,
                       "macd": 1.0, "rvol": 1.4, "rvol_delta": 0.2, "atr_pct": 0.7, "return_5bars": 0.5},
        "five_minute": {"time": ts.isoformat(), "price": 3200, "ema9": 3170, "ema21": 3120, "rsi": 60,
                        "macd": 1.2, "rvol": 1.5, "rvol_delta": 0.3, "atr_pct": 0.8, "return_5bars": 1.0,
                        "breakout": breakout, "breakdown": False},
    }


def test_market_cycle_persists_evidence_and_objective_observations():
    td, root, db, repo = setup_repo()
    try:
        write_json(root / "data" / "observer_latest.json", {
            "generated_at": NOW.isoformat(), "signals": [market_row()],
            "health": {"assets_requested": 1, "assets_analysed": 1, "unavailable_assets": []},
        })
        result = DeterministicBrainCore(repo, LegacySnapshotCollector(root)).run(CycleType.MARKET_15M, NOW)
        assert result.status == "COMPLETED"
        assert result.analysed_assets == 1
        assert db.scalar("SELECT COUNT(*) FROM evidence_records") >= 10
        metrics = {r["metric"]: json.loads(r["value_json"]) for r in db.query("SELECT metric,value_json FROM observation_records")}
        assert metrics["multi_timeframe_direction"] == "UP"
        assert metrics["volume_flow"] == "UP"
        assert metrics["volume_participation"] == "ELEVATED"
        assert "anomaly_level" in metrics
        assert db.scalar("SELECT COUNT(*) FROM ai_calls") == 0
        assert db.scalar("SELECT COUNT(*) FROM specialist_findings") == 0
    finally:
        td.cleanup()


def test_micro_cycle_preserves_objective_arrow_style_volume_direction():
    td, root, db, repo = setup_repo()
    try:
        write_json(root / "data" / "microstructure_latest.json", {
            "generated_at": NOW.isoformat(), "signals": [micro_row()],
            "health": {"assets_requested": 1, "assets_analysed": 1, "unavailable_assets": []},
        })
        result = DeterministicBrainCore(repo, LegacySnapshotCollector(root)).run(CycleType.MICRO_5M, NOW)
        assert result.status == "COMPLETED"
        obs = {r["metric"]: json.loads(r["value_json"]) for r in db.query("SELECT metric,value_json FROM observation_records")}
        assert obs["micro_trend_alignment"] == "UP"
        assert obs["volume_flow_1m"] == "UP"
        assert obs["volume_flow_5m"] == "UP"
    finally:
        td.cleanup()


def test_unavailable_asset_makes_cycle_partial_not_complete():
    td, root, _, repo = setup_repo()
    try:
        write_json(root / "data" / "observer_latest.json", {
            "generated_at": NOW.isoformat(), "signals": [market_row("BTC")],
            "health": {"assets_requested": 2, "assets_analysed": 1, "unavailable_assets": ["COTI"]},
        })
        result = DeterministicBrainCore(repo, LegacySnapshotCollector(root)).run(CycleType.MARKET_15M, NOW)
        assert result.status == "PARTIAL"
        assert result.expected_assets == 2 and result.analysed_assets == 1
        assert result.failures["COTI"] == "source unavailable"
    finally:
        td.cleanup()


def test_stale_asset_is_not_counted_as_genuine_analysis():
    td, root, _, repo = setup_repo()
    try:
        stale = NOW - timedelta(hours=2)
        write_json(root / "data" / "observer_latest.json", {
            "generated_at": NOW.isoformat(), "signals": [market_row("BTC", stale)],
            "health": {"assets_requested": 1, "assets_analysed": 1, "unavailable_assets": []},
        })
        result = DeterministicBrainCore(repo, LegacySnapshotCollector(root)).run(CycleType.MARKET_15M, NOW)
        assert result.status == "PARTIAL"
        assert result.analysed_assets == 0
        assert "stale" in result.failures["BTC"]
    finally:
        td.cleanup()


def test_same_scheduled_cycle_is_retry_safe():
    td, root, db, repo = setup_repo()
    try:
        write_json(root / "data" / "observer_latest.json", {
            "generated_at": NOW.isoformat(), "signals": [market_row()],
            "health": {"assets_requested": 1, "assets_analysed": 1, "unavailable_assets": []},
        })
        core = DeterministicBrainCore(repo, LegacySnapshotCollector(root))
        first = core.run(CycleType.MARKET_15M, NOW)
        e1 = db.scalar("SELECT COUNT(*) FROM evidence_records")
        o1 = db.scalar("SELECT COUNT(*) FROM observation_records")
        second = core.run(CycleType.MARKET_15M, NOW)
        assert first.cycle_id == second.cycle_id
        assert db.scalar("SELECT COUNT(*) FROM brain_cycles") == 1
        assert db.scalar("SELECT COUNT(*) FROM evidence_records") == e1
        assert db.scalar("SELECT COUNT(*) FROM observation_records") == o1
    finally:
        td.cleanup()


def test_missing_snapshot_records_failed_cycle():
    td, root, db, repo = setup_repo()
    try:
        core = DeterministicBrainCore(repo, LegacySnapshotCollector(root))
        with pytest.raises(FileNotFoundError):
            core.run(CycleType.MARKET_15M, NOW)
        row = db.query("SELECT status,error FROM brain_cycles")[0]
        assert row["status"] == "FAILED"
        assert row["error"] == "collection failed"
    finally:
        td.cleanup()
