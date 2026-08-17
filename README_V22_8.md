# V22.8 — GitHub Free 24/7 Validation Runtime

V22.8 activates the no-card proof environment. The production-grade AWS/Restate path remains optional and inactive. During validation, GitHub Actions wakes the deterministic Brain and Neon remains the canonical durable source of truth.

## Active validation schedules

- 5-minute deterministic live cycle: minutes `04,09,14,...,59` UTC.
- 15-minute deterministic live cycle: minutes `07,22,37,52` UTC.
- Hourly Neon watchdog: minute `26` UTC.
- Nightly validation report: `03:43` UTC.

The offsets deliberately avoid the top of the hour. Scheduled GitHub Actions are best-effort; V22 therefore measures expected slots against actual Neon `brain_cycles` instead of treating a workflow trigger as proof of analysis.

## Runtime truth model

`runtime_schedule_events` answers: did GitHub actually start the V22 job?

`brain_cycles` answers: did V22 genuinely create a market-analysis cycle, and was it COMPLETED, PARTIAL or FAILED?

`cycle_asset_coverage` answers: which expected assets were genuinely analysed?

`runtime_validation_reports` answers: over a time window, how many cycles were expected, recorded, partial, failed or missing?

## Important boundaries

- GitHub workflows have `contents: read`; no runtime JSON is committed back to the repository.
- `DATABASE_URL` is read only from the existing GitHub encrypted secret.
- Live market evidence uses the Stage-5 public collector.
- AI/Agents are still disabled.
- AWS is not required or activated.
- Restate is not required or activated.
- Existing Lambda code remains as an optional future runtime adapter.

## Validation target

Run this deterministic environment long enough to measure actual reliability. The 30-day report can later be generated from Neon using:

`python scripts/v22_runtime_report.py --window-hours 720 --report-type THIRTY_DAY_VALIDATION`

The proof is successful only when the database can explain missing cycles, partial cycles, source failures and genuine completed coverage rather than relying on GitHub's workflow UI.
