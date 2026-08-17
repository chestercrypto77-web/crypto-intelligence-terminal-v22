# V22.1 — Brain Contracts + Neon Memory Foundation

V22.1 is the first implementation step of the frozen free-first architecture.

It deliberately does **not** connect Restate, AWS Lambda, Neon credentials or AI services yet. Instead it makes the Brain core safe and testable locally before infrastructure is added.

## Added
- Typed V22 contracts for cycles, evidence, observations, coverage, findings, synthesis, episodes, outcomes and AI-call audit.
- Strict UTC/timezone validation.
- Deterministic idempotency keys for scheduled cycles, evidence and observations.
- Versioned Stage 1 SQLite and PostgreSQL/Neon migrations.
- Retry-safe BrainRepository persistence boundary.
- Explicit cycle state machine.
- Genuine asset-coverage completion rule: incomplete cycles become PARTIAL.
- Provider-neutral semantic-memory queue without prematurely locking an embedding model.
- Stage 1 regression tests.

## Not activated yet
- Restate
- AWS Lambda
- External Neon database
- OpenAI Agents SDK
- Gemini or other AI inference
- pgvector embedding index
- Streamlit Brain-memory read path

Those remain later gated stages.

## Safety
The existing V21/V22 UI, workflows, paper-trading histories and live JSON runtime files are not replaced by Stage 1. The new relational Brain memory is additive until later migration gates are passed.
