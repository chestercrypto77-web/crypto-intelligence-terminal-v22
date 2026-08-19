# Railway deployment — V22.13 realtime POC

This is a proof deployment, not the final production migration.

## Required Railway variables

- `DATABASE_URL` — the same pooled Neon connection string already used by V22.
- `REALTIME_POC_MODE=true`
- `REALTIME_UNIVERSE=BTC,ETH,SOL,XRP,LINK,COTI`
- `KRAKEN_ENABLED=true`

Optional only if a region cannot reach Binance's primary endpoint:

- `BINANCE_WS_BASE=wss://data-stream.binance.vision`

The application binds its health server to Railway's injected `PORT` automatically.

## What Railway reads from the repo

- `railway.json` — Dockerfile build, persistent start command, `/health`, restart policy and graceful draining.
- `Dockerfile.realtime` — Python 3.12 runtime.
- `requirements-realtime.txt` — Neon driver + WebSocket client.

For the no-card proof, `railway.json` uses `ON_FAILURE` with 10 restart attempts because Railway does not expose `ALWAYS` restart policy to trial/free users. If the architecture passes and is promoted to paid Hobby, change restart policy to `ALWAYS` and remove the retry ceiling.

## Freeze the code during the 72-hour proof

A deployment creates a new realtime session. Once the POC starts, avoid deploying new code until the acceptance window finishes, otherwise the 72-hour session clock intentionally resets.
