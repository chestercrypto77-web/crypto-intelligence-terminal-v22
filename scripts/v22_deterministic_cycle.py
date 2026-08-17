from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v22.brain.config import SETTINGS
from v22.contracts import CycleType
from v22.core import DeterministicBrainCore, LegacySnapshotCollector
from v22.storage import BrainRepository, Database


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one V22 Stage-2 deterministic Brain cycle")
    parser.add_argument("--cycle", choices=["5m", "15m"], required=True)
    parser.add_argument("--scheduled-at", help="ISO-8601 UTC time; defaults to now")
    parser.add_argument("--database-url", default=SETTINGS.database_url)
    args = parser.parse_args()

    scheduled = datetime.now(timezone.utc) if not args.scheduled_at else datetime.fromisoformat(args.scheduled_at.replace("Z", "+00:00"))
    cycle_type = CycleType.MICRO_5M if args.cycle == "5m" else CycleType.MARKET_15M
    db = Database(args.database_url); db.migrate()
    core = DeterministicBrainCore(BrainRepository(db), LegacySnapshotCollector(ROOT))
    result = core.run(cycle_type, scheduled)
    print(json.dumps(result.__dict__, indent=2, sort_keys=True))
    return 0 if result.status in {"COMPLETED", "PARTIAL"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
