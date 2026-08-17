# V22.2 — Deterministic Brain Core

V22.2 implements Stage 2 of the frozen free-first architecture.

It adds a strict deterministic pipeline over the existing 5-minute microstructure and 15-minute observer snapshots:

`cycle -> collect -> validate -> calculate -> persist -> coverage -> final status`

## Added
- LegacySnapshotCollector adapter that converts existing observer snapshots into V22 evidence contracts.
- Freshness and data-quality validation before calculations are accepted.
- Objective deterministic calculations for multi-timeframe direction, volume flow, volume participation, market structure and anomaly level.
- Per-asset failure isolation: one unavailable/stale asset makes the cycle PARTIAL rather than corrupting other assets.
- Retry-safe cycle execution using the V22.1 idempotency model.
- CLI runner for local/manual 5m and 15m deterministic cycles.
- Stage 2 regression tests.

## Important architecture rule
V22.2 does not run AI. `anomaly_level` is a deterministic rule-based observation used later to decide whether AI reasoning is warranted.

## Transitional source boundary
The existing observer network collectors remain unchanged. Stage 2 consumes their latest snapshots and turns them into canonical relational evidence/observations. Replacing the legacy fetchers is a later isolated change, not mixed into this release.

## Not activated yet
- Restate
- AWS Lambda
- external Neon credentials
- OpenAI Agents SDK
- Gemini/other model inference
- pgvector retrieval
- Streamlit reads from Brain memory
