from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from v22 import __version__
from v22.contracts import CycleType
from v22.runtime.github_validation import ScheduleEventLedger, expected_slots, previous_slot
from v22.storage import Database


def main():
    now=datetime(2026,8,17,12,21,tzinfo=timezone.utc)
    with tempfile.TemporaryDirectory() as td:
        db=Database(f"sqlite:///{Path(td)/'brain.db'}"); db.migrate()
        ledger=ScheduleEventLedger(db)
        slot=previous_slot(now,CycleType.MICRO_5M)
        eid=ledger.start('stage8-smoke',slot,CycleType.MICRO_5M)
        ledger.finish(eid,status='SUCCEEDED',details={'smoke':True})
        result={
            'status':'passed',
            'version':__version__,
            '5m_previous_slot':slot.isoformat(),
            'one_hour_5m_slots':len(expected_slots(datetime(2026,8,17,12,0,tzinfo=timezone.utc),datetime(2026,8,17,12,59,tzinfo=timezone.utc),CycleType.MICRO_5M)),
            'one_hour_15m_slots':len(expected_slots(datetime(2026,8,17,12,0,tzinfo=timezone.utc),datetime(2026,8,17,12,59,tzinfo=timezone.utc),CycleType.MARKET_15M)),
            'schedule_events':db.scalar('SELECT COUNT(*) FROM runtime_schedule_events'),
            'ai_calls':db.scalar('SELECT COUNT(*) FROM ai_calls'),
        }
        assert result['one_hour_5m_slots']==12 and result['one_hour_15m_slots']==4 and result['schedule_events']==1 and result['ai_calls']==0
        print(json.dumps(result,indent=2))

if __name__=='__main__': main()
