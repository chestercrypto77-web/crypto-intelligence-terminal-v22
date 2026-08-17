from __future__ import annotations
import json
from v22.brain.config import SETTINGS
from v22.storage.database import Database
from v22.audit.watchdog import snapshot
def main():
    db=Database(SETTINGS.database_url); db.migrate()
    print(json.dumps(snapshot(db,SETTINGS.stale_factor),indent=2))
if __name__=="__main__": main()
