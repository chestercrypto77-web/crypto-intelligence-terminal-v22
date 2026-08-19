# V22.15 — Hyperliquid Trading Laboratory Foundation

Direction change: the generic Railway/Render observer experiment is no longer the active path.

V22.15 runs locally at zero hosting cost and consumes Hyperliquid MAINNET public WebSocket data for BTC, ETH, SOL and HYPE.
It subscribes to individual trades and L2 order-book snapshots, records raw evidence in Neon, calculates objective 60-second aggressive-flow + book-imbalance alignment events, and exposes them in a new Streamlit Hyperliquid Lab page.

Execution is deliberately DISABLED in this foundation build. The execution adapter is separated from observation so the next build can add Hyperliquid TESTNET order placement without rewriting the market-data layer.

No confidence scores are used.
