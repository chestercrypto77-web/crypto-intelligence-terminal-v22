from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import uuid

import pytest

from v22.contracts import (
    CoverageContract,
    CycleContract,
    CycleStatus,
    CycleType,
    DataQuality,
    EvidenceContract,
    FindingContract,
    ObservationContract,
    Provenance,
)
from v22.storage import BrainRepository, Database


NOW = datetime(2026, 8, 17, 4, 30, tzinfo=timezone.utc)


def make_repo():
    td = tempfile.TemporaryDirectory()
    db = Database("sqlite:///" + str(Path(td.name) / "brain.db"))
    db.migrate()
    return td, db, BrainRepository(db)


def make_cycle(expected_assets: int = 1):
    return CycleContract(
        cycle_type=CycleType.MICRO_5M,
        scheduled_at=NOW,
        expected_assets=expected_assets,
        provenance=Provenance(brain_version="22.1.0", software_commit="test"),
    )


def test_all_stage1_tables_are_created():
    td, db, _ = make_repo()
    try:
        names = {r["name"] for r in db.query("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {
            "brain_cycles", "evidence_records", "observation_records", "cycle_asset_coverage",
            "specialist_findings", "synthesis_records", "episodes", "episode_outcomes",
            "ai_calls", "semantic_memory_queue",
        }
        assert required <= names
    finally:
        td.cleanup()


def test_cycle_creation_is_idempotent_by_schedule_slot():
    td, db, repo = make_repo()
    try:
        first = make_cycle()
        second = make_cycle()
        stored_a = repo.create_cycle(first)
        stored_b = repo.create_cycle(second)
        assert stored_a["cycle_id"] == stored_b["cycle_id"]
        assert db.scalar("SELECT COUNT(*) FROM brain_cycles") == 1
    finally:
        td.cleanup()


def test_cycle_state_machine_rejects_skips():
    td, _, repo = make_repo()
    try:
        cycle = make_cycle()
        repo.create_cycle(cycle)
        with pytest.raises(ValueError):
            repo.transition_cycle(cycle.cycle_id, CycleStatus.COMPLETED)
        repo.transition_cycle(cycle.cycle_id, CycleStatus.STARTED)
        repo.transition_cycle(cycle.cycle_id, CycleStatus.COLLECTING)
        assert repo.get_cycle(cycle.cycle_id)["status"] == "COLLECTING"
    finally:
        td.cleanup()


def test_evidence_write_is_retry_safe():
    td, db, repo = make_repo()
    try:
        cycle = make_cycle()
        repo.create_cycle(cycle)
        evidence_a = EvidenceContract(
            cycle_id=cycle.cycle_id,
            asset_id="BTC",
            metric="price_usd",
            value=65000.0,
            source="test-feed",
            source_timestamp=NOW,
            retrieved_at=NOW,
        )
        evidence_b = EvidenceContract(
            cycle_id=cycle.cycle_id,
            asset_id="BTC",
            metric="price_usd",
            value=65000.0,
            source="test-feed",
            source_timestamp=NOW,
            retrieved_at=NOW,
        )
        id_a = repo.record_evidence(evidence_a)
        id_b = repo.record_evidence(evidence_b)
        assert id_a == id_b
        assert db.scalar("SELECT COUNT(*) FROM evidence_records") == 1
    finally:
        td.cleanup()


def test_observation_references_evidence_and_is_retry_safe():
    td, db, repo = make_repo()
    try:
        cycle = make_cycle()
        repo.create_cycle(cycle)
        evidence = EvidenceContract(
            cycle_id=cycle.cycle_id,
            asset_id="ETH",
            metric="volume_usd",
            value=1000,
            source="test-feed",
            source_timestamp=NOW,
            retrieved_at=NOW,
        )
        evidence_id = repo.record_evidence(evidence)
        observation = ObservationContract(
            cycle_id=cycle.cycle_id,
            asset_id="ETH",
            metric="volume_change_5m_pct",
            value=18.2,
            observed_at=NOW,
            calculation="volume_change_v1",
            evidence_ids=(evidence_id,),
        )
        first = repo.record_observation(observation)
        second = repo.record_observation(observation)
        assert first == second
        assert db.scalar("SELECT COUNT(*) FROM observation_records") == 1
    finally:
        td.cleanup()


def test_completion_requires_genuine_asset_coverage():
    td, _, repo = make_repo()
    try:
        cycle = make_cycle(expected_assets=2)
        repo.create_cycle(cycle)
        for state in (
            CycleStatus.STARTED, CycleStatus.COLLECTING, CycleStatus.VALIDATING,
            CycleStatus.CALCULATING, CycleStatus.PERSISTING,
        ):
            repo.transition_cycle(cycle.cycle_id, state)
        repo.upsert_coverage(CoverageContract(
            cycle_id=cycle.cycle_id,
            asset_id="BTC",
            evidence_collected=True,
            deterministic_completed=True,
            quality=DataQuality.GOOD,
        ))
        repo.upsert_coverage(CoverageContract(
            cycle_id=cycle.cycle_id,
            asset_id="ETH",
            evidence_collected=True,
            deterministic_completed=False,
            quality=DataQuality.PARTIAL,
            failure_reason="missing source",
        ))
        final = repo.finalise_cycle(cycle.cycle_id)
        assert final["status"] == "PARTIAL"
        assert final["analysed_assets"] == 1
    finally:
        td.cleanup()


def test_completed_cycle_requires_full_coverage():
    td, _, repo = make_repo()
    try:
        cycle = make_cycle(expected_assets=2)
        repo.create_cycle(cycle)
        for state in (
            CycleStatus.STARTED, CycleStatus.COLLECTING, CycleStatus.VALIDATING,
            CycleStatus.CALCULATING, CycleStatus.PERSISTING,
        ):
            repo.transition_cycle(cycle.cycle_id, state)
        for asset in ("BTC", "ETH"):
            repo.upsert_coverage(CoverageContract(
                cycle_id=cycle.cycle_id,
                asset_id=asset,
                evidence_collected=True,
                deterministic_completed=True,
                quality=DataQuality.GOOD,
            ))
        final = repo.finalise_cycle(cycle.cycle_id)
        assert final["status"] == "COMPLETED"
        assert final["analysed_assets"] == 2
    finally:
        td.cleanup()


def test_ai_finding_without_evidence_is_rejected():
    cycle_id = str(uuid.uuid4())
    with pytest.raises(ValueError):
        FindingContract(
            cycle_id=cycle_id,
            specialist="Momentum",
            claim="Acceleration detected",
            evidence_ids=(),
            created_at=NOW,
            provenance=Provenance(brain_version="22.1.0"),
        )


def test_naive_timestamps_are_rejected():
    with pytest.raises(ValueError):
        CycleContract(
            cycle_type=CycleType.MICRO_5M,
            scheduled_at=datetime(2026, 8, 17, 4, 30),
            provenance=Provenance(brain_version="22.1.0"),
        )


def test_database_transaction_rolls_back_on_failure():
    td, db, _ = make_repo()
    try:
        try:
            with db.connect() as conn:
                conn.execute("INSERT INTO supervisor_state(key,value,updated_at) VALUES (?,?,?)", ("rollback", "1", 1.0))
                raise RuntimeError("forced failure")
        except RuntimeError:
            pass
        assert db.scalar("SELECT COUNT(*) FROM supervisor_state WHERE key=?", ("rollback",)) == 0
    finally:
        td.cleanup()
