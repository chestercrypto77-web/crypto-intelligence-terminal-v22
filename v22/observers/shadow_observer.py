from __future__ import annotations
from pathlib import Path
import json, time
ROOT=Path(__file__).resolve().parents[2]

def run_shadow(interval_seconds: int):
    source=ROOT/"data"/("microstructure_latest.json" if interval_seconds<=300 else "observer_latest.json")
    obj={}
    if source.exists():
        try: obj=json.loads(source.read_text(encoding="utf-8"))
        except Exception: obj={}
    rows=[]
    if isinstance(obj,dict):
        for key in ("records","signals","assets"):
            if isinstance(obj.get(key),list):
                rows=obj[key]; break
    requested=(obj.get("health") or {}).get("assets_requested") if isinstance(obj,dict) else None
    analysed=(obj.get("health") or {}).get("assets_analysed") if isinstance(obj,dict) else None
    return {
        "source_file":str(source.relative_to(ROOT)),
        "assets_requested":int(requested or len(rows)),
        "assets_analysed":int(analysed or len(rows)),
        "source_timestamp": obj.get("generated_at") or obj.get("updated_at") if isinstance(obj,dict) else None
    }
