from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v22.contracts import CycleType
from v22.runtime.github_validation import previous_slot, run_cycle


def parse_at(raw: str | None, cycle_type: CycleType) -> datetime:
    if raw:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if value.tzinfo is None:
            raise ValueError("--scheduled-at must include timezone")
        return value.astimezone(timezone.utc)
    return previous_slot(datetime.now(timezone.utc), cycle_type)


def main() -> int:
    p = argparse.ArgumentParser(description="Run one V22 GitHub/Neon deterministic validation cycle")
    p.add_argument("--cycle", choices=("5m", "15m"), required=True)
    p.add_argument("--scheduled-at")
    p.add_argument("--workflow-name")
    args = p.parse_args()
    cycle_type = CycleType.MICRO_5M if args.cycle == "5m" else CycleType.MARKET_15M
    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise SystemExit("DATABASE_URL secret is required")
    scheduled_at = parse_at(args.scheduled_at, cycle_type)
    workflow_name = args.workflow_name or f"V22 GitHub {args.cycle} Validation"
    result = run_cycle(url, ROOT, cycle_type, scheduled_at, workflow_name)
    print(json.dumps({"scheduled_at": scheduled_at.isoformat(), **result}, indent=2, sort_keys=True, default=str))
    # PARTIAL is a truthful completed workflow, not a GitHub infrastructure failure.
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
