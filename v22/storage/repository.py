from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any
import uuid

from v22.contracts import (
    CoverageContract,
    CycleContract,
    CycleStatus,
    EvidenceContract,
    ObservationContract,
)


TERMINAL = {CycleStatus.COMPLETED, CycleStatus.PARTIAL, CycleStatus.FAILED}
ALLOWED_TRANSITIONS = {
    CycleStatus.SCHEDULED: {CycleStatus.STARTED, CycleStatus.FAILED},
    CycleStatus.STARTED: {CycleStatus.COLLECTING, CycleStatus.FAILED},
    CycleStatus.COLLECTING: {CycleStatus.VALIDATING, CycleStatus.PARTIAL, CycleStatus.FAILED},
    CycleStatus.VALIDATING: {CycleStatus.CALCULATING, CycleStatus.PARTIAL, CycleStatus.FAILED},
    CycleStatus.CALCULATING: {CycleStatus.ANALYSING, CycleStatus.PERSISTING, CycleStatus.PARTIAL, CycleStatus.FAILED},
    CycleStatus.ANALYSING: {CycleStatus.PERSISTING, CycleStatus.PARTIAL, CycleStatus.FAILED},
    CycleStatus.PERSISTING: {CycleStatus.COMPLETED, CycleStatus.PARTIAL, CycleStatus.FAILED},
    CycleStatus.COMPLETED: set(),
    CycleStatus.PARTIAL: set(),
    CycleStatus.FAILED: set(),
}


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def _dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


