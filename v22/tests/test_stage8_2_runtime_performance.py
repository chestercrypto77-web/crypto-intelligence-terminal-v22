from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from v22.contracts import CoverageContract, CycleContract, CycleStatus, CycleType, DataQuality, Provenance
from v22.core import DeterministicBrainCore
from v22.core.sources import CollectionBatch, CollectedAsset, CollectedMetric
from v22.storage import BrainRepository, Database

UTC = timezone.utc


class CountingDatabase(Database):
    def __init__(self, url: str):
        super().__init__(url)
        self.opens = 0

    def _open_connection(self, *, autocommit: bool = False):
        self.opens += 1
        return super()._open_connection(autocommit=autocommit)


def test_bounded_session_reuses_one_physical_connection(tmp_path):
    db = CountingDatabase(f"sqlite:///{tmp_path/'session.db'}")
    db.execute("CREATE TABLE t(v INTEGER)")
    before = db.opens
    with db.session():
        for i in range(12):
            db.execute("INSERT INTO t(v) VALUES (?)", (i,))
        assert db.scalar("SELECT COUNT(*) FROM t") == 12
    assert db.opens - before == 1
    assert db.scalar("SELECT COUNT(*) FROM t") == 12


def _asset(asset_id: str, at: datetime) -> CollectedAsset:
    metrics = (
        CollectedMetric("price_usd", 100.0, at, "USD"),
        CollectedMetric("return_1m_5bar_pct", 1.0, at, "%"),
        CollectedMetric("return_5m_5bar_pct", 2.0, at, "%"),
        CollectedMetric("relative_volume_1m", 1.2, at, "x"),
        CollectedMetric("relative_volume_delta_1m", 0.1, at, "x"),
        CollectedMetric("relative_volume_5m", 1.3, at, "x"),
        CollectedMetric("relative_volume_delta_5m", 0.1, at, "x"),
        CollectedMetric("rsi_1m", 55.0, at),
        CollectedMetric("rsi_5m", 54.0, at),
        CollectedMetric("macd_1m", 0.2, at),
        CollectedMetric("macd_5m", 0.1, at),
        CollectedMetric("ema9_1m", 101.0, at, "USD"),
        CollectedMetric("ema21_1m", 99.0, at, "USD"),
        CollectedMetric("ema9_5m", 100.5, at, "USD"),
        CollectedMetric("ema21_5m", 99.5, at, "USD"),
        CollectedMetric("atr_1m_pct", 0.5, at, "%"),
        CollectedMetric("atr_5m_pct", 0.7, at, "%"),
        CollectedMetric("breakout_5m", False, at),
        CollectedMetric("breakdown_5m", False, at),
    )
    return CollectedAsset(asset_id, "fixture", at, metrics)


class FixtureCollector:
    def __init__(self, assets):
        self.assets = tuple(assets)

    def collect(self, cycle_type, scheduled_at):
        return CollectionBatch(
            source_file="fixture",
            generated_at=scheduled_at,
            requested_assets=tuple(a.asset_id for a in self.assets),
            assets=self.assets,
            unavailable_assets=(),
            source_health={"fixture": True},
        )


def test_soft_deadline_finalises_truthfully_instead_of_sticking(tmp_path):
    db = Database(f"sqlite:///{tmp_path/'deadline.db'}")
    db.migrate()
    at = datetime.now(UTC).replace(microsecond=0)
    core = DeterministicBrainCore(BrainRepository(db), FixtureCollector([_asset("BTC", at), _asset("ETH", at)]))
    result = core.run(CycleType.MICRO_5M, at, soft_deadline_seconds=0.000001)
    assert result.status == CycleStatus.PARTIAL.value
    row = BrainRepository(db).get_cycle(result.cycle_id)
    assert row["completed_at"] is not None
    assert row["status"] == CycleStatus.PARTIAL.value


def test_progress_is_visible_before_finalisation(tmp_path):
    db = Database(f"sqlite:///{tmp_path/'progress.db'}")
    db.migrate()
    repo = BrainRepository(db)
    at = datetime.now(UTC).replace(microsecond=0)
    cycle = CycleContract(cycle_type=CycleType.MICRO_5M, scheduled_at=at, expected_assets=2, provenance=Provenance(brain_version="test"))
    row = repo.create_cycle(cycle)
    cid = row["cycle_id"]
    repo.transition_cycle(cid, CycleStatus.STARTED)
    repo.transition_cycle(cid, CycleStatus.COLLECTING)
    repo.transition_cycle(cid, CycleStatus.VALIDATING)
    repo.transition_cycle(cid, CycleStatus.CALCULATING)
    repo.upsert_coverage(CoverageContract(cycle_id=cid, asset_id="BTC", evidence_collected=True, deterministic_completed=True, quality=DataQuality.GOOD))
    assert repo.refresh_cycle_progress(cid) == 1
    assert int(repo.get_cycle(cid)["analysed_assets"]) == 1


def test_stale_calculating_cycle_is_reconciled_from_coverage(tmp_path):
    db = Database(f"sqlite:///{tmp_path/'stale.db'}")
    db.migrate()
    repo = BrainRepository(db)
    now = datetime.now(UTC).replace(microsecond=0)
    old = now - timedelta(minutes=30)
    cycle = CycleContract(cycle_type=CycleType.MICRO_5M, scheduled_at=old, expected_assets=2, provenance=Provenance(brain_version="test"))
    cid = repo.create_cycle(cycle)["cycle_id"]
    repo.transition_cycle(cid, CycleStatus.STARTED, at=old)
    repo.transition_cycle(cid, CycleStatus.COLLECTING, at=old)
    repo.transition_cycle(cid, CycleStatus.VALIDATING, at=old)
    repo.transition_cycle(cid, CycleStatus.CALCULATING, at=old)
    repo.upsert_coverage(CoverageContract(cycle_id=cid, asset_id="BTC", evidence_collected=True, deterministic_completed=True, quality=DataQuality.GOOD))
    repaired = repo.reconcile_stale_cycles(now - timedelta(minutes=8))
    assert any(r["cycle_id"] == cid for r in repaired)
    row = repo.get_cycle(cid)
    assert row["status"] == CycleStatus.PARTIAL.value
    assert int(row["analysed_assets"]) == 1
    assert row["completed_at"] is not None
