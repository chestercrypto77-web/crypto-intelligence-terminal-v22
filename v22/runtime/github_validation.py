from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from typing import Any
import uuid

from v22.contracts import CycleType
from v22.core import DeterministicBrainCore, LiveEvidenceCollector
from v22.storage import BrainRepository, Database

UTC = timezone.utc
SCHEDULES = {
    CycleType.MICRO_5M: (5, 4),      # :04, :09, :14 ... :59
    CycleType.MARKET_15M: (15, 7),   # :07, :22, :37, :52
}


def utcnow() -> datetime:
    return datetime.now(UTC)


def iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat()


def previous_slot(now: datetime, cycle_type: CycleType) -> datetime:
    """Return the most recent nominal GitHub schedule slot, never a future slot."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    cadence, offset = SCHEDULES[cycle_type]
    now = now.astimezone(UTC).replace(second=0, microsecond=0)
    minute = now.minute
    candidates = [m for m in range(offset, 60, cadence) if m <= minute]
    if candidates:
        return now.replace(minute=max(candidates))
    prev = now - timedelta(hours=1)
    return prev.replace(minute=max(range(offset, 60, cadence)))


def expected_slots(start: datetime, end: datetime, cycle_type: CycleType) -> list[datetime]:
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("window timestamps must be timezone-aware")
    if end < start:
        return []
    cadence, offset = SCHEDULES[cycle_type]
    cursor = start.astimezone(UTC).replace(second=0, microsecond=0)
    cursor -= timedelta(minutes=cadence + 1)
    cursor = previous_slot(cursor + timedelta(minutes=cadence + 1), cycle_type)
    while cursor < start:
        cursor += timedelta(minutes=cadence)
    out = []
    while cursor <= end:
        if cursor.minute in range(offset, 60, cadence):
            out.append(cursor)
        cursor += timedelta(minutes=cadence)
    return out


def _ph(db: Database) -> str:
    return "?" if db.kind == "sqlite" else "%s"


def _json(db: Database, value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _require_external_database(db: Database) -> None:
    if db.kind != "postgres":
        raise RuntimeError("V22 GitHub validation runtime requires external PostgreSQL/Neon DATABASE_URL; SQLite is refused")


class ScheduleEventLedger:
    def __init__(self, db: Database):
        self.db = db

    def start(self, workflow_name: str, scheduled_at: datetime, cycle_type: CycleType | None) -> str:
        event_key = f"{workflow_name}:{iso(scheduled_at)}"
        existing = self.db.query(
            f"SELECT event_id FROM runtime_schedule_events WHERE event_key={_ph(self.db)}",
            (event_key,),
        )
        run_id = os.getenv("GITHUB_RUN_ID") or "local"
        attempt = os.getenv("GITHUB_RUN_ATTEMPT") or "1"
        if existing:
            event_id = str(existing[0]["event_id"])
            sql = (
                "UPDATE runtime_schedule_events SET started_at=?,completed_at=NULL,github_run_id=?,github_run_attempt=?,status='STARTED',details_json=? WHERE event_id=?"
                if self.db.kind == "sqlite" else
                "UPDATE runtime_schedule_events SET started_at=%s,completed_at=NULL,github_run_id=%s,github_run_attempt=%s,status='STARTED',details_json=%s::jsonb WHERE event_id=%s"
            )
            self.db.execute(sql, (iso(utcnow()), run_id, attempt, _json(self.db, {"retry": True}), event_id))
            return event_id
        event_id = str(uuid.uuid4())
        values = (event_id, event_key, workflow_name, cycle_type.value if cycle_type else None, iso(scheduled_at), iso(utcnow()), run_id, attempt, "STARTED", _json(self.db, {}))
        sql = (
            "INSERT INTO runtime_schedule_events(event_id,event_key,workflow_name,cycle_type,scheduled_at,started_at,github_run_id,github_run_attempt,status,details_json) VALUES (?,?,?,?,?,?,?,?,?,?)"
            if self.db.kind == "sqlite" else
            "INSERT INTO runtime_schedule_events(event_id,event_key,workflow_name,cycle_type,scheduled_at,started_at,github_run_id,github_run_attempt,status,details_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)"
        )
        self.db.execute(sql, values)
        return event_id

    def finish(self, event_id: str, *, status: str, cycle_id: str | None = None, details: dict[str, Any] | None = None) -> None:
        sql = (
            "UPDATE runtime_schedule_events SET completed_at=?,status=?,cycle_id=?,details_json=? WHERE event_id=?"
            if self.db.kind == "sqlite" else
            "UPDATE runtime_schedule_events SET completed_at=%s,status=%s,cycle_id=%s,details_json=%s::jsonb WHERE event_id=%s"
        )
        self.db.execute(sql, (iso(utcnow()), status, cycle_id, _json(self.db, details or {}), event_id))


@dataclass(frozen=True)
class ValidationSummary:
    window_start: str
    window_end: str
    expected_5m: int
    actual_5m: int
    completed_5m: int
    partial_5m: int
    failed_5m: int
    missing_5m: int
    expected_15m: int
    actual_15m: int
    completed_15m: int
    partial_15m: int
    failed_15m: int
    missing_15m: int
    ai_calls: int
    schedule_events: int

    @property
    def coverage_5m_pct(self) -> float:
        return round(100.0 * self.actual_5m / self.expected_5m, 2) if self.expected_5m else 100.0

    @property
    def coverage_15m_pct(self) -> float:
        return round(100.0 * self.actual_15m / self.expected_15m, 2) if self.expected_15m else 100.0

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["coverage_5m_pct"] = self.coverage_5m_pct
        d["coverage_15m_pct"] = self.coverage_15m_pct
        return d


def _cycles(db: Database, cycle_type: CycleType, start: datetime, end: datetime) -> list[dict]:
    ph = _ph(db)
    return db.query(
        f"SELECT cycle_id,scheduled_at,status,analysed_assets,expected_assets FROM brain_cycles WHERE cycle_type={ph} AND scheduled_at>={ph} AND scheduled_at<={ph} ORDER BY scheduled_at",
        (cycle_type.value, iso(start), iso(end)),
    )


def validation_summary(db: Database, start: datetime, end: datetime) -> ValidationSummary:
    slots5 = expected_slots(start, end, CycleType.MICRO_5M)
    slots15 = expected_slots(start, end, CycleType.MARKET_15M)
    c5 = _cycles(db, CycleType.MICRO_5M, start, end)
    c15 = _cycles(db, CycleType.MARKET_15M, start, end)
    count = lambda rows, status: sum(1 for r in rows if r["status"] == status)
    ph = _ph(db)
    schedule_events = int(db.scalar(
        f"SELECT COUNT(*) FROM runtime_schedule_events WHERE scheduled_at>={ph} AND scheduled_at<={ph}",
        (iso(start), iso(end)), 0,
    ) or 0)
    ai_calls = int(db.scalar(
        f"SELECT COUNT(*) FROM ai_calls WHERE invoked_at>={ph} AND invoked_at<={ph}",
        (iso(start), iso(end)), 0,
    ) or 0)
    return ValidationSummary(
        window_start=iso(start), window_end=iso(end),
        expected_5m=len(slots5), actual_5m=len(c5), completed_5m=count(c5,"COMPLETED"), partial_5m=count(c5,"PARTIAL"), failed_5m=count(c5,"FAILED"), missing_5m=max(0,len(slots5)-len(c5)),
        expected_15m=len(slots15), actual_15m=len(c15), completed_15m=count(c15,"COMPLETED"), partial_15m=count(c15,"PARTIAL"), failed_15m=count(c15,"FAILED"), missing_15m=max(0,len(slots15)-len(c15)),
        ai_calls=ai_calls, schedule_events=schedule_events,
    )


def persist_report(db: Database, report_type: str, start: datetime, end: datetime, summary: ValidationSummary) -> str:
    report_key = f"{report_type}:{iso(start)}:{iso(end)}"
    existing = db.query(f"SELECT report_id FROM runtime_validation_reports WHERE report_key={_ph(db)}", (report_key,))
    if existing:
        return str(existing[0]["report_id"])
    report_id = str(uuid.uuid4())
    values = (report_id, report_key, report_type, iso(start), iso(end), iso(utcnow()), _json(db, summary.as_dict()))
    sql = (
        "INSERT INTO runtime_validation_reports(report_id,report_key,report_type,window_start,window_end,generated_at,summary_json) VALUES (?,?,?,?,?,?,?)"
        if db.kind == "sqlite" else
        "INSERT INTO runtime_validation_reports(report_id,report_key,report_type,window_start,window_end,generated_at,summary_json) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)"
    )
    db.execute(sql, values)
    return report_id


def run_cycle(database_url: str, root: Path, cycle_type: CycleType, scheduled_at: datetime, workflow_name: str) -> dict[str, Any]:
    db = Database(database_url)
    _require_external_database(db)
    db.migrate()
    ledger = ScheduleEventLedger(db)
    event_id = ledger.start(workflow_name, scheduled_at, cycle_type)
    try:
        repo = BrainRepository(db)
        collector = LiveEvidenceCollector(root)
        result = DeterministicBrainCore(repo, collector).run(cycle_type, scheduled_at, workflow_id=os.getenv("GITHUB_RUN_ID") or workflow_name)
        ledger.finish(event_id, status="SUCCEEDED", cycle_id=result.cycle_id, details={"brain_status": result.status, "analysed_assets": result.analysed_assets, "expected_assets": result.expected_assets})
        return result.__dict__
    except Exception as exc:
        ledger.finish(event_id, status="FAILED", details={"error_type": type(exc).__name__, "message": str(exc)[:500]})
        raise
