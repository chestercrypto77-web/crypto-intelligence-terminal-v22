# V22.10 — Platform Bridge

This clean overlay restores the familiar Intelligence Desk workspace on top of the proven V22/Neon Brain.

Live now: Today, Portfolio, Markets, Watch, Research, Performance Lab, Learning Evidence, Brain Audit and Settings.
Trading Desk and Strategy Lab are visible but intentionally locked.

The UI reads Neon in a read-only database session. It does not run market collection, AI specialists, or trading execution. Legacy holding quantities are carried forward as portfolio configuration; legacy conviction scores are intentionally excluded.

## V22.10.1 Streamlit compatibility hotfix
- Normalises legacy dictionary snapshots and current BrainSnapshot objects before rendering.
- Prevents AttributeError during mixed-version/overlay deployments.
