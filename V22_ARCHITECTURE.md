# V22 Brain — Frozen Architecture Specification (through V22.3)

## Decision
V22 is built as a portable Brain core with replaceable infrastructure. The free-validation target is:

- Durable orchestration: Restate Cloud Free (introduced later, Stage 5)
- Runtime: AWS Lambda / Python (introduced later, Stage 4)
- Canonical memory: Neon Postgres (schema established in Stage 1)
- Agent framework: OpenAI Agents SDK through a provider adapter (Stage 7)
- Validation inference: free-tier model provider such as Gemini (Stage 7)
- Frontend: existing Streamlit terminal, reading curated database views later
- CI / independent watchdog: GitHub Actions

V22.1 does **not** activate Restate, Lambda, Neon or external AI. It freezes the contracts and builds the database foundation locally first.

## Non-negotiable invariants
1. Scheduler execution is not proof of market analysis.
2. A cycle is COMPLETED only when required durable coverage exists.
3. Raw evidence is retained separately from calculated observations.
4. AI findings never replace raw evidence and must reference evidence IDs.
5. Critical state never exists only in process memory.
6. Every persistent write is designed for safe retry/idempotency.
7. Restate will own execution state; Neon will own market-intelligence state.
8. Normal market calculations remain deterministic.
9. AI wakes because evidence warrants reasoning, not merely because a timer fired.
10. Model providers remain replaceable.
11. Protected/private information must not enter free external inference.
12. Historical findings are not rewritten after outcomes are known.
13. Runtime/hosting platforms remain adapters around the Brain core.
14. Free-tier quotas are explicit validation constraints.
15. Real-money autonomous execution is out of scope for this architecture stage.

## Core cycle contract
Cycle types:
- MICRO_5M
- MARKET_15M
- NIGHTLY_LEARNING
- BACKFILL
- MANUAL_TEST

Cycle states:
SCHEDULED -> STARTED -> COLLECTING -> VALIDATING -> CALCULATING -> [ANALYSING] -> PERSISTING -> COMPLETED/PARTIAL

FAILED is permitted from any active pre-terminal stage. Terminal states cannot silently re-open.

Every scheduled slot has a deterministic `cycle_key` derived from cycle type + UTC scheduled time. That makes duplicate scheduler/runtime delivery safe: the same slot resolves to the same durable cycle.

## Memory boundaries
### Evidence
What an external source actually reported. Stored with source, source timestamp, retrieval time, quality and immutable idempotency identity.

### Observation
What deterministic V22 calculations derive from evidence. Stored separately from source truth and linked back to evidence IDs.

### Coverage
Per-cycle/per-asset proof that expected evidence and deterministic analysis genuinely completed. Coverage controls cycle completion truth.

### Finding
Structured specialist reasoning. AI findings must contain evidence references and full model/prompt/software provenance.

### Synthesis
Cross-specialist interpretation. Original specialist findings remain intact even when they disagree.

### Episode
A meaningful historical market situation that can later receive outcome measurements.

### Outcome
What objectively happened after an episode at defined future horizons.

### Semantic memory queue
A provider-neutral staging area for memories that may later receive embeddings. V22.1 intentionally does not lock an embedding model or vector dimension. pgvector is introduced only when Stage 10 proves the retrieval design.

### AI call audit
Why an AI call occurred, which provider/model was used, protected-data check result, token counts when available, status and errors.

## Responsibility boundaries
### Brain Core
Owns deterministic market logic, contracts and persistence semantics. Must be runnable locally without Restate, Lambda, Streamlit or an AI provider.

### Restate (future Stage 5)
Owns scheduling, durable workflow progress, retries and recovery. It does not own domain memory.

### Lambda (Stage 4 adapter implemented)
Disposable Python execution only. No critical state is permitted to live only in a Lambda process. V22.4 adds a thin handler and strict invocation/environment contract; live AWS deployment remains intentionally deferred until the collector/runtime input path is proven fresh.

### Neon
Canonical domain source of truth: evidence, observations, coverage, findings, episodes, outcomes and provenance.

### Agents SDK (future Stage 7)
Specialist reasoning only. It does not schedule cycles, define technical success, or mutate evidence truth.

### Streamlit
Read/display/control surface only. It must not be required to keep the Brain alive.

### GitHub Actions
CI, release validation and independent watchdog. It is not treated as proof of successful market analysis.

