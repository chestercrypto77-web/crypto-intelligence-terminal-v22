# V22.5 — Live Evidence Collector

V22.5 replaces the final stale-runtime assumption in Stage 4: the Brain can now obtain fresh market candles at execution time through a provider-neutral collector boundary.

## What changed
- Added `LiveEvidenceCollector` using Binance's public market-data-only REST host (`data-api.binance.vision`) with no trading credentials.
- Added a small explicit live asset universe in `config/v22_live_assets.json`.
- Added 15-minute live evidence normalisation: price, 15m/1h/4h/24h returns, relative volume/delta, RSI/delta, MACD histogram/delta, breakout/breakdown.
- Added 1m/5m live microstructure evidence: returns, relative volume, RSI, MACD, EMA9/EMA21, ATR%, breakout/breakdown.
- Added isolated asset failure handling, malformed-response handling, stale-bar rejection, and rate-limit stop behaviour.
- Lambda can select `V22_COLLECTOR_MODE=snapshot|live`; default remains `snapshot` until deployment is intentionally activated.
- Existing snapshot collector remains available for deterministic tests and fallback operation.

## Architecture rule
Provider/network logic ends at the collector boundary. The deterministic Brain consumes the same `CollectionBatch` contract regardless of whether evidence came from legacy snapshots or live market APIs.

## Deployment state
This release does **not** deploy AWS, Restate, Neon, or AI. `live` mode is implemented and tested with deterministic HTTP fixtures, but production activation remains a later controlled deployment step.

## Free-first note
The default live implementation uses Binance public market-data-only endpoints and therefore requires no exchange account, API secret, or trading permission. Unsupported pairs are reported as unavailable and never count as analysed.
