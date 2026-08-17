# Crypto Intelligence Terminal V22.0.0 — Always-On Brain Foundation

This release begins the infrastructure migration from scheduled GitHub Actions to a persistent, always-running brain.

**This is deliberately a shadow foundation.** It proves timing, durable state, recovery and auditing before trading intelligence is migrated.

Start locally:
```bash
pip install -r requirements-v22.txt
python -m v22.brain.supervisor --once
python -m v22.audit.status
```

Continuous local shadow run:
```bash
python -m v22.brain.supervisor
```

Default local storage uses `data/v22_local.db`. Production uses `DATABASE_URL` with PostgreSQL.
