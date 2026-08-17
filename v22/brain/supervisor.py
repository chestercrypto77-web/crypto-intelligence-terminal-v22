from __future__ import annotations
import argparse, json, signal, time, uuid
from v22.brain.config import SETTINGS
from v22.storage.database import Database
from v22.brain.heartbeat import Heartbeat
from v22.brain.scheduler import due_slots
from v22.brain.recovery import record_gap
from v22.observers.shadow_observer import run_shadow
from v22.adapters.v21_bridge import import_snapshot
from v22.audit.watchdog import snapshot, persist_incidents

STOP=False
def _stop(*_):
    global STOP; STOP=True

def last_success(db, engine):
    q=("SELECT scheduled_for FROM observation_runs WHERE engine=? AND status='SUCCESS' ORDER BY scheduled_for DESC LIMIT 1"
       if db.kind=="sqlite" else
       "SELECT scheduled_for FROM observation_runs WHERE engine=%s AND status='SUCCESS' ORDER BY scheduled_for DESC LIMIT 1")
    rows=db.query(q,(engine,))
    return float(rows[0]["scheduled_for"]) if rows else None

def run_observation(db, engine, interval, slot, evidence_class):
    hb=Heartbeat(db,engine,SETTINGS.instance_id)
    start=time.time()
    with hb.run(slot,evidence_class) as run_id:
        result=run_shadow(interval)
        db.insert_event("observation_runs",{
            "run_id":run_id,"engine":engine,"interval_seconds":interval,"scheduled_for":slot,
            "started_at":start,"completed_at":time.time(),"status":"SUCCESS","evidence_class":evidence_class,
            "assets_requested":result["assets_requested"],"assets_analysed":result["assets_analysed"],
            "error":None,"source":result["source_file"]
        })

def cycle(db):
    now=time.time()
    with Heartbeat(db,"supervisor",SETTINGS.instance_id).run(now,"LIVE"):
        if SETTINGS.v21_bridge_enabled: import_snapshot(db)
        schedules=[("observer_1m",SETTINGS.one_minute_seconds),
                   ("observer_5m",SETTINGS.five_minute_seconds),
                   ("observer_15m",SETTINGS.fifteen_minute_seconds)]
        for engine,interval in schedules:
            slots=due_slots(last_success(db,engine),now,interval)
            record_gap(db,engine,interval,slots)
            # historical slots are explicitly reconstructed; current slot is LIVE.
            for slot in slots:
                klass="LIVE" if slot==slots[-1] else "RECONSTRUCTED"
                run_observation(db,engine,interval,slot,klass)
        snap=snapshot(db,SETTINGS.stale_factor); persist_incidents(db,snap)
        return snap

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--once",action="store_true")
    args=ap.parse_args()
    signal.signal(signal.SIGTERM,_stop); signal.signal(signal.SIGINT,_stop)
    db=Database(SETTINGS.database_url); db.migrate()
    if args.once:
        print(json.dumps(cycle(db),indent=2)); return 0
    print(json.dumps({"v22":"22.0.0","mode":SETTINGS.mode,"instance":SETTINGS.instance_id,"status":"STARTING"}))
    while not STOP:
        try: cycle(db)
        except Exception as e:
            print(json.dumps({"status":"CYCLE_FAILED","error":repr(e)}),flush=True)
        end=time.time()+SETTINGS.poll_seconds
        while not STOP and time.time()<end: time.sleep(min(.25,end-time.time()))
    print(json.dumps({"status":"STOPPED"})); return 0
if __name__=="__main__": raise SystemExit(main())
