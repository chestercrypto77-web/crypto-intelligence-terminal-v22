# V22 Streamlit Foundation

This release adds a root `app.py` for Streamlit Community Cloud. It is deliberately read-only.

Runtime ownership remains:

`GitHub Actions -> V22 Brain -> Neon`

The Streamlit app only reads Neon and presents durable Brain state. It does not collect market data, calculate observations, call AI, or mutate V22 memory.

## Streamlit deployment

Repository: `chestercrypto77-web/crypto-intelligence-terminal-v22`

Branch: `main`

Main file path: `app.py`

In Streamlit Advanced settings -> Secrets add the pooled Neon connection string under `DATABASE_URL`.
