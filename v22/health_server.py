from __future__ import annotations
import json, os
from http.server import BaseHTTPRequestHandler, HTTPServer
from v22.brain.config import SETTINGS
from v22.storage.database import Database
from v22.audit.watchdog import snapshot
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/health","/status"):
            self.send_response(404); self.end_headers(); return
        try:
            db=Database(SETTINGS.database_url); db.migrate(); snap=snapshot(db,SETTINGS.stale_factor)
            body=json.dumps(snap).encode()
            self.send_response(200 if self.path=="/status" or snap["overall"]=="HEALTHY" else 503)
        except Exception as e:
            body=json.dumps({"overall":"FAILED","error":repr(e)}).encode(); self.send_response(503)
        self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(body)
def main():
    port=int(os.getenv("PORT","10000")); HTTPServer(("0.0.0.0",port),H).serve_forever()
if __name__=="__main__": main()
