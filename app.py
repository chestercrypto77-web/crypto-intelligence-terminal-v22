from __future__ import annotations

from datetime import datetime, timezone
import json

import pandas as pd
import streamlit as st

from v22.ui.neon_reader import (
    load_latest_coverage,
    load_snapshot,
    readonly_connection,
    resolve_database_url,
    safe_database_label,
)

APP_VERSION = "22.9-streamlit-foundation"

st.set_page_config(
    page_title="Crypto Intelligence Terminal V22",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
.block-container {max-width: 1500px; padding-top: 1.35rem;}
[data-testid="stSidebar"] {border-right: 1px solid rgba(255,255,255,.09);}
.v22-kicker {font-size:.72rem;letter-spacing:.16em;text-transform:uppercase;color:#7faeff;font-weight:800;}
.v22-title {font-size:2rem;font-weight:820;margin:.12rem 0 .15rem;}
.v22-muted {color:#9ca8b7;font-size:.88rem;}
.v22-card {border:1px solid rgba(255,255,255,.10);border-radius:14px;padding:1rem;background:rgba(255,255,255,.025);height:100%;}
.v22-good {color:#62dc94;font-weight:800;}
.v22-warn {color:#f2c96d;font-weight:800;}
.v22-bad {color:#ff7b7b;font-weight:800;}
</style>
""",
    unsafe_allow_html=True,
)


def fmt_time(value) -> str:
    if value is None:
        return "—"
    try:
        dt = pd.to_datetime(value, utc=True)
        return dt.tz_convert("Australia/Perth").strftime("%d %b %H:%M:%S AWST")
    except Exception:
        return str(value)


def display_value(value) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"))
    return str(value)


def latest_cycle(cycles: list[dict], cycle_type: str) -> dict | None:
    return next((row for row in cycles if row.get("cycle_type") == cycle_type), None)


def cycle_health(row: dict | None) -> tuple[str, str]:
    if not row:
        return "NO DATA", "bad"
    status = str(row.get("status", "UNKNOWN")).upper()
    expected = int(row.get("expected_assets") or 0)
    analysed = int(row.get("analysed_assets") or 0)
    if status == "COMPLETED" and expected > 0 and analysed == expected:
        return f"COMPLETED · {analysed}/{expected}", "good"
    if status in {"PARTIAL", "CALCULATING", "COLLECTING", "SCHEDULED"}:
        return f"{status} · {analysed}/{expected}", "warn"
    return f"{status} · {analysed}/{expected}", "bad"


def metric_card(title: str, value: str, note: str = "") -> None:
    st.markdown(
        f"<div class='v22-card'><div class='v22-muted'>{title}</div>"
        f"<div style='font-size:1.45rem;font-weight:800;margin:.2rem 0'>{value}</div>"
        f"<div class='v22-muted'>{note}</div></div>",
        unsafe_allow_html=True,
    )


with st.sidebar:
    st.markdown("### 🧠 V22 Brain")
    st.caption(f"Streamlit Foundation · {APP_VERSION}")
    st.divider()
    page = st.radio("View", ["Brain Overview", "Market Observations", "Reliability"], label_visibility="collapsed")
    st.divider()
    st.caption("Read-only interface. GitHub Actions runs the Brain; Neon is durable memory.")

st.markdown("<div class='v22-kicker'>Crypto Intelligence Terminal</div>", unsafe_allow_html=True)
st.markdown("<div class='v22-title'>V22 Brain</div>", unsafe_allow_html=True)
st.markdown("<div class='v22-muted'>A read-only window into the deterministic Brain and its durable Neon memory.</div>", unsafe_allow_html=True)

database_url = resolve_database_url(st.secrets)
if not database_url:
    st.error("Neon is not connected to this Streamlit app yet.")
    st.markdown(
        "Open **Advanced settings → Secrets** for this Streamlit app and add a secret named "
        "`DATABASE_URL` containing the same pooled Neon connection string used by the V22 GitHub Actions runtime."
    )
    st.code('DATABASE_URL = "postgresql://...-pooler...neon.tech/neondb?sslmode=require..."', language="toml")
    st.warning("Do not put the real connection string in GitHub or paste it into chat.")
    st.stop()

try:
    snapshot = load_snapshot(database_url)
except Exception as exc:
    st.error("V22 could not read Neon.")
    st.caption(f"Connection status: {safe_database_label(database_url)}")
    # The exception is useful for deployment diagnosis but does not contain the URL.
    st.code(f"{type(exc).__name__}: {exc}")
    st.stop()

cycles = snapshot.cycles
micro = latest_cycle(cycles, "MICRO_5M")
market = latest_cycle(cycles, "MARKET_15M")

if page == "Brain Overview":
    m_status, _ = cycle_health(micro)
    q_status, _ = cycle_health(market)
    completed = sum(1 for c in cycles if str(c.get("status", "")).upper() == "COMPLETED")
    recent_failures = snapshot.failures[:10]

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("5-minute Brain", m_status, fmt_time(micro.get("completed_at")) if micro else "No cycle")
    with c2:
        metric_card("15-minute Brain", q_status, fmt_time(market.get("completed_at")) if market else "No cycle")
    with c3:
        metric_card("Recent completed cycles", str(completed), f"Last {len(cycles)} cycles loaded")
    with c4:
        metric_card("AI activity", "OFF", "Deterministic validation stage")

    st.subheader("Latest cycle coverage")
    chosen = micro or market
    if chosen:
        with readonly_connection(database_url) as conn:
            coverage = load_latest_coverage(conn, chosen["cycle_id"])
        if coverage:
            df = pd.DataFrame(coverage)
            shown = df[["asset_id", "evidence_collected", "deterministic_completed", "quality", "failure_reason"]].copy()
            shown.columns = ["Asset", "Evidence", "Deterministic", "Quality", "Failure"]
            st.dataframe(shown, use_container_width=True, hide_index=True)
        else:
            st.info("No coverage rows exist for the latest cycle.")

    st.subheader("Latest observations")
    recent = snapshot.observations[:30]
    if recent:
        odf = pd.DataFrame(recent)
        odf["value"] = odf["value_json"].map(display_value)
        odf["observed"] = odf["observed_at"].map(fmt_time)
        st.dataframe(
            odf[["asset_id", "metric", "value", "quality", "cycle_type", "observed"]]
            .rename(columns={"asset_id":"Asset", "metric":"Metric", "value":"Value", "quality":"Quality", "cycle_type":"Cycle", "observed":"Observed"}),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No deterministic observations have been persisted yet.")

    if recent_failures:
        st.subheader("Recent recorded failures")
        st.caption("Historical failures remain visible by design; successful later cycles are not erased.")
        fdf = pd.DataFrame(recent_failures)
        fdf["occurred"] = fdf["occurred_at"].map(fmt_time)
        st.dataframe(
            fdf[["asset_id", "stage", "error_type", "severity", "retryable", "occurred"]]
            .rename(columns={"asset_id":"Asset", "stage":"Stage", "error_type":"Error", "severity":"Severity", "retryable":"Retryable", "occurred":"Occurred"}),
            use_container_width=True,
            hide_index=True,
        )

elif page == "Market Observations":
    st.subheader("Deterministic market observations")
    st.caption("Objective outputs only. No 0–100 confidence or conviction scoring is generated by this V22 interface.")
    observations = snapshot.observations
    if not observations:
        st.info("No observations available.")
    else:
        assets = sorted({str(r["asset_id"]) for r in observations})
        asset = st.selectbox("Asset", ["All"] + assets)
        rows = observations if asset == "All" else [r for r in observations if r["asset_id"] == asset]
        odf = pd.DataFrame(rows)
        odf["Value"] = odf["value_json"].map(display_value)
        odf["Observed"] = odf["observed_at"].map(fmt_time)
        st.dataframe(
            odf[["asset_id", "metric", "Value", "quality", "cycle_type", "calculation", "Observed"]]
            .rename(columns={"asset_id":"Asset", "metric":"Metric", "quality":"Quality", "cycle_type":"Cycle", "calculation":"Calculation"}),
            use_container_width=True,
            hide_index=True,
        )

elif page == "Reliability":
    st.subheader("Runtime reliability")
    st.caption("GitHub workflow status is not treated as Brain truth; durable Neon cycle state is shown here.")

    if cycles:
        cdf = pd.DataFrame(cycles)
        cdf["Scheduled"] = cdf["scheduled_at"].map(fmt_time)
        cdf["Completed"] = cdf["completed_at"].map(fmt_time)
        st.dataframe(
            cdf[["cycle_type", "status", "expected_assets", "analysed_assets", "workflow_id", "Scheduled", "Completed"]]
            .rename(columns={"cycle_type":"Cycle", "status":"Status", "expected_assets":"Expected", "analysed_assets":"Analysed", "workflow_id":"GitHub run"}),
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Scheduler events")
    if snapshot.schedule_events:
        sdf = pd.DataFrame(snapshot.schedule_events)
        sdf["Scheduled"] = sdf["scheduled_at"].map(fmt_time)
        sdf["Completed"] = sdf["completed_at"].map(fmt_time)
        st.dataframe(
            sdf[["workflow_name", "cycle_type", "status", "github_run_id", "Scheduled", "Completed"]]
            .rename(columns={"workflow_name":"Workflow", "cycle_type":"Cycle", "status":"Status", "github_run_id":"GitHub run"}),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No runtime schedule events have been recorded yet.")

    st.subheader("Failure ledger")
    if snapshot.failures:
        fdf = pd.DataFrame(snapshot.failures)
        fdf["Occurred"] = fdf["occurred_at"].map(fmt_time)
        st.dataframe(
            fdf[["asset_id", "stage", "component", "error_type", "severity", "retryable", "Occurred"]]
            .rename(columns={"asset_id":"Asset", "stage":"Stage", "component":"Component", "error_type":"Error", "severity":"Severity", "retryable":"Retryable"}),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.success("No failure events are currently stored.")

st.caption(f"V22 read-only UI · {safe_database_label(database_url)} · rendered {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
