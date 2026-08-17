# V22.3 — Failure Engine

V22.3 implements Stage 3 of the frozen free-first architecture. It does not add AI, Restate, Lambda or live Neon credentials. Its purpose is to prove that the deterministic Brain reports failure truthfully before external orchestration is introduced.

## Added

- Structured `brain_failure_events` ledger with stage, component, asset, severity, retryability and stable error fingerprint.
- `FailureEngine` classification and best-effort audit persistence.
- Test-only `FaultInjector` for deterministic failure simulation.
- Failure-aware deterministic pipeline across collection, validation, evidence persistence, calculation, observation persistence, coverage persistence and finalisation.
- Explicit duplicate-in-progress protection.
- Migration 003 for SQLite and PostgreSQL/Neon.

## Truth rules

- Missing or malformed source snapshots fail the whole cycle and are audited.
- Stale data cannot count as analysed.
- Missing/unavailable assets make expected coverage partial.
- Calculation or per-asset persistence failure makes that asset incomplete.
- A finalisation failure makes the whole cycle `FAILED`.
- A duplicate scheduled slot never creates a second canonical cycle.
- Failure-audit writes are retry-safe.
- If the database itself is unavailable, the original exception is never hidden by a secondary audit-write failure.
- AI remains disabled.

## Scope boundary

V22.3 deliberately does not retry work itself. Later durable orchestration will own retry timing. V22.3 only classifies the failure, preserves evidence where possible, and ensures cycle/coverage state never overstates successful analysis.
