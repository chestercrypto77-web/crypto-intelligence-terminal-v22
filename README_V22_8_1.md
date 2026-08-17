# V22.8.1 — UUID Persistence Repair

This hotfix repairs the first live GitHub → Neon 5-minute validation failure.

The production run successfully created a `MICRO_5M` cycle in Neon, but persisted 0/16 analysed assets and recorded 32 retryable `AttributeError` events across `EVIDENCE_PERSIST` and `COVERAGE_PERSIST`. The root cause was a storage-boundary type mismatch: Psycopg/Postgres returns native `uuid.UUID` objects for UUID columns, while the V22 domain contracts deliberately use string UUIDs. SQLite returned strings and therefore did not expose the issue during earlier local validation.

V22.8.1 normalizes native Postgres UUID values to strings inside the database adapter, preserving identical contract behaviour across SQLite and Neon. The fix also covers scalar UUID results such as persisted `evidence_id` values used by deterministic observation contracts.

No schedule, architecture, AI, AWS, Restate, market-source, or database-schema change is introduced by this release.

After upload, rerun exactly one `V22 5-Minute Free Validation` workflow. Acceptance target: 16 expected assets, 16 coverage rows, 16 analysed assets, cycle status `COMPLETED`, and no new UUID persistence failure events.
