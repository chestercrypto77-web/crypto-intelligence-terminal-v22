# V22.6 — Neon Live Memory Integration

Stage 6 hardens the existing Postgres storage boundary for Neon/serverless use without activating any external account during upload.

## Added
- short-lived Psycopg 3 Postgres connections suitable for Lambda
- Neon detection and TLS-required default
- pooled-endpoint detection for future serverless deployment
- configurable connection timeout
- database health check
- durable reconnect smoke test
- explicit `requirements-v22.txt`

## Deliberately not activated
- no Neon credentials in the repository
- no AWS deployment
- no Restate scheduling
- no AI/agents
- no pgvector embedding model yet

When a Neon project is created later, use the pooled connection string from Neon's Connect dialog as `DATABASE_URL`. The smoke script migrates the schema, writes a MANUAL_TEST cycle, destroys its first database/repository objects, reconnects, and verifies the same durable cycle remains.
