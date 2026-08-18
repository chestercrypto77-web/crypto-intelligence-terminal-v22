from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
from typing import Any, Iterator


@dataclass(frozen=True)
class BrainSnapshot:
    cycles: list[dict[str, Any]]
    observations: list[dict[str, Any]]
    failures: list[dict[str, Any]]
    schedule_events: list[dict[str, Any]]


def resolve_database_url(streamlit_secrets: Any | None = None) -> str | None:
    """Resolve DATABASE_URL without ever logging it.

    Streamlit Community Cloud injects app secrets through st.secrets. Local/dev
    execution can use the DATABASE_URL environment variable.
    """
    if streamlit_secrets is not None:
        try:
            value = streamlit_secrets.get("DATABASE_URL")
            if value:
                return str(value).strip()
        except Exception:
            pass
    value = os.getenv("DATABASE_URL", "").strip()
    return value or None


def safe_database_label(database_url: str | None) -> str:
    if not database_url:
        return "Not configured"
    return "Neon connected" if ".neon.tech" in database_url else "Postgres configured"


@contextmanager
def readonly_connection(database_url: str) -> Iterator[Any]:
    import psycopg
    from psycopg.rows import dict_row

    conn = psycopg.connect(
        database_url,
        connect_timeout=10,
        row_factory=dict_row,
        application_name="v22-streamlit-readonly",
    )
    try:
        # Enforce read-only behaviour at the session level. This protects the
        # Brain's durable memory even if a UI query is accidentally changed.
        with conn.cursor() as cur:
            cur.execute("SET default_transaction_read_only = on")
        yield conn
    finally:
        conn.close()


def _fetch_all(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]


def load_cycles(conn: Any, limit: int = 30) -> list[dict[str, Any]]:
    return _fetch_all(
        conn,
        """
        SELECT cycle_id::text AS cycle_id, cycle_type, scheduled_at, started_at,
               completed_at, workflow_id, status, expected_assets, analysed_assets,
               error
          FROM brain_cycles
         ORDER BY scheduled_at DESC
         LIMIT %s
        """,
        (limit,),
    )


def load_recent_observations(conn: Any, limit: int = 250) -> list[dict[str, Any]]:
    return _fetch_all(
        conn,
        """
        SELECT o.observation_id::text AS observation_id,
               o.cycle_id::text AS cycle_id,
               c.cycle_type,
               o.asset_id,
               o.metric,
               o.value_json,
               o.observed_at,
               o.calculation,
               o.quality
          FROM observation_records o
          JOIN brain_cycles c ON c.cycle_id = o.cycle_id
         ORDER BY o.observed_at DESC, o.asset_id, o.metric
         LIMIT %s
        """,
        (limit,),
    )


def load_recent_failures(conn: Any, limit: int = 100) -> list[dict[str, Any]]:
    return _fetch_all(
        conn,
        """
        SELECT f.failure_id::text AS failure_id,
               f.cycle_id::text AS cycle_id,
               f.asset_id, f.stage, f.component, f.error_type,
               f.message, f.severity, f.retryable, f.occurred_at
          FROM brain_failure_events f
         ORDER BY f.occurred_at DESC
         LIMIT %s
        """,
        (limit,),
    )


def load_schedule_events(conn: Any, limit: int = 40) -> list[dict[str, Any]]:
    return _fetch_all(
        conn,
        """
        SELECT event_id::text AS event_id, workflow_name, cycle_type,
               scheduled_at, started_at, completed_at, github_run_id,
               status, cycle_id::text AS cycle_id
          FROM runtime_schedule_events
         ORDER BY scheduled_at DESC
         LIMIT %s
        """,
        (limit,),
    )


def load_latest_coverage(conn: Any, cycle_id: str) -> list[dict[str, Any]]:
    return _fetch_all(
        conn,
        """
        SELECT asset_id, expected, evidence_collected, deterministic_completed,
               ai_requested, ai_completed, quality, failure_reason, updated_at
          FROM cycle_asset_coverage
         WHERE cycle_id = %s::uuid
         ORDER BY asset_id
        """,
        (cycle_id,),
    )


def load_snapshot(database_url: str) -> BrainSnapshot:
    with readonly_connection(database_url) as conn:
        return BrainSnapshot(
            cycles=load_cycles(conn),
            observations=load_recent_observations(conn),
            failures=load_recent_failures(conn),
            schedule_events=load_schedule_events(conn),
        )
