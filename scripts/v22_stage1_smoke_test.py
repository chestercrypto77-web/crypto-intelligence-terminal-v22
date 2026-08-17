from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v22.contracts import CoverageContract, CycleContract, CycleStatus, CycleType, DataQuality, EvidenceContract, ObservationContract, Provenance
from v22.storage import BrainRepository, Database


def main() -> int:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    with tempfile.TemporaryDirectory() as td:
        db = Database("sqlite:///" + str(Path(td) / "v22_stage1.db"))
        db.migrate()
        repo = BrainRepository(db)
        cycle = CycleContract(
            cycle_type=CycleType.MANUAL_TEST,
            scheduled_at=now,
            expected_assets=1,
            provenance=Provenance(brain_version="22.1.0", software_commit="smoke-test"),
        )
        stored = repo.create_cycle(cycle)
        duplicate = repo.create_cycle(CycleContract(
            cycle_type=CycleType.MANUAL_TEST,
            scheduled_at=now,
            expected_assets=1,
            provenance=cycle.provenance,
        ))
        assert stored["cycle_id"] == duplicate["cycle_id"]
        for status in (CycleStatus.STARTED, CycleStatus.COLLECTING):
            repo.transition_cycle(cycle.cycle_id, status)
        evidence = EvidenceContract(
            cycle_id=cycle.cycle_id, asset_id="BTC", metric="price_usd", value=1.0,
            source="synthetic", source_timestamp=now, retrieved_at=now,
        )
        evidence_id = repo.record_evidence(evidence)
        repo.transition_cycle(cycle.cycle_id, CycleStatus.VALIDATING)
        repo.transition_cycle(cycle.cycle_id, CycleStatus.CALCULATING)
        repo.record_observation(ObservationContract(
            cycle_id=cycle.cycle_id, asset_id="BTC", metric="test_change", value=0.0,
            observed_at=now, calculation="stage1_smoke_v1", evidence_ids=(evidence_id,),
        ))
        repo.upsert_coverage(CoverageContract(
            cycle_id=cycle.cycle_id, asset_id="BTC", evidence_collected=True,
            deterministic_completed=True, quality=DataQuality.GOOD,
        ))
        repo.transition_cycle(cycle.cycle_id, CycleStatus.PERSISTING)
        final = repo.finalise_cycle(cycle.cycle_id)
        assert final["status"] == "COMPLETED"
        print(json.dumps({
            "status": "passed",
            "cycle_status": final["status"],
            "idempotent_cycle": True,
            "evidence_records": db.scalar("SELECT COUNT(*) FROM evidence_records"),
            "observation_records": db.scalar("SELECT COUNT(*) FROM observation_records"),
            "coverage": repo.coverage_summary(cycle.cycle_id),
        }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
