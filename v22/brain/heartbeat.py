from __future__ import annotations
import json, time, uuid
from contextlib import contextmanager

class Heartbeat:
    def __init__(self, db, engine, instance_id):
        self.db=db; self.engine=engine; self.instance_id=instance_id

    @contextmanager
    def run(self, scheduled_for=None, evidence_class="LIVE", details=None):
        run_id=str(uuid.uuid4()); start=time.time()
        self.db.insert_event("engine_heartbeats",{
            "run_id":run_id,"engine":self.engine,"instance_id":self.instance_id,"status":"RUNNING",
            "evidence_class":evidence_class,"scheduled_for":scheduled_for,"started_at":start,
            "completed_at":None,"duration_ms":None,"details_json":json.dumps(details or {})
        })
        try:
            yield run_id
        except Exception as e:
            end=time.time()
            self.db.execute("UPDATE engine_heartbeats SET status=?,completed_at=?,duration_ms=?,details_json=? WHERE run_id=?" if self.db.kind=="sqlite" else
                            "UPDATE engine_heartbeats SET status=%s,completed_at=%s,duration_ms=%s,details_json=%s WHERE run_id=%s",
                            ("FAILED",end,int((end-start)*1000),json.dumps({"error":repr(e)}),run_id))
            raise
        else:
            end=time.time()
            self.db.execute("UPDATE engine_heartbeats SET status=?,completed_at=?,duration_ms=? WHERE run_id=?" if self.db.kind=="sqlite" else
                            "UPDATE engine_heartbeats SET status=%s,completed_at=%s,duration_ms=%s WHERE run_id=%s",
                            ("SUCCESS",end,int((end-start)*1000),run_id))
