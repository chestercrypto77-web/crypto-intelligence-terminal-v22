from __future__ import annotations
import json, time

CRITICAL={"observer_1m":60,"observer_5m":300,"observer_15m":900,"supervisor":30}

def snapshot(db, stale_factor=2.2):
    now=time.time(); engines=[]; overall="HEALTHY"
    for engine,interval in CRITICAL.items():
        q=("SELECT started_at,status,evidence_class FROM engine_heartbeats WHERE engine=? ORDER BY started_at DESC LIMIT 1"
           if db.kind=="sqlite" else
           "SELECT started_at,status,evidence_class FROM engine_heartbeats WHERE engine=%s ORDER BY started_at DESC LIMIT 1")
        rows=db.query(q,(engine,))
        if not rows:
            state="NO_HEARTBEAT"; age=None
        else:
            r=rows[0]; age=now-float(r["started_at"])
            state="HEALTHY" if r["status"]=="SUCCESS" and age<=interval*stale_factor else "STALE"
        if state!="HEALTHY": overall="DEGRADED"
        engines.append({"engine":engine,"state":state,"age_seconds":age,"expected_seconds":interval})
    return {"generated_at":now,"overall":overall,"engines":engines}

def persist_incidents(db, snap):
    now=time.time()
    for e in snap["engines"]:
        if e["state"]=="HEALTHY": continue
        key=f'{e["engine"]}:{e["state"]}'
        q=("SELECT COUNT(*) FROM system_incidents WHERE incident_key=? AND status='OPEN'"
           if db.kind=="sqlite" else
           "SELECT COUNT(*) FROM system_incidents WHERE incident_key=%s AND status='OPEN'")
        if not db.scalar(q,(key,),0):
            db.insert_event("system_incidents",{
                "incident_key":key,"severity":"CRITICAL" if e["engine"] in {"observer_1m","supervisor"} else "WARNING",
                "component":e["engine"],"opened_at":now,"resolved_at":None,"status":"OPEN",
                "message":f'{e["engine"]} is {e["state"]}',"details_json":json.dumps(e)
            })
