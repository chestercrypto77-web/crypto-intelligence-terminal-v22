# V22.4 — Lambda Adapter

V22.4 implements Stage 4 of the frozen free-first architecture. It does **not** deploy AWS, Restate, Neon, or AI. It proves that the already-working deterministic Brain can be invoked through a thin AWS Lambda-compatible entry point without moving business logic into the runtime layer.

## Added

- `v22.runtime.lambda_adapter.lambda_handler` as the Lambda entry point.
- Strict invocation contract for `5m` and `15m` cycles.
- Required timezone-aware `scheduled_at` so retries always map to the same canonical cycle slot.
- Runtime configuration only through environment variables; database URLs and data-root paths are rejected if supplied in event payloads.
- Warm-runtime cache for configuration while keeping all durable state in the database.
- Minimum remaining-time preflight so a cycle is not started when the runtime is already near timeout.
- Local Lambda smoke runner and Stage 4 tests.
- Explicit replaceable collector boundary so the temporary legacy snapshot collector can later be exchanged for direct market collection without changing the Lambda handler or Brain Core.

## Lambda event contract

Example direct invocation:

```json
{
  "cycle": "15m",
  "scheduled_at": "2026-08-17T05:00:00Z",
  "workflow_id": "optional-durable-workflow-id"
}
```

Accepted cycle values are `5m` and `15m`. `scheduled_at` is mandatory and must include a timezone.

## Environment contract

- `DATABASE_URL` — canonical V22 database connection. Defaults to local SQLite only for development.
- `V22_DATA_ROOT` — root containing the current collector inputs. Defaults to current directory.
- `V22_LAMBDA_MIN_REMAINING_MS` — minimum time budget required before starting a cycle. Default `10000`.
- `V22_AUTO_MIGRATE` — `1` only for controlled local/testing use. Production deployment should migrate separately.
- `V22_SOFTWARE_COMMIT` — optional explicit software provenance identifier.

## Important deployment boundary

The current deterministic core still uses the existing observer snapshot files through `LegacySnapshotCollector`. V22.4 therefore proves the **runtime adapter**, not live Lambda market ingestion. A future deployment must provide a fresh collector source (or replace the collector with direct market collection) before Lambda is allowed to become the production observer runtime.

This is deliberate: V22.4 will not bundle stale GitHub snapshots and pretend they are live market evidence.

## Failure semantics

The Lambda handler deliberately allows processing exceptions to escape. A future durable orchestrator must see a failed invocation as a failure and apply retry policy. V22's own failure ledger and cycle state remain the domain truth.

## Stage 4 acceptance gate

- Lambda-style invocation and direct Python execution produce equivalent deterministic results.
- Re-delivery of the same scheduled slot returns the same canonical cycle rather than duplicating work.
- Missing/naive `scheduled_at` is rejected.
- Runtime secrets/configuration cannot be injected through the event payload.
- Invocation refuses to begin when remaining runtime is below the safety threshold.
- Cold/warm runtime behavior does not move durable state into process memory.
- Existing Stage 1-3 behavior continues to pass.
- No AI calls, Restate calls, or AWS deployment are introduced.
