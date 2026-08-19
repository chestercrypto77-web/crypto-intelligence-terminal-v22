from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
from typing import Any, Iterator


@dataclass(frozen=True)
class BrainSnapshot:
    cycles: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    observations: list[dict[str, Any]]
    failures: list[dict[str, Any]]
    schedule_events: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    syntheses: list[dict[str, Any]]
    episodes: list[dict[str, Any]]
    outcomes: list[dict[str, Any]]
    ai_calls: list[dict[str, Any]]
    semantic_memory: list[dict[str, Any]]
    paper_brains: list[dict[str, Any]]
    paper_positions: list[dict[str, Any]]
    paper_trades: list[dict[str, Any]]
    paper_decisions: list[dict[str, Any]]
    paper_lessons: list[dict[str, Any]]
    paper_marks: list[dict[str, Any]]
    paper_outcomes: list[dict[str, Any]]
    realtime_sessions: list[dict[str, Any]]
    realtime_providers: list[dict[str, Any]]
    realtime_assets: list[dict[str, Any]]
    realtime_bars: list[dict[str, Any]]
    realtime_states: list[dict[str, Any]]
    realtime_signals: list[dict[str, Any]]
    realtime_gaps: list[dict[str, Any]]


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



def load_recent_evidence(conn: Any, limit: int = 500) -> list[dict[str, Any]]:
    return _fetch_all(conn, """
        SELECT evidence_id::text AS evidence_id, cycle_id::text AS cycle_id,
               asset_id, metric, value_json, unit, source, source_timestamp,
               retrieved_at, quality
          FROM evidence_records
         ORDER BY source_timestamp DESC, asset_id, metric
         LIMIT %s
    """, (limit,))


def load_specialist_findings(conn: Any, limit: int = 100) -> list[dict[str, Any]]:
    return _fetch_all(conn, """
        SELECT finding_id::text AS finding_id, cycle_id::text AS cycle_id, specialist,
               claim, anomaly_level, created_at
          FROM specialist_findings ORDER BY created_at DESC LIMIT %s
    """, (limit,))


def load_syntheses(conn: Any, limit: int = 50) -> list[dict[str, Any]]:
    return _fetch_all(conn, """
        SELECT synthesis_id::text AS synthesis_id, cycle_id::text AS cycle_id,
               summary, created_at FROM synthesis_records
         ORDER BY created_at DESC LIMIT %s
    """, (limit,))


def load_episodes(conn: Any, limit: int = 100) -> list[dict[str, Any]]:
    return _fetch_all(conn, """
        SELECT episode_id::text AS episode_id, cycle_id::text AS cycle_id, asset_id,
               episode_type, description, opened_at, closed_at, created_at
          FROM episodes ORDER BY opened_at DESC LIMIT %s
    """, (limit,))


def load_outcomes(conn: Any, limit: int = 150) -> list[dict[str, Any]]:
    return _fetch_all(conn, """
        SELECT o.outcome_id::text AS outcome_id, o.episode_id::text AS episode_id,
               e.asset_id, o.horizon, o.measured_at, o.metrics_json, o.source
          FROM episode_outcomes o JOIN episodes e ON e.episode_id=o.episode_id
         ORDER BY o.measured_at DESC LIMIT %s
    """, (limit,))


def load_ai_calls(conn: Any, limit: int = 100) -> list[dict[str, Any]]:
    return _fetch_all(conn, """
        SELECT call_id::text AS call_id, cycle_id::text AS cycle_id, specialist, provider,
               model, invoked_at, completed_at, reason, status, protected_data_check,
               input_tokens, output_tokens, error
          FROM ai_calls ORDER BY invoked_at DESC LIMIT %s
    """, (limit,))


def load_semantic_memory(conn: Any, limit: int = 100) -> list[dict[str, Any]]:
    return _fetch_all(conn, """
        SELECT memory_id::text AS memory_id, memory_type, source_id, text_content,
               embedding_provider, embedding_model, embedded_at, created_at
          FROM semantic_memory_queue ORDER BY created_at DESC LIMIT %s
    """, (limit,))


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



def _table_exists(conn: Any, table_name: str) -> bool:
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s)", (f"public.{table_name}",))
            row = cur.fetchone()
            if isinstance(row, dict):
                return bool(next(iter(row.values())))
            return bool(row[0]) if row else False
    except Exception:
        return False


def load_paper_brains(conn: Any, limit: int = 20) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_brains"):
        return []
    return _fetch_all(conn, """
        SELECT b.brain_id::text AS brain_id,b.name,b.strategy_key,b.cash_aud,b.realised_pnl_aud,
               b.risk_multiplier,b.trades_closed,b.wins,b.losses,c.starting_cash_aud,c.status AS competition_status
          FROM paper_brains b JOIN paper_competitions c ON c.competition_id=b.competition_id
         ORDER BY b.name LIMIT %s
    """, (limit,))


