from __future__ import annotations
import time

def floor_slot(ts: float, interval: int) -> float:
    return float(int(ts // interval) * interval)

def due_slots(last_success: float | None, now: float, interval: int, max_backfill: int=500):
    current=floor_slot(now, interval)
    if last_success is None:
        return [current]
    first=floor_slot(last_success, interval)+interval
    if first>current: return []
    count=int((current-first)//interval)+1
    if count>max_backfill:
        first=current-(max_backfill-1)*interval
    return [first+i*interval for i in range(int((current-first)//interval)+1)]
