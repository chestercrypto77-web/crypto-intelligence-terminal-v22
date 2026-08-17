from __future__ import annotations
import json, time

def record_gap(db, engine, interval, slots):
    if len(slots)<=1: return 0
    missing=slots[:-1]
    if not missing: return 0
    db.insert_event("observation_gaps",{
        "engine":engine,"interval_seconds":interval,"gap_start":missing[0],
        "gap_end":missing[-1],"missing_intervals":len(missing),"recovery_status":"DETECTED",
        "detected_at":time.time(),"details_json":json.dumps({"policy":"do not relabel as LIVE"})
    })
    return len(missing)
