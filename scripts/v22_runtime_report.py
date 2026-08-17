from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v22.runtime.github_validation import persist_report, validation_summary
from v22.storage import Database


def main() -> int:
    p=argparse.ArgumentParser(description="V22 GitHub free-runtime coverage report")
    p.add_argument("--window-hours", type=float, default=24.0)
    p.add_argument("--report-type", default="NIGHTLY_VALIDATION")
    p.add_argument("--grace-minutes", type=int, default=12)
    p.add_argument("--fail-on-stale", action="store_true")
    args=p.parse_args()
    url=os.getenv("DATABASE_URL","")
    if not url: raise SystemExit("DATABASE_URL secret is required")
    db=Database(url)
    if db.kind != "postgres": raise SystemExit("external Postgres/Neon DATABASE_URL is required")
    db.migrate()
    end=datetime.now(timezone.utc)-timedelta(minutes=max(0,args.grace_minutes))
    start=end-timedelta(hours=max(0.1,args.window_hours))
    summary=validation_summary(db,start,end)
    report_id=persist_report(db,args.report_type,start,end,summary)
    payload={"report_id":report_id,**summary.as_dict()}
    print(json.dumps(payload,indent=2,sort_keys=True))
    if args.fail_on_stale and (summary.missing_5m > 2 or summary.missing_15m > 1):
        return 2
    return 0

if __name__=="__main__": raise SystemExit(main())
