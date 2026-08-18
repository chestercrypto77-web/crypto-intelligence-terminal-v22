# V22.8.2 — Runtime Performance + Finalisation Repair

This hotfix addresses the production timeout discovered after V22.8.1 repaired Neon UUID persistence.

## Root cause
The V22 storage adapter opened a fresh remote Postgres/Neon connection for nearly every durable insert and follow-up ID lookup. A 16-asset MICRO_5M cycle produces hundreds of evidence and observation writes, so repeated TLS/database connection setup consumed most of GitHub's four-minute job budget.

## Repair
- Reuse one bounded physical Neon connection for a cycle while preserving statement-level autocommit durability.
- Use PostgreSQL `RETURNING` for evidence and observation IDs to remove follow-up SELECT round trips.
- Persist `analysed_assets` progress after each successfully completed asset.
- Add a 210-second soft runtime deadline so a slow cycle can close truthfully as PARTIAL before GitHub's 4-minute hard timeout.
- Reconcile abandoned non-terminal cycles older than the safety window from their durable coverage records.
- Record stage timing telemetry in the cycle result / schedule-event details.

## Safety
No AI, AWS, Restate, trading execution, schema migration, or architecture change is introduced.
The GitHub job hard timeout remains four minutes; V22 is optimized to fit inside it rather than hiding the problem by increasing the limit.
