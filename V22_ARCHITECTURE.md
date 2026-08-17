# V22 Brain — Frozen Architecture Specification (V22.1)

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

### Lambda (future Stage 4)
Disposable Python execution only. No critical state is permitted to live only in a Lambda process.

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
