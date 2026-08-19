# Realtime POC acceptance — do not shortcut this gate

The purpose of V22.13 is not to prove that a Docker container starts. It is to prove that the Crypto Intelligence Terminal can observe markets continuously enough to learn causally rather than in catch-up mode.

## Pass means

1. **Raw feed continuity:** provider and per-asset message gaps are measured in seconds and remain within the gate.
2. **Canonical minute continuity:** >=99.5% of expected 1-minute bars are retained per asset and no unexplained hole is longer than one minute.
3. **Realtime provenance:** all decision-eligible data was actually available live. Backfill can repair history later but never changes what the system could have known at the time.
4. **Recovery:** WebSocket reconnects and provider switches are recorded, and the service resumes without manual intervention.
5. **Persistence:** Neon remains current while the socket continues receiving data; a database outage queues durable minute/state events instead of dropping raw decision evidence silently.
6. **No trading contamination:** this POC cannot call the paper or live execution engines.

## Fail means stop and reassess

Do not "fix the dashboard" around a failing feed. If the 72-hour run fails the continuity gates, investigate whether the cause is the exchange feed, deployment host, network region, database path, or our runtime. If Railway itself is the problem, move the same container to the next host rather than rebuilding the Brain around Railway.
