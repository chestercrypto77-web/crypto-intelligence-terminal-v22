# V22.13 — Realtime Observer Proof of Concept

V22.13 changes the market heartbeat architecture without moving the paper brains yet.

## What changes

- Adds a persistent Python realtime observer intended to run 24/7 as a container service.
- Binance Spot public WebSocket is the primary feed.
  - aggregate trades build causal 1-minute OHLCV and signed taker-flow evidence;
  - individual mini-ticker streams provide a 1-second reference/heartbeat per asset.
- Kraken Spot WebSocket v2 is an optional secondary live feed for supported assets.
- The six-asset proof universe is BTC, ETH, SOL, XRP, LINK and COTI.
- Rolling 1m / 5m / 15m / 1h / 4h states are derived from canonical 1-minute bars.
- Objective 60-second price-move and flow-imbalance events can be recorded immediately, inside a candle window.
- Neon stores only durable minute/state/health/event evidence — not every raw tick.
- Streamlit gains a Realtime Feed page showing provider freshness, feed-message gaps, asset coverage, missing bars, failovers, latest bars and derived states.

## Causality and learning safety

Realtime provenance is explicit:

- `LIVE_STREAM` — built from primary live trades.
- `LIVE_DERIVED_IDLE` — no trades in a minute, but the primary live reference feed remained fresh; zero trade volume is retained truthfully.
- `LIVE_FAILOVER` — built from the secondary live provider while primary was stale.
- `LIVE_MULTI_PROVIDER_TRANSITION` — a provider change occurred inside the minute; retained for continuity but **not decision eligible**.
- future `BACKFILL_*` evidence is reserved for historical repair and is **never decision eligible**.

The POC is observational only. It imports no paper-trading engine and cannot create paper trades or decisions. Existing V22 paper brains continue on the current path until the realtime acceptance test passes.

## Reliability design

- Provider sockets reconnect themselves with bounded exponential backoff.
- A silent Binance socket is treated as failed rather than allowed to hang indefinitely.
- Binance is deliberately rotated before its 24-hour server connection limit.
- Kraken also has a silence watchdog and reconnect loop.
- Raw provider message-gap maxima are measured in seconds, separately from candle coverage.
- A missing minute is recorded as a real gap; it is not silently fabricated.
- Database writes use a queue and bounded batches so market ingestion does not open a Postgres connection per tick.
- Railway `/health` is only green after both the primary feed and Neon persistence are fresh.
- Critical internal tasks are supervised; an unexpected critical task exit terminates the process so the hosting platform can restart it.

## Deployment portability

The runtime itself has no Railway SDK dependency. `Dockerfile.realtime` is a standard Python 3.12 container and the observer only requires environment variables plus outbound WebSocket/HTTPS access. Railway is the first proof host, not a permanent lock-in decision.

## 72-hour acceptance gates

Do not connect paper-brain decisions to realtime evidence until the proof run meets all gates:

- same runtime session has run for at least 72 hours;
- runtime heartbeat age <= 30 seconds;
- primary provider maximum raw message gap <= 15 seconds;
- each asset maximum live-feed message gap <= 15 seconds;
- each asset 1-minute live coverage >= 99.5%;
- no missing-bar gap > 60 seconds;
- database persistence errors = 0;
- zero backfilled rows marked decision eligible;
- provider switches/reconnects are visible rather than hidden.

Run `python scripts/v22_realtime_acceptance.py` after the proof window. The Streamlit Realtime Feed page exposes the same operational truth during the test.
