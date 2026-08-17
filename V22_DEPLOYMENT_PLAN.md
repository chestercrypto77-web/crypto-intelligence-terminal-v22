# V22 Deployment Plan — Step by Step

## Stage A — do not retire V21
Keep the existing V21 Streamlit and GitHub workflows running during the first V22 shadow trial. V22.0 is observation/reliability infrastructure only.

## Stage B — Render foundation
1. Push this complete release to GitHub.
2. Create a Render Blueprint from `render.yaml`.
3. Provision the managed PostgreSQL database.
4. Deploy `crypto-v22-brain` as the continuous background worker.
5. Deploy `crypto-v22-health` as the health/status service.
6. Confirm `DATABASE_URL` is injected from the managed database.
7. Leave `V22_MODE=shadow` and `V22_V21_BRIDGE=1`.
8. Do not add exchange API keys.

## Stage C — first proof
Run for 24 hours. Inspect:
- engine_heartbeats
- observation_runs
- observation_gaps
- system_incidents
- v21_bridge_events

Do not judge strategy performance yet. Judge only whether the nervous system stays alive and tells the truth.

## Stage D — 72-hour gate
Require:
- expected 5m and 15m slots accounted for,
- LIVE and RECONSTRUCTED clearly separated,
- restarts visible,
- no duplicate slots,
- database persists across deploy/restart.

## Stage E — migrate intelligence
Only after Stage D passes, migrate V21 market acquisition and decision engines into V22 one subsystem at a time.

## Rollback
V21 remains untouched during V22 shadow deployment. If V22 fails, stop the V22 Render services. V21 remains the reference system.

## V22.8 validation deployment — active path

AWS deployment is paused because the proof phase requires no payment method. The active validation path is GitHub Actions -> live collector -> deterministic Brain -> Neon.

Required secret already present: `DATABASE_URL`.

Install/replace the four V22.8 workflow files in `.github/workflows`:
- `microstructure_5m.yml`
- `observer_15m.yml`
- `hourly_signal_recorder.yml`
- `nightly_deep_learning.yml`

After installation, manually run 5m and 15m once. Verify each workflow succeeds, then verify Neon contains corresponding `runtime_schedule_events`, `brain_cycles`, evidence, observations and coverage. Only then leave schedules active.
