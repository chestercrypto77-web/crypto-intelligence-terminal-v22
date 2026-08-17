from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile

import pytest

from v22.contracts import CycleContract, CycleStatus, CycleType, Provenance
from v22.core import DeterministicBrainCore, LegacySnapshotCollector
from v22.failure import FailureStage, FaultInjector
from v22.storage import BrainRepository, Database


NOW = datetime(2026, 8, 17, 5, 30, tzinfo=timezone.utc)


def setup_repo():
    td = tempfile.TemporaryDirectory()
    root = Path(td.name)
    (root / "data").mkdir()
    db = Database("sqlite:///" + str(root / "brain.db")); db.migrate()
    return td, root, db, BrainRepository(db)


def write_json(path: Path, payload: dict):
    path.write_text(json.dumps(payload), encoding="utf-8")


def row(symbol="BTC", ts=NOW):
    return {
        "symbol": symbol, "name": symbol, "data_source": "fixture 15m",
        "candle_time": ts.isoformat(), "price": 65000,
        "return_15m": 0.5, "return_1h": 1.1, "return_4h": 2.3, "return_24h": 3.5,
        "rvol": 1.6, "rvol_delta": 0.4, "rsi": 61, "rsi_delta": 3,
        "macd_histogram": 1.2, "macd_delta": 0.3, "breakout": False, "breakdown": False,
    }


def snapshot(root: Path, rows=None, requested=None, unavailable=None):
    rows = rows or [row()]
    requested = requested if requested is not None else len(rows)
    write_json(root / "data" / "observer_latest.json", {
        "generated_at": NOW.isoformat(),
        "signals": rows,
        "health": {"assets_requested": requested, "assets_analysed": len(rows), "unavailable_assets": unavailable or []},
    })


def failures(db):
    return db.query("SELECT * FROM brain_failure_events ORDER BY occurred_at, failure_id")


def test_missing_source_is_failed_and_audited():
    td, root, db, repo = setup_repo()
    try:
        with pytest.raises(FileNotFoundError):
            DeterministicBrainCore(repo, LegacySnapshotCollector(root)).run(CycleType.MARKET_15M, NOW)
        cycle = db.query("SELECT status,error FROM brain_cycles")[0]
        assert cycle["status"] == "FAILED"
        assert "collection failed" in cycle["error"]
        events = failures(db)
        assert len(events) == 1 and events[0]["stage"] == "COLLECTION"
        assert events[0]["error_type"] == "FileNotFoundError"
    finally:
        td.cleanup()


def test_malformed_json_is_failed_and_audited():
    td, root, db, repo = setup_repo()
    try:
        (root / "data" / "observer_latest.json").write_text('{"broken":', encoding="utf-8")
        with pytest.raises(ValueError):
            DeterministicBrainCore(repo, LegacySnapshotCollector(root)).run(CycleType.MARKET_15M, NOW)
        assert db.scalar("SELECT status FROM brain_cycles") == "FAILED"
        event = failures(db)[0]
        assert event["stage"] == "COLLECTION"
        assert "invalid JSON" in event["message"]
    finally:
        td.cleanup()


def test_stale_source_is_partial_not_complete_and_failure_is_visible():
    td, root, db, repo = setup_repo()
    try:
        snapshot(root, [row(ts=NOW - timedelta(hours=2))])
        result = DeterministicBrainCore(repo, LegacySnapshotCollector(root)).run(CycleType.MARKET_15M, NOW)
        assert result.status == "PARTIAL" and result.analysed_assets == 0
        assert result.failure_events == 1
        event = failures(db)[0]
        assert event["stage"] == "VALIDATION" and event["asset_id"] == "BTC"
    finally:
        td.cleanup()


def test_partial_coverage_records_unavailable_asset_failure():
    td, root, db, repo = setup_repo()
    try:
        snapshot(root, [row("BTC")], requested=2, unavailable=["COTI"])
        result = DeterministicBrainCore(repo, LegacySnapshotCollector(root)).run(CycleType.MARKET_15M, NOW)
        assert result.status == "PARTIAL" and result.analysed_assets == 1
        event = [x for x in failures(db) if x["asset_id"] == "COTI"][0]
        assert event["stage"] == "COLLECTION" and "unavailable" in event["message"]
    finally:
        td.cleanup()


