# V22.9 — Scalable Observation Engine

V22.9 keeps the proven V22.8.2 16/16 observation path intact while adding the execution strategy required for a future 100+ token universe.

## What changes

### Bounded concurrent market collection
`LiveEvidenceCollector` now fetches assets in bounded concurrent waves rather than one token at a time.

Defaults:
- `V22_LIVE_MAX_WORKERS=8`
- `V22_LIVE_BATCH_SIZE=8`

Both are configurable and hard-clamped to safe bounds. Asset output is restored to configured order after concurrent collection so idempotency and audit output remain deterministic.

### Tiered 5-minute observation depth
Each configured asset can now declare:
- `tier`: `A`, `B`, or `C`
- `micro_depth`: `FULL` or `SCREEN`

`FULL` preserves the current 1m + 5m evidence and deterministic calculations.

`SCREEN` uses one 5m request and records a smaller objective surveillance set: price, 5m return, relative volume/delta, RSI, MACD, ATR and structure. It produces screen momentum, 5m volume flow, volume participation, market structure and anomaly level. No synthetic/fake 1m observations are created.

The current 16-token production universe remains explicitly `Tier A / FULL`.

### Rate-limit containment
A provider rate limit stops future collection waves. Already-running requests in the current bounded wave are allowed to finish, but V22 does not continue submitting the remaining universe.

### Auditability
Observation tier/depth is attached to evidence and observation metadata, so later learning and diagnostics can distinguish full analysis from screening analysis.

## 100-token proof
The offline scalability smoke uses:
- 20 Tier A / FULL assets
- 40 Tier B / SCREEN assets
- 40 Tier C / SCREEN assets

This reduces a brute-force 200-request 5-minute design to 120 requests while still producing deterministic coverage for all 100 assets.

The release smoke completed 100/100 assets with 1,100 evidence records, 520 observations, bounded concurrency of 8 and zero AI calls.

## What V22.9 does NOT do
- It does not add 84 arbitrary live tokens to the production config.
- It does not activate AI, agents, AWS or Restate.
- It does not change the working GitHub schedules or four-minute safety timeout.
- It does not weaken cycle coverage truth or failure isolation.

The next live step after upload is one controlled 5-minute run on the existing 16 Tier A assets to prove the concurrent collector behaves identically in production before increasing the universe in measured stages.
