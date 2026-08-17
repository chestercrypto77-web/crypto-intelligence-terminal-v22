# V22 Always-On Brain — Foundation Specification

## Purpose
V22 removes GitHub Actions from the critical market-observation heartbeat. GitHub remains source control, testing and deployment. Streamlit remains the control room. The V22 Brain Supervisor is a continuously running process and PostgreSQL becomes authoritative operational memory.

## Safety boundary for V22.0
V22.0 runs in **SHADOW MODE ONLY**. It does not place real trades and does not alter V21 paper positions. Its first job is to prove continuity, restart recovery, durable state and truthful auditing.

## Core invariants
1. A missed live interval is never silently relabelled LIVE.
2. Recovered intervals are RECONSTRUCTED.
3. Database state is authoritative; local files are compatibility inputs/exports.
4. Heavy learning never blocks observation/risk loops.
5. Every critical engine emits a heartbeat.
6. Consumers will emit receipts when decision/learning migration begins.
7. A process restart must resume from durable database state.
8. Duplicate interval execution is prevented by unique run IDs/state checks.
9. Live-learning promotion remains governed; no single trade can rewrite behaviour.
10. Real-money execution is out of scope until long-duration paper reliability gates pass.

## V22.0 services
- Brain Supervisor: continuously alive, internal timing loop.
- PostgreSQL: durable heartbeats, observation runs, gaps, incidents and bridge imports.
- Watchdog: evaluates stale/missing critical engines independently.
- Health service: operational status endpoint for infrastructure monitoring.
- V21 bridge: imports hashes/timestamps/counts from existing V21 outputs without mutating them.
- Shadow observers: establish timing, evidence classification and persistence before V21 intelligence logic is migrated.

## Migration sequence
1. Deploy V22.0 shadow foundation.
2. Run V21 and V22 in parallel.
3. Prove 5m/15m continuity for at least 72 hours.
4. Migrate real market-data acquisition into V22.
5. Migrate Move Phase / Committee in read-only shadow mode.
6. Migrate paper position/risk engine with independent reconciliation.
7. Migrate learning asynchronously.
8. Migrate external intelligence.
9. Switch Streamlit primary read path to PostgreSQL.
10. Retire GitHub observation schedules only after acceptance gates pass.

## Acceptance gates before V22 becomes primary
- 5m live continuity >= 99.5% over 7 days; target >=99.9% over 30 days.
- 15m live continuity >= 99.5% over 7 days.
- Zero unexplained duplicate observation slots.
- Every restart produces a recorded incident/recovery trail.
- Database restart/failure does not create false LIVE observations.
- V21/V22 comparison produces deterministic explainable differences.
- Paper positions reconcile exactly after restart.
- Stop/risk enforcement remains isolated from learning workload.