def load_paper_positions(conn: Any, limit: int = 100) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_positions"):
        return []
    return _fetch_all(conn, """
        SELECT p.position_id::text AS position_id,p.brain_id::text AS brain_id,b.name AS brain,
               p.asset_id,p.quantity,p.avg_entry_price_aud,p.cost_basis_aud,p.opened_at,
               p.updated_at,p.status,p.add_count,p.last_price_aud,p.closed_at
          FROM paper_positions p JOIN paper_brains b ON b.brain_id=p.brain_id
         ORDER BY p.updated_at DESC LIMIT %s
    """, (limit,))


def load_paper_trades(conn: Any, limit: int = 250) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_trades"):
        return []
    return _fetch_all(conn, """
        SELECT t.trade_id::text AS trade_id,t.brain_id::text AS brain_id,b.name AS brain,
               t.asset_id,t.side,t.quantity,t.price_aud,t.notional_aud,t.executed_at,t.reason,t.cash_after_aud
          FROM paper_trades t JOIN paper_brains b ON b.brain_id=t.brain_id
         ORDER BY t.executed_at DESC LIMIT %s
    """, (limit,))


def load_paper_decisions(conn: Any, limit: int = 250) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_trade_decisions"):
        return []
    return _fetch_all(conn, """
        SELECT d.decision_id::text AS decision_id,d.brain_id::text AS brain_id,b.name AS brain,
               d.asset_id,d.action,d.reason,d.risk_approved,d.requested_notional_aud,
               d.approved_notional_aud,d.price_aud,d.observed_at
          FROM paper_trade_decisions d JOIN paper_brains b ON b.brain_id=d.brain_id
         ORDER BY d.observed_at DESC LIMIT %s
    """, (limit,))


def load_paper_lessons(conn: Any, limit: int = 100) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_lessons"):
        return []
    return _fetch_all(conn, """
        SELECT l.lesson_id::text AS lesson_id,l.brain_id::text AS brain_id,b.name AS brain,
               l.sample_size,l.wins,l.losses,l.win_rate,l.avg_return_pct,l.previous_risk_multiplier,
               l.proposed_risk_multiplier,l.state,l.reason,l.created_at
          FROM paper_lessons l JOIN paper_brains b ON b.brain_id=l.brain_id
         ORDER BY l.created_at DESC LIMIT %s
    """, (limit,))



def load_paper_marks(conn: Any, limit: int = 250) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_position_marks"):
        return []
    return _fetch_all(conn, """
        SELECT m.mark_id::text AS mark_id,m.position_id::text AS position_id,
               m.brain_id::text AS brain_id,b.name AS brain,m.asset_id,m.price_aud,
               m.return_pct,m.marked_at
          FROM paper_position_marks m JOIN paper_brains b ON b.brain_id=m.brain_id
         ORDER BY m.marked_at DESC LIMIT %s
    """, (limit,))


def load_paper_trade_outcomes(conn: Any, limit: int = 150) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_trade_outcomes"):
        return []
    return _fetch_all(conn, """
        SELECT o.outcome_id::text AS outcome_id,o.position_id::text AS position_id,
               o.brain_id::text AS brain_id,b.name AS brain,o.asset_id,o.entry_price_aud,
               o.exit_price_aud,o.cost_basis_aud,o.proceeds_aud,o.pnl_aud,o.return_pct,
               o.max_favourable_pct,o.max_adverse_pct,o.holding_minutes,o.entry_reason,
               o.exit_reason,o.opened_at,o.closed_at
          FROM paper_trade_outcomes o JOIN paper_brains b ON b.brain_id=o.brain_id
         ORDER BY o.closed_at DESC LIMIT %s
    """, (limit,))


def load_realtime_sessions(conn: Any, limit: int = 10) -> list[dict[str, Any]]:
    if not _table_exists(conn, "realtime_runtime_sessions"):
        return []
    return _fetch_all(conn, """
        SELECT session_id::text AS session_id,instance_id,version,status,primary_provider,
               secondary_provider,universe_json,started_at,last_heartbeat_at,stopped_at,
               stop_reason,metrics_json
          FROM realtime_runtime_sessions ORDER BY started_at DESC LIMIT %s
    """, (limit,))


