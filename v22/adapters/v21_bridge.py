from __future__ import annotations
from pathlib import Path
import hashlib, json, time

ROOT=Path(__file__).resolve().parents[2]
SOURCES=[
 ("data/microstructure_latest.json","5m Microstructure"),
 ("data/observer_latest.json","15m Observer"),
 ("data/move_phase_intelligence.json","Move Phase"),
 ("data/committee_latest.json","Investment Committee"),
 ("data/active_trade_casefiles.json","Active Trade Casefiles"),
 ("data/learning_experience_store.json","Experience Store"),
]
def _hash(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def _stamp(obj):
    if isinstance(obj,dict):
        return obj.get("updated_at") or obj.get("generated_at") or obj.get("recorded_at")
    return None
def _count(obj):
    if isinstance(obj,list): return len(obj)
    if isinstance(obj,dict):
        for k in ("records","signals","positions","experiences","assets"):
            if isinstance(obj.get(k),list): return len(obj[k])
    return 1 if obj else 0

def import_snapshot(db):
    imported=[]
    for rel,label in SOURCES:
        p=ROOT/rel
        if not p.exists(): continue
        try: obj=json.loads(p.read_text(encoding="utf-8"))
        except Exception: continue
        h=_hash(p)
        q="SELECT COUNT(*) FROM v21_bridge_events WHERE source_file=? AND source_hash=?" if db.kind=="sqlite" else "SELECT COUNT(*) FROM v21_bridge_events WHERE source_file=%s AND source_hash=%s"
        if db.scalar(q,(rel,h),0): continue
        db.insert_event("v21_bridge_events",{
            "imported_at":time.time(),"source_file":rel,"source_timestamp":_stamp(obj),
            "source_hash":h,"record_count":_count(obj),
            "details_json":json.dumps({"label":label})
        })
        imported.append(rel)
    return imported