## Stage sequence
0. Freeze contracts and failure semantics.
1. Neon-ready schema + local SQLite compatibility. **V22.1 scope.**
2. Deterministic Brain Core.
3. Failure engine / deliberate fault testing.
4. Lambda adapter.
5. Restate orchestration.
6. Seven-day deterministic observer test.
7. AI/model adapter + one specialist.
8. AI escalation controller.
9. Specialist expansion only when measurable value exists.
10. Episode engine + semantic retrieval/pgvector.
11. Outcome engine.
12. Nightly learning.
13. Streamlit read integration.

## V22.1 acceptance gate
- Versioned migrations create all Stage 1 tables in SQLite and are Postgres/Neon compatible by design.
- Same scheduled cycle is idempotent.
- Duplicate evidence/observations do not duplicate memory.
- Invalid state transitions are rejected.
- Incomplete expected asset coverage cannot report COMPLETED.
- Transaction failure rolls back.
- AI finding contract rejects findings without evidence references.
- All timestamps are timezone-aware UTC-compatible.
- Existing V22 foundation tests and project release validation continue to pass.


## Implementation status

- **V22.1 / Stage 0-1:** frozen contracts, relational memory schema, idempotency and coverage truth.
- **V22.2 / Stage 2:** deterministic Brain Core over the existing 5m/15m observer snapshots. It validates freshness, stores canonical evidence, calculates objective observations and finalises genuine coverage.
- **V22.4 / Stage 4:** thin AWS Lambda-compatible adapter with retry-safe scheduled invocation, environment-only runtime configuration, time-budget preflight and replaceable collector boundary.
- **Not yet activated:** live AWS Lambda deployment, Restate, external Neon, AI agents/models and pgvector retrieval.



## V22.3 / Stage 3 — Failure Engine

Stage 3 makes failure a first-class evidence type before durable external orchestration is introduced. `brain_failure_events` records the failure stage, component, optional asset, error type, severity, retryability, stable fingerprint and details.

The deterministic pipeline now proves these semantics:

- collection failure => cycle `FAILED`;
- malformed source => cycle `FAILED`;
- stale/invalid asset => asset incomplete and cycle `PARTIAL` when expected coverage is not achieved;
- unavailable expected asset => explicit coverage failure;
- deterministic calculation failure => asset incomplete;
- evidence/observation/coverage persistence failure => asset cannot claim deterministic completion;
- finalisation failure => cycle `FAILED`;
- duplicate in-progress scheduled slot => rejected without a second canonical cycle;
- repeated identical failure evidence => idempotent ledger entry.

Stage 3 still owns no retry timing. Restate will later use these failure classifications and cycle states to decide when/how execution is retried.


## V22.4 / Stage 4 — Lambda Adapter

Stage 4 wraps the deterministic Brain in a disposable runtime boundary without moving domain logic into Lambda. The handler validates only the invocation contract, builds runtime dependencies from environment, and calls `DeterministicBrainCore`.

Key rules:

- `scheduled_at` is mandatory and timezone-aware; Lambda retries must resolve to the same canonical cycle.
- database/data-root configuration never comes from the event payload; secrets remain environment configuration.
- a minimum remaining-time check refuses to begin a cycle too close to runtime expiry.
- processing exceptions escape the handler so future durable orchestration can observe/retry the failure.
- warm execution may cache configuration, but no durable market state lives in Lambda memory.
- the collector is explicitly replaceable. V22.4 still uses `LegacySnapshotCollector` for local equivalence testing; live Lambda deployment is blocked until a fresh runtime market-data source is supplied.

## V22.5 — Live Evidence Collector boundary

Stage 5 introduces a replaceable live market evidence adapter without changing the deterministic Brain contract.

`LiveEvidenceCollector -> CollectionBatch -> EvidenceValidator -> DeterministicBrainCore -> BrainRepository`

The initial live provider is Binance public market-data-only REST. The provider is intentionally hidden behind the collector boundary so a future source or multi-source collector can replace it without changing Lambda, cycle control, deterministic calculations, or memory contracts.

Snapshot mode remains available for tests/fallback. Lambda selects the collector using `V22_COLLECTOR_MODE=snapshot|live`; live activation is deferred until the controlled deployment stage.

## Stage 6 — Neon Live Memory Integration (V22.6)

The canonical `Database` boundary now supports short-lived Psycopg 3 Postgres
connections suitable for serverless execution. For Neon, TLS is required by
default and pooled endpoints are detected so the future Lambda deployment can
use Neon's PgBouncer endpoint. The database URL remains environment-only.

Stage 6 does not activate Neon during repository upload. A dedicated smoke test
will later migrate a real Neon database, write a `MANUAL_TEST` cycle, destroy
its first client objects, reconnect, and verify the same canonical cycle is
recoverable. AI, Restate, AWS deployment and vector embeddings remain disabled.