class BrainRepository:
    """Canonical Stage 1 persistence boundary.

    Business logic should use this repository rather than issuing ad-hoc writes to
    the V22 Brain memory tables. All insert paths are designed to be retry-safe.
    """

    def __init__(self, db):
        self.db = db

    def _sql(self, sqlite: str, postgres: str) -> str:
        return sqlite if self.db.kind == "sqlite" else postgres

    def create_cycle(self, cycle: CycleContract) -> dict:
        fields = (
            cycle.cycle_id,
            cycle.cycle_key,
            cycle.cycle_type.value,
            _iso(cycle.scheduled_at),
            _iso(cycle.started_at),
            _iso(cycle.completed_at),
            cycle.workflow_id,
            cycle.status.value,
            cycle.expected_assets,
            cycle.error,
            cycle.provenance.as_json(),
        )
        sql = self._sql(
            """INSERT OR IGNORE INTO brain_cycles(
                cycle_id,cycle_key,cycle_type,scheduled_at,started_at,completed_at,
                workflow_id,status,expected_assets,error,provenance_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            """INSERT INTO brain_cycles(
                cycle_id,cycle_key,cycle_type,scheduled_at,started_at,completed_at,
                workflow_id,status,expected_assets,error,provenance_json
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT(cycle_key) DO NOTHING""",
        )
        self.db.execute(sql, fields)
        return self.get_cycle_by_key(cycle.cycle_key)

    def get_cycle(self, cycle_id: str) -> dict | None:
        ph = "?" if self.db.kind == "sqlite" else "%s"
        rows = self.db.query(f"SELECT * FROM brain_cycles WHERE cycle_id={ph}", (cycle_id,))
        return rows[0] if rows else None

    def get_cycle_by_key(self, cycle_key: str) -> dict | None:
        ph = "?" if self.db.kind == "sqlite" else "%s"
        rows = self.db.query(f"SELECT * FROM brain_cycles WHERE cycle_key={ph}", (cycle_key,))
        return rows[0] if rows else None

    def transition_cycle(
        self,
        cycle_id: str,
        new_status: CycleStatus,
        *,
        at: datetime | None = None,
        error: str | None = None,
    ) -> dict:
        current = self.get_cycle(cycle_id)
        if current is None:
            raise KeyError(f"unknown cycle_id: {cycle_id}")
        old_status = CycleStatus(current["status"])
        if new_status == old_status:
            return current
        if new_status not in ALLOWED_TRANSITIONS[old_status]:
            raise ValueError(f"invalid cycle transition: {old_status.value} -> {new_status.value}")

        when = _iso(at or datetime.now(timezone.utc))
        started_at = when if new_status == CycleStatus.STARTED and not current.get("started_at") else current.get("started_at")
        completed_at = when if new_status in TERMINAL else current.get("completed_at")
        sql = self._sql(
            "UPDATE brain_cycles SET status=?,started_at=?,completed_at=?,error=?,updated_at=CURRENT_TIMESTAMP WHERE cycle_id=?",
            "UPDATE brain_cycles SET status=%s,started_at=%s,completed_at=%s,error=%s,updated_at=NOW() WHERE cycle_id=%s",
        )
        self.db.execute(sql, (new_status.value, started_at, completed_at, error, cycle_id))
        return self.get_cycle(cycle_id)

    def record_evidence(self, evidence: EvidenceContract) -> str:
        values = (
            evidence.evidence_id,
            evidence.idempotency_key,
            evidence.cycle_id,
            evidence.asset_id,
            evidence.metric,
            _dump(evidence.value),
            evidence.unit,
            evidence.source,
            _iso(evidence.source_timestamp),
            _iso(evidence.retrieved_at),
            evidence.quality.value,
            evidence.raw_reference,
            _dump(dict(evidence.metadata)),
        )
        sql = self._sql(
            """INSERT OR IGNORE INTO evidence_records(
                evidence_id,idempotency_key,cycle_id,asset_id,metric,value_json,unit,
                source,source_timestamp,retrieved_at,quality,raw_reference,metadata_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            """INSERT INTO evidence_records(
                evidence_id,idempotency_key,cycle_id,asset_id,metric,value_json,unit,
                source,source_timestamp,retrieved_at,quality,raw_reference,metadata_json
            ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT(idempotency_key) DO NOTHING""",
        )
        if self.db.kind == "postgres":
            sql = """INSERT INTO evidence_records(
                evidence_id,idempotency_key,cycle_id,asset_id,metric,value_json,unit,
                source,source_timestamp,retrieved_at,quality,raw_reference,metadata_json
            ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT(idempotency_key) DO UPDATE SET idempotency_key=EXCLUDED.idempotency_key
            RETURNING evidence_id"""
            return str(self.db.scalar(sql, values))
        self.db.execute(sql, values)
        return str(self.db.scalar(
            "SELECT evidence_id FROM evidence_records WHERE idempotency_key=?",
            (evidence.idempotency_key,),
        ))

    def record_observation(self, observation: ObservationContract) -> str:
        values = (
            observation.observation_id,
            observation.idempotency_key,
            observation.cycle_id,
            observation.asset_id,
            observation.metric,
            _dump(observation.value),
            _iso(observation.observed_at),
            observation.calculation,
            observation.quality.value,
            _dump(list(observation.evidence_ids)),
            _dump(dict(observation.metadata)),
        )
        sql = self._sql(
            """INSERT OR IGNORE INTO observation_records(
                observation_id,idempotency_key,cycle_id,asset_id,metric,value_json,
                observed_at,calculation,quality,evidence_ids_json,metadata_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            """INSERT INTO observation_records(
                observation_id,idempotency_key,cycle_id,asset_id,metric,value_json,
                observed_at,calculation,quality,evidence_ids_json,metadata_json
            ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb,%s::jsonb)
            ON CONFLICT(idempotency_key) DO NOTHING""",
        )
        if self.db.kind == "postgres":
            sql = """INSERT INTO observation_records(
                observation_id,idempotency_key,cycle_id,asset_id,metric,value_json,
                observed_at,calculation,quality,evidence_ids_json,metadata_json
            ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb,%s::jsonb)
            ON CONFLICT(idempotency_key) DO UPDATE SET idempotency_key=EXCLUDED.idempotency_key
            RETURNING observation_id"""
            return str(self.db.scalar(sql, values))
        self.db.execute(sql, values)
        return str(self.db.scalar(
            "SELECT observation_id FROM observation_records WHERE idempotency_key=?",
            (observation.idempotency_key,),
        ))

    def upsert_coverage(self, coverage: CoverageContract) -> None:
        values = (
            coverage.cycle_id,
            coverage.asset_id,
            coverage.expected,
            coverage.evidence_collected,
            coverage.deterministic_completed,
            coverage.ai_requested,
            coverage.ai_completed,
            coverage.quality.value,
            coverage.failure_reason,
        )
        sql = self._sql(
            """INSERT INTO cycle_asset_coverage(
                cycle_id,asset_id,expected,evidence_collected,deterministic_completed,
                ai_requested,ai_completed,quality,failure_reason
            ) VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(cycle_id,asset_id) DO UPDATE SET
              expected=excluded.expected,
              evidence_collected=excluded.evidence_collected,
              deterministic_completed=excluded.deterministic_completed,
              ai_requested=excluded.ai_requested,
              ai_completed=excluded.ai_completed,
              quality=excluded.quality,
              failure_reason=excluded.failure_reason,
              updated_at=CURRENT_TIMESTAMP""",
            """INSERT INTO cycle_asset_coverage(
                cycle_id,asset_id,expected,evidence_collected,deterministic_completed,
                ai_requested,ai_completed,quality,failure_reason
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(cycle_id,asset_id) DO UPDATE SET
              expected=EXCLUDED.expected,
              evidence_collected=EXCLUDED.evidence_collected,
              deterministic_completed=EXCLUDED.deterministic_completed,
              ai_requested=EXCLUDED.ai_requested,
              ai_completed=EXCLUDED.ai_completed,
              quality=EXCLUDED.quality,
              failure_reason=EXCLUDED.failure_reason,
              updated_at=NOW()""",
        )
        self.db.execute(sql, values)


    def record_failure_event(self, event) -> str:
        failure_id = str(uuid.uuid4())
        idempotency_key = f"{event.cycle_id}:{event.asset_id or ''}:{event.stage.value}:{event.fingerprint}"
        values = (
            failure_id,
            idempotency_key,
            event.cycle_id,
            event.asset_id,
            event.stage.value,
            event.component,
            event.error_type,
            event.message,
            event.severity.value,
            event.retryable,
            event.fingerprint,
            _iso(event.occurred_at),
            _dump(event.details or {}),
        )
        sql = self._sql(
            """INSERT OR IGNORE INTO brain_failure_events(
                failure_id,idempotency_key,cycle_id,asset_id,stage,component,error_type,
                message,severity,retryable,fingerprint,occurred_at,details_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            """INSERT INTO brain_failure_events(
                failure_id,idempotency_key,cycle_id,asset_id,stage,component,error_type,
                message,severity,retryable,fingerprint,occurred_at,details_json
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT(idempotency_key) DO NOTHING""",
        )
        self.db.execute(sql, values)
        ph = "?" if self.db.kind == "sqlite" else "%s"
        return self.db.scalar(
            f"SELECT failure_id FROM brain_failure_events WHERE idempotency_key={ph}",
            (idempotency_key,),
        )

    def list_failure_events(self, cycle_id: str) -> list[dict]:
        ph = "?" if self.db.kind == "sqlite" else "%s"
        return self.db.query(
            f"SELECT * FROM brain_failure_events WHERE cycle_id={ph} ORDER BY occurred_at, failure_id",
            (cycle_id,),
        )

    def coverage_summary(self, cycle_id: str) -> dict:
        ph = "?" if self.db.kind == "sqlite" else "%s"
        rows = self.db.query(f"SELECT * FROM cycle_asset_coverage WHERE cycle_id={ph}", (cycle_id,))
        expected = [r for r in rows if bool(r["expected"])]
        complete = [r for r in expected if bool(r["deterministic_completed"]) and r["quality"] not in ("INVALID", "STALE")]
        return {
            "expected": len(expected),
            "covered": len(rows),
            "deterministic_complete": len(complete),
            "failed": len([r for r in expected if r.get("failure_reason")]),
        }

    def refresh_cycle_progress(self, cycle_id: str) -> int:
        """Persist truthful analysed-asset progress before finalisation."""
        ph = "?" if self.db.kind == "sqlite" else "%s"
        complete = int(self.db.scalar(
            f"SELECT COUNT(*) FROM cycle_asset_coverage WHERE cycle_id={ph} AND expected={('1' if self.db.kind == 'sqlite' else 'TRUE')} AND deterministic_completed={('1' if self.db.kind == 'sqlite' else 'TRUE')} AND quality NOT IN ('INVALID','STALE')",
            (cycle_id,), 0,
        ) or 0)
        sql = self._sql(
            "UPDATE brain_cycles SET analysed_assets=?,updated_at=CURRENT_TIMESTAMP WHERE cycle_id=?",
            "UPDATE brain_cycles SET analysed_assets=%s,updated_at=NOW() WHERE cycle_id=%s",
        )
        self.db.execute(sql, (complete, cycle_id))
        return complete

    def reconcile_stale_cycles(self, before: datetime, *, reason: str = "stale runtime execution reconciled") -> list[dict]:
        """Close abandoned non-terminal cycles using durable coverage as truth."""
        cutoff = _iso(before)
        ph = "?" if self.db.kind == "sqlite" else "%s"
        rows = self.db.query(
            f"SELECT * FROM brain_cycles WHERE completed_at IS NULL AND started_at IS NOT NULL AND started_at<{ph} AND status NOT IN ('COMPLETED','PARTIAL','FAILED') ORDER BY started_at",
            (cutoff,),
        )
        repaired = []
        for row in rows:
            cycle_id = str(row["cycle_id"])
            complete = self.refresh_cycle_progress(cycle_id)
            old = CycleStatus(row["status"])
            target = CycleStatus.PARTIAL if complete > 0 and CycleStatus.PARTIAL in ALLOWED_TRANSITIONS[old] else CycleStatus.FAILED
            try:
                repaired.append(self.transition_cycle(cycle_id, target, error=reason))
            except ValueError:
                # Some very-early states permit FAILED but not PARTIAL.
                repaired.append(self.transition_cycle(cycle_id, CycleStatus.FAILED, error=reason))
        return repaired

    def finalise_cycle(self, cycle_id: str, *, at: datetime | None = None) -> dict:
        current = self.get_cycle(cycle_id)
        if current is None:
            raise KeyError(f"unknown cycle_id: {cycle_id}")
        if CycleStatus(current["status"]) != CycleStatus.PERSISTING:
            raise ValueError("cycle can only be finalised from PERSISTING")
        expected = int(current.get("expected_assets") or 0)
        complete = self.refresh_cycle_progress(cycle_id)
        final = CycleStatus.COMPLETED if expected == complete else CycleStatus.PARTIAL
        return self.transition_cycle(cycle_id, final, at=at)
