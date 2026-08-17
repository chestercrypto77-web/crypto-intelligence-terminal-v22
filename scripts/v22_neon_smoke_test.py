from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v22.contracts import CycleContract, CycleType, Provenance
from v22.storage import BrainRepository, Database


def main() -> int:
    parser = argparse.ArgumentParser(description="V22.6 Neon durable-memory smoke test")
    parser.add_argument("--allow-sqlite", action="store_true", help="permit local SQLite rehearsal")
    args = parser.parse_args()

    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        print("FAIL: DATABASE_URL is not set", file=sys.stderr)
        return 2
    db = Database(url)
    if db.kind != "postgres" and not args.allow_sqlite:
        print("FAIL: live-memory smoke requires a Postgres/Neon DATABASE_URL", file=sys.stderr)
        return 2

    health = db.healthcheck()
    db.migrate()
    slot = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    marker = uuid.uuid4().hex[:12]
    cycle = CycleContract(
        cycle_type=CycleType.MANUAL_TEST,
        scheduled_at=slot,
        expected_assets=0,
        workflow_id=f"v22.6-neon-smoke-{marker}",
        provenance=Provenance(brain_version="22.6.0", software_commit=os.getenv("GITHUB_SHA", "manual-smoke")),
    )
    repo = BrainRepository(db)
    stored = repo.create_cycle(cycle)

    # Recreate both objects to prove the durable record is not process/object memory.
    del repo, db
    db2 = Database(url)
    repo2 = BrainRepository(db2)
    recovered = repo2.get_cycle_by_key(cycle.cycle_key)
    if not recovered or str(recovered["cycle_id"]) != str(stored["cycle_id"]):
        print("FAIL: cycle did not survive reconnect", file=sys.stderr)
        return 1

    print("PASS: V22.6 durable-memory reconnect smoke")
    print(f"backend={health.kind} pooled_endpoint={health.pooled_endpoint} server_version={health.server_version}")
    print(f"cycle_id={recovered['cycle_id']} status={recovered['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