def load_realtime_provider_health(conn: Any, limit: int = 20) -> list[dict[str, Any]]:
    if not _table_exists(conn, "realtime_provider_health"):
        return []
    return _fetch_all(conn, """
        SELECT p.session_id::text AS session_id,p.provider,p.status,p.connected_at,
               p.last_message_at,p.last_event_at,p.reconnects,p.scheduled_reconnects,
               p.messages,p.max_message_gap_seconds,p.errors,p.last_error,p.updated_at
          FROM realtime_provider_health p
         ORDER BY p.updated_at DESC LIMIT %s
    """, (limit,))


def load_realtime_asset_health(conn: Any, limit: int = 200) -> list[dict[str, Any]]:
    if not _table_exists(conn, "realtime_asset_health"):
        return []
    return _fetch_all(conn, """
        SELECT a.session_id::text AS session_id,a.asset_id,a.active_provider,
               a.primary_last_message_at,a.secondary_last_message_at,a.last_trade_at,
               a.last_bar_close_at,a.expected_minutes,a.live_minutes,a.coverage_pct,
               a.max_message_gap_seconds,a.max_gap_seconds,a.failovers,a.status,a.updated_at
          FROM realtime_asset_health a
         ORDER BY a.updated_at DESC,a.asset_id LIMIT %s
    """, (limit,))


def load_realtime_bars(conn: Any, limit: int = 120) -> list[dict[str, Any]]:
    if not _table_exists(conn, "realtime_bars_1m"):
        return []
    return _fetch_all(conn, """
        SELECT asset_id,bucket_start,provider,provenance,decision_eligible,open,high,low,close,
               base_volume,quote_volume,signed_quote_volume,trades,source_latency_ms_avg,written_at
          FROM realtime_bars_1m ORDER BY bucket_start DESC,asset_id LIMIT %s
    """, (limit,))


def load_realtime_states(conn: Any, limit: int = 240) -> list[dict[str, Any]]:
    if not _table_exists(conn, "realtime_timeframe_state"):
        return []
    return _fetch_all(conn, """
        SELECT asset_id,timeframe,measured_at,window_minutes,change_pct,quote_volume,
               signed_quote_volume,flow_share,participation_ratio,direction,volume_flow,
               coverage_pct,provenance,decision_eligible,metadata_json
          FROM realtime_timeframe_state ORDER BY measured_at DESC,asset_id,timeframe LIMIT %s
    """, (limit,))


def load_realtime_signals(conn: Any, limit: int = 100) -> list[dict[str, Any]]:
    if not _table_exists(conn, "realtime_signal_events"):
        return []
    return _fetch_all(conn, """
        SELECT event_id::text AS event_id,session_id::text AS session_id,asset_id,event_type,
               event_time,provider,provenance,decision_eligible,value,threshold,evidence_json
          FROM realtime_signal_events ORDER BY event_time DESC LIMIT %s
    """, (limit,))


def load_realtime_gaps(conn: Any, limit: int = 100) -> list[dict[str, Any]]:
    if not _table_exists(conn, "realtime_gap_events"):
        return []
    return _fetch_all(conn, """
        SELECT gap_id::text AS gap_id,session_id::text AS session_id,asset_id,provider,
               gap_start,gap_end,duration_seconds,reason,recovered_by,decision_eligible,created_at
          FROM realtime_gap_events ORDER BY gap_start DESC LIMIT %s
    """, (limit,))

def load_snapshot(database_url: str) -> BrainSnapshot:
    with readonly_connection(database_url) as conn:
        return BrainSnapshot(
            cycles=load_cycles(conn),
            evidence=load_recent_evidence(conn),
            observations=load_recent_observations(conn),
            failures=load_recent_failures(conn),
            schedule_events=load_schedule_events(conn),
            findings=load_specialist_findings(conn),
            syntheses=load_syntheses(conn),
            episodes=load_episodes(conn),
            outcomes=load_outcomes(conn),
            ai_calls=load_ai_calls(conn),
            semantic_memory=load_semantic_memory(conn),
            paper_brains=load_paper_brains(conn),
            paper_positions=load_paper_positions(conn),
            paper_trades=load_paper_trades(conn),
            paper_decisions=load_paper_decisions(conn),
            paper_lessons=load_paper_lessons(conn),
            paper_marks=load_paper_marks(conn),
            paper_outcomes=load_paper_trade_outcomes(conn),
            realtime_sessions=load_realtime_sessions(conn),
            realtime_providers=load_realtime_provider_health(conn),
            realtime_assets=load_realtime_asset_health(conn),
            realtime_bars=load_realtime_bars(conn),
            realtime_states=load_realtime_states(conn),
            realtime_signals=load_realtime_signals(conn),
            realtime_gaps=load_realtime_gaps(conn),
        )
