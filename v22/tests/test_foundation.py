from pathlib import Path
import os, sqlite3, tempfile, time
from v22.storage.database import Database
from v22.brain.scheduler import due_slots
from v22.audit.watchdog import snapshot

def test_due_slots_marks_gap():
    slots=due_slots(0, 1200, 300)
    assert slots == [300.0,600.0,900.0,1200.0]

def test_db_migrate_and_persist():
    with tempfile.TemporaryDirectory() as td:
        db=Database("sqlite:///"+str(Path(td)/"x.db")); db.migrate()
        db.insert_event("supervisor_state",{"key":"x","value":"1","updated_at":time.time()})
        assert db.scalar("SELECT value FROM supervisor_state WHERE key=?",("x",))=="1"

def test_watchdog_truthful_without_heartbeats():
    with tempfile.TemporaryDirectory() as td:
        db=Database("sqlite:///"+str(Path(td)/"x.db")); db.migrate()
        snap=snapshot(db)
        assert snap["overall"]=="DEGRADED"
        assert all(x["state"]=="NO_HEARTBEAT" for x in snap["engines"])