def test_calculation_failure_cannot_claim_asset_analysed():
    td, root, db, repo = setup_repo()
    try:
        snapshot(root)
        fault = FaultInjector(FailureStage.CALCULATION, asset_id="BTC")
        result = DeterministicBrainCore(repo, LegacySnapshotCollector(root), fault_injector=fault).run(CycleType.MARKET_15M, NOW)
        assert result.status == "PARTIAL" and result.analysed_assets == 0
        coverage = db.query("SELECT * FROM cycle_asset_coverage")[0]
        assert not coverage["deterministic_completed"]
        event = failures(db)[0]
        assert event["stage"] == "CALCULATION" and event["asset_id"] == "BTC"
    finally:
        td.cleanup()


def test_observation_database_write_failure_leaves_cycle_partial():
    td, root, db, repo = setup_repo()
    try:
        snapshot(root)
        fault = FaultInjector(FailureStage.OBSERVATION_PERSIST, asset_id="BTC", exc_factory=lambda: OSError("simulated database write failure"))
        result = DeterministicBrainCore(repo, LegacySnapshotCollector(root), fault_injector=fault).run(CycleType.MARKET_15M, NOW)
        assert result.status == "PARTIAL" and result.analysed_assets == 0
        assert db.scalar("SELECT COUNT(*) FROM evidence_records") > 0
        event = failures(db)[0]
        assert event["stage"] == "OBSERVATION_PERSIST"
        assert event["retryable"] == 1
        assert "database write failure" in event["message"]
    finally:
        td.cleanup()


def test_finalisation_failure_marks_whole_cycle_failed():
    td, root, db, repo = setup_repo()
    try:
        snapshot(root)
        fault = FaultInjector(FailureStage.FINALISE, exc_factory=lambda: OSError("simulated finalisation outage"))
        with pytest.raises(OSError):
            DeterministicBrainCore(repo, LegacySnapshotCollector(root), fault_injector=fault).run(CycleType.MARKET_15M, NOW)
        assert db.scalar("SELECT status FROM brain_cycles") == "FAILED"
        event = failures(db)[0]
        assert event["stage"] == "FINALISE" and event["severity"] == "CRITICAL"
    finally:
        td.cleanup()


def test_in_progress_duplicate_is_rejected_without_second_cycle():
    td, root, db, repo = setup_repo()
    try:
        snapshot(root)
        cycle = CycleContract(
            cycle_type=CycleType.MARKET_15M,
            scheduled_at=NOW,
            expected_assets=1,
            provenance=Provenance(brain_version="22.3.0", schema_version="003"),
        )
        stored = repo.create_cycle(cycle)
        repo.transition_cycle(stored["cycle_id"], CycleStatus.STARTED)
        with pytest.raises(RuntimeError, match="already in progress"):
            DeterministicBrainCore(repo, LegacySnapshotCollector(root)).run(CycleType.MARKET_15M, NOW)
        assert db.scalar("SELECT COUNT(*) FROM brain_cycles") == 1
        event = failures(db)[0]
        assert event["stage"] == "DUPLICATE_EXECUTION" and event["severity"] == "WARNING"
    finally:
        td.cleanup()


def test_same_failure_is_retry_safe_in_failure_ledger():
    td, root, db, repo = setup_repo()
    try:
        snapshot(root)
        cycle = CycleContract(
            cycle_type=CycleType.MARKET_15M,
            scheduled_at=NOW,
            expected_assets=1,
            provenance=Provenance(brain_version="22.3.0", schema_version="003"),
        )
        stored = repo.create_cycle(cycle)
        repo.transition_cycle(stored["cycle_id"], CycleStatus.STARTED)
        core = DeterministicBrainCore(repo, LegacySnapshotCollector(root))
        for _ in range(2):
            with pytest.raises(RuntimeError):
                core.run(CycleType.MARKET_15M, NOW)
        assert db.scalar("SELECT COUNT(*) FROM brain_failure_events") == 1
    finally:
        td.cleanup()


def test_failure_engine_does_not_activate_ai():
    td, root, db, repo = setup_repo()
    try:
        snapshot(root)
        fault = FaultInjector(FailureStage.CALCULATION)
        DeterministicBrainCore(repo, LegacySnapshotCollector(root), fault_injector=fault).run(CycleType.MARKET_15M, NOW)
        assert db.scalar("SELECT COUNT(*) FROM ai_calls") == 0
        assert db.scalar("SELECT COUNT(*) FROM specialist_findings") == 0
    finally:
        td.cleanup()
