from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import html
import json
import math
import urllib.request

import pandas as pd
import streamlit as st

from v22.ui.neon_reader import (
    load_latest_coverage,
    load_snapshot,
    readonly_connection,
    resolve_database_url,
    safe_database_label,
)

APP_NAME = "Crypto Intelligence Terminal"
APP_VERSION = "22.10.2-aud-charcoal"
ROOT = Path(__file__).resolve().parent
HOLDINGS_FILE = ROOT / "config" / "portfolio_holdings.json"

st.set_page_config(page_title=APP_NAME, page_icon="◈", layout="wide", initial_sidebar_state="expanded")

CSS = r"""
<style>
:root { --panel:#171c23; --panel2:#1d232c; --line:#2a323d; --muted:#aab7c7; --text:#f4f7fb; --good:#49d17d; --bad:#ff6f76; --watch:#67a9ff; --fade:#f3a65a; --flat:#e4c45c; }
html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"], .stApp {background:#11161c !important;color:var(--text) !important;}
[data-testid="stHeader"] {background:rgba(17,22,28,.96) !important;}
.block-container {max-width:1550px;padding-top:1.2rem;padding-bottom:3rem;}
[data-testid="stSidebar"] {background:#14191f !important;border-right:1px solid var(--line);}
[data-testid="stSidebar"] .block-container {padding-top:1rem;}
[data-testid="stSidebar"] * {color:#dce4ee;}
[data-testid="stMarkdownContainer"] p, [data-testid="stCaptionContainer"], .stCaption {color:#b6c1cf !important;}
h1,h2,h3,h4,h5,h6 {color:#f5f7fb !important;}
label, [data-testid="stWidgetLabel"] {color:#dfe7f0 !important;}
[data-testid="stDataFrame"] {border:1px solid #2a323d;border-radius:10px;overflow:hidden;}
.term-kicker{font-size:.72rem;text-transform:uppercase;letter-spacing:.16em;color:#8ab8ef;font-weight:850}
.term-title{font-size:2rem;font-weight:900;margin:.08rem 0 .12rem;color:#ffffff !important}
.term-sub{color:#c0cad7;font-size:.94rem;margin-bottom:1.05rem;font-weight:500}
.section-title{font-size:.76rem;letter-spacing:.15em;text-transform:uppercase;color:#d5deea;font-weight:900;margin:1.25rem 0 .55rem}
.card{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:13px;padding:14px 15px;height:100%;}
.card-label{font-size:.68rem;letter-spacing:.10em;text-transform:uppercase;color:#a8b7c9;font-weight:850}
.card-value{font-size:1.28rem;font-weight:850;color:#fff;margin:.18rem 0}
.card-note{font-size:.78rem;color:#b2bdca}
.asset-row{display:grid;grid-template-columns:1.1fr .8fr .8fr .8fr 1fr 1.1fr;gap:10px;align-items:center;background:#171c23;border:1px solid #29313c;border-radius:11px;padding:10px 12px;margin:.34rem 0}
.asset-name{font-weight:850;color:#ffffff}.asset-sub{font-size:.73rem;color:#a9b6c6}.label{font-size:.65rem;text-transform:uppercase;letter-spacing:.08em;color:#9fb0c4;font-weight:800}.value{font-weight:800;color:#f3f7fb}
.signal-up{color:var(--good);font-weight:850}.signal-down{color:var(--bad);font-weight:850}.signal-watch{color:var(--watch);font-weight:850}.signal-fade{color:var(--fade);font-weight:850}.signal-flat{color:var(--flat);font-weight:850}.signal-muted{color:#9aa7b6;font-weight:750}
.pill{display:inline-block;border:1px solid #374250;border-radius:999px;padding:.10rem .45rem;font-size:.69rem;color:#c4cfdb;background:#1b222a}.pill-good{border-color:#2d6c49;color:#6ee59c}.pill-warn{border-color:#735e2c;color:#f1cd72}.pill-bad{border-color:#73373b;color:#ff9298}
.notice{background:#171d24;border:1px solid #2b3541;border-radius:12px;padding:12px 14px;color:#c7d0da}.locked{background:#181b20;border:1px dashed #48515c;border-radius:12px;padding:18px;color:#aeb8c4}
.small{font-size:.78rem;color:#8e9caf}.good{color:var(--good);font-weight:800}.bad{color:var(--bad);font-weight:800}.warn{color:var(--flat);font-weight:800}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def esc(v) -> str:
    return html.escape(str(v if v is not None else ""))


def fnum(v, default=0.0) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def fmt_num(v, decimals=2) -> str:
    x = fnum(v)
    if abs(x) >= 1_000_000_000: return f"{x/1_000_000_000:.2f}B"
    if abs(x) >= 1_000_000: return f"{x/1_000_000:.2f}M"
    if abs(x) >= 1_000: return f"{x/1_000:.2f}K"
    return f"{x:.{decimals}f}"


AUD_FALLBACK_PER_USD = 1.4092

@st.cache_data(ttl=21600, show_spinner=False)
def aud_per_usd() -> tuple[float, str]:
    # Display conversion only. Raw V22 evidence remains untouched in Neon.
    try:
        req = urllib.request.Request(
            "https://api.frankfurter.dev/v2/rate/USD/AUD",
            headers={"User-Agent": "Crypto-Intelligence-Terminal-V22/22.10.2"},
        )
        with urllib.request.urlopen(req, timeout=4) as response:
            payload = json.loads(response.read().decode("utf-8"))
        rate = fnum(payload.get("rate"))
        if rate > 0:
            return rate, "Frankfurter reference FX"
    except Exception:
        pass
    return AUD_FALLBACK_PER_USD, "cached fallback FX"

AUD_PER_USD, AUD_FX_SOURCE = aud_per_usd()

def usd_to_aud(v) -> float:
    return fnum(v) * AUD_PER_USD

def money(v, *, source_currency="USD") -> str:
    x = fnum(v)
    if source_currency.upper() == "USD":
        x = usd_to_aud(x)
    if abs(x)>=1_000_000:return f"A${x/1_000_000:.2f}M"
    if abs(x)>=1_000:return f"A${x/1_000:.1f}K"
    return f"A${x:,.2f}"

def aud_price_from_usd(v) -> str:
    x = usd_to_aud(v)
    if x >= 1_000:
        return f"A${x:,.2f}"
    if x >= 1:
        return f"A${x:,.4f}"
    if x >= 0.01:
        return f"A${x:,.5f}"
    return f"A${x:,.7f}"


def signed(v) -> str:
    x=fnum(v); return f"{x:+.2f}%"


def fmt_time(v) -> str:
    if v is None:return "—"
    try:
        return pd.to_datetime(v,utc=True).tz_convert("Australia/Perth").strftime("%d %b %H:%M AWST")
    except Exception:return str(v)


def val(v):
    if isinstance(v,(dict,list)):return json.dumps(v,separators=(",",":"))
    return v


def latest_cycle(cycles, cycle_type):
    return next((r for r in cycles if r.get("cycle_type")==cycle_type),None)


def cycle_text(row):
    if not row:return "NO DATA","bad"
    s=str(row.get("status") or "UNKNOWN").upper(); a=int(row.get("analysed_assets") or 0); e=int(row.get("expected_assets") or 0)
    if s=="COMPLETED" and e and a==e:return f"COMPLETED · {a}/{e}","good"
    if s in {"PARTIAL","CALCULATING","COLLECTING","PERSISTING","SCHEDULED"}:return f"{s} · {a}/{e}","warn"
    return f"{s} · {a}/{e}","bad"


def metric_card(title,value,note=""):
    st.markdown(f'<div class="card"><div class="card-label">{esc(title)}</div><div class="card-value">{esc(value)}</div><div class="card-note">{esc(note)}</div></div>',unsafe_allow_html=True)


def section(title):
    st.markdown(f'<div class="section-title">{esc(title)}</div>',unsafe_allow_html=True)


def load_holdings():
    try:
        payload=json.loads(HOLDINGS_FILE.read_text(encoding="utf-8"))
        return payload.get("holdings",[]) if isinstance(payload,dict) else []
    except Exception:return []


def build_maps(snapshot):
    evidence=defaultdict(dict)
    evidence_time={}
    for r in snapshot.evidence:
        a=str(r.get("asset_id") or "").upper(); m=str(r.get("metric") or "")
        evidence[a][m]=r.get("value_json")
        evidence_time[a]=max(evidence_time.get(a,pd.Timestamp.min.tz_localize("UTC")),pd.to_datetime(r.get("source_timestamp"),utc=True))
    observations=defaultdict(dict); observation_time={}
    for r in snapshot.observations:
        a=str(r.get("asset_id") or "").upper(); m=str(r.get("metric") or "")
        if m not in observations[a]: observations[a][m]=r.get("value_json")
        t=pd.to_datetime(r.get("observed_at"),utc=True)
        observation_time[a]=max(observation_time.get(a,pd.Timestamp.min.tz_localize("UTC")),t)
    return evidence,observations,evidence_time,observation_time


def flow_class(text):
    t=str(text or "").upper()
    if t in {"UP","RISING","BREAKOUT","ACCELERATING"}:return "signal-up","↑"
    if t in {"DOWN","FALLING","BREAKDOWN"}:return "signal-down","↓"
    if t in {"ELEVATED","INTERESTING","SIGNIFICANT"}:return "signal-watch","↑"
    if t in {"LOW","FADING"}:return "signal-fade","↓"
    return "signal-flat","→"


def attention_reasons(obs):
    reasons=[]
    anomaly=str(obs.get("anomaly_level") or "").upper()
    structure=str(obs.get("market_structure") or "").upper()
    participation=str(obs.get("volume_participation") or "").upper()
    flow=str(obs.get("volume_flow") or obs.get("volume_flow_5m") or "").upper()
    micro=str(obs.get("micro_trend_alignment") or "").upper()
    mtf=str(obs.get("multi_timeframe_direction") or "").upper()
    if anomaly in {"INTERESTING","SIGNIFICANT"}:reasons.append(f"Anomaly {anomaly.lower()}")
    if structure in {"BREAKOUT","BREAKDOWN"}:reasons.append(structure.title())
    if participation in {"ELEVATED","LOW"}:reasons.append(f"Participation {participation.lower()}")
    if flow in {"UP","DOWN"} and micro in {"UP","DOWN"} and flow==micro:reasons.append(f"5m flow + trend {flow.lower()}")
    if mtf in {"UP","DOWN"} and micro in {"UP","DOWN"} and mtf!=micro:reasons.append("Timeframes disagree")
    return reasons


def latest_asset_rows(evidence, observations):
    assets=sorted(set(evidence)|set(observations))
    rows=[]
    for a in assets:
        ev=evidence[a]; ob=observations[a]
        rows.append({
            "Asset":a,
            "Price":fnum(ev.get("price_usd")),
            "15m":fnum(ev.get("return_15m_pct")),
            "1h":fnum(ev.get("return_1h_pct")),
            "4h":fnum(ev.get("return_4h_pct")),
            "24h":fnum(ev.get("return_24h_pct")),
            "Volume":str(ob.get("volume_flow") or ob.get("volume_flow_5m") or "—"),
            "Participation":str(ob.get("volume_participation") or "—"),
            "Structure":str(ob.get("market_structure") or "—"),
            "Trend":str(ob.get("multi_timeframe_direction") or ob.get("micro_trend_alignment") or "—"),
            "Anomaly":str(ob.get("anomaly_level") or "—"),
            "reasons":attention_reasons(ob),
        })
    return rows


def render_attention(row, name="", narrative=""):
    vol_cls,vol_arrow=flow_class(row["Volume"]); trend_cls,trend_arrow=flow_class(row["Trend"])
    reason=" · ".join(row["reasons"]) if row["reasons"] else "No unusual deterministic condition"
    st.markdown(
        f'<div class="asset-row"><div><div class="asset-name">{esc(row["Asset"])} {("· "+esc(name)) if name else ""}</div><div class="asset-sub">{esc(narrative)}</div></div>'
        f'<div><div class="label">24h</div><div class="value">{signed(row["24h"])}</div></div>'
        f'<div><div class="label">Volume</div><div class="{vol_cls}">{vol_arrow} {esc(row["Volume"])}</div></div>'
        f'<div><div class="label">Trend</div><div class="{trend_cls}">{trend_arrow} {esc(row["Trend"])}</div></div>'
        f'<div><div class="label">Structure</div><div class="value">{esc(row["Structure"])}</div></div>'
        f'<div><div class="label">Why it matters</div><div class="asset-sub">{esc(reason)}</div></div></div>',unsafe_allow_html=True)


# Sidebar: familiar platform shell, V22 source of truth.
with st.sidebar:
    st.markdown("## ◈ Intelligence Desk")
    st.caption(f"V22 Platform · {APP_VERSION}")
    st.divider()
    selection=st.radio("Navigation",[
        "Today","Portfolio","Markets","Watch","Research",
        "Trading Desk","Strategy Lab","Performance Lab","Learning Evidence","Brain Audit","Settings"
    ],label_visibility="collapsed")
    st.divider()
    st.caption("V22 Brain → Neon → read-only Streamlit")
    st.caption(f"Display currency: AUD · FX {AUD_PER_USD:.4f}")

st.markdown('<div class="term-kicker">Crypto Intelligence Terminal</div>',unsafe_allow_html=True)

DB=resolve_database_url(st.secrets)
if not DB:
    st.error("Neon is not connected to this Streamlit app.")
    st.code('DATABASE_URL = "postgresql://...-pooler...neon.tech/neondb?sslmode=require"',language="toml")
    st.stop()
try:
    snapshot=load_snapshot(DB)
except Exception as exc:
    st.error("The terminal could not read V22 durable memory.")
    st.caption(safe_database_label(DB))
    st.code(f"{type(exc).__name__}: {exc}")
    st.stop()

# Compatibility bridge: older V22 Streamlit readers returned a dictionary,
# while the V22.10 reader returns a BrainSnapshot dataclass. Normalise both
# shapes here so deployment order cannot break the UI.
if isinstance(snapshot, dict):
    class _SnapshotCompat:
        pass
    _s = _SnapshotCompat()
    aliases = {
        "cycles": ("cycles", "brain_cycles"),
        "evidence": ("evidence", "recent_evidence", "evidence_records"),
        "observations": ("observations", "recent_observations", "observation_records"),
        "failures": ("failures", "recent_failures", "brain_failure_events"),
        "schedule_events": ("schedule_events", "runtime_schedule_events"),
        "findings": ("findings", "specialist_findings"),
        "syntheses": ("syntheses", "synthesis_records"),
        "episodes": ("episodes",),
        "outcomes": ("outcomes", "episode_outcomes"),
        "ai_calls": ("ai_calls",),
        "semantic_memory": ("semantic_memory", "semantic_memory_queue"),
    }
    for attr, keys in aliases.items():
        value = []
        for key in keys:
            if key in snapshot and snapshot.get(key) is not None:
                value = snapshot.get(key)
                break
        setattr(_s, attr, value if isinstance(value, list) else [])
    snapshot = _s

holdings=load_holdings()
holding_map={str(x.get("symbol") or "").upper():x for x in holdings}
evidence,observations,evidence_time,observation_time=build_maps(snapshot)
asset_rows=latest_asset_rows(evidence,observations)
row_map={r["Asset"]:r for r in asset_rows}
micro=latest_cycle(snapshot.cycles,"MICRO_5M"); market=latest_cycle(snapshot.cycles,"MARKET_15M")

TITLES={
    "Today":("Today","Your five-minute view of what the V22 Brain is seeing now."),
    "Portfolio":("Portfolio","Your holdings overlaid with the objective V22 evidence currently available."),
    "Markets":("Markets","The live V22 observed universe: price movement, volume, structure and anomaly state."),
    "Watch":("Watch","Assets that deserve attention because objective conditions changed or disagree."),
    "Research":("Research","Specialist findings and synthesis when the deeper research layer is activated."),
    "Trading Desk":("Trading Desk","Future execution layer. Visible now, but intentionally not authorised."),
    "Strategy Lab":("Strategy Lab","Future controlled experiments and challenger strategies."),
    "Performance Lab":("Performance Lab","Outcomes and episode evidence used to judge what actually worked."),
    "Learning Evidence":("Learning Evidence","Durable episodes, outcomes and semantic-memory candidates."),
    "Brain Audit":("Brain Audit","Coverage, scheduler truth, failures and runtime reliability."),
    "Settings":("Settings","Platform state and safety boundaries."),
}
title,subtitle=TITLES[selection]
st.markdown(f'<div class="term-title">{esc(title)}</div><div class="term-sub">{esc(subtitle)}</div>',unsafe_allow_html=True)

if selection=="Today":
    ms,_=cycle_text(micro); qs,_=cycle_text(market)
    attention=[r for r in asset_rows if r["reasons"]]
    recent_complete=sum(1 for c in snapshot.cycles[:12] if str(c.get("status") or "").upper()=="COMPLETED")
    c1,c2,c3,c4=st.columns(4)
    with c1:metric_card("5-minute Brain",ms,fmt_time(micro.get("completed_at")) if micro else "No cycle")
    with c2:metric_card("15-minute Brain",qs,fmt_time(market.get("completed_at")) if market else "No cycle")
    with c3:metric_card("Attention now",str(len(attention)),"Objective conditions only")
    with c4:metric_card("AI activity","OFF" if not snapshot.ai_calls else "RECORDED",f"{len(snapshot.ai_calls)} durable AI call records")
    section("Executive brief")
    if attention:
        names=", ".join(r["Asset"] for r in attention[:5])
        st.markdown(f'<div class="notice"><b>{len(attention)} asset(s) deserve attention.</b> The strongest current reasons are concentrated in {esc(names)}. This is an observation summary, not a trade instruction.</div>',unsafe_allow_html=True)
    else:
        st.markdown('<div class="notice">No current asset meets the objective attention rules in the latest persisted V22 observations.</div>',unsafe_allow_html=True)
    section("Moves now")
    movers=sorted(asset_rows,key=lambda r:(len(r["reasons"]),abs(r["24h"]),abs(r["4h"])),reverse=True)[:8]
    for r in movers:
        h=holding_map.get(r["Asset"],{})
        render_attention(r,h.get("name",""),h.get("narrative",""))
    section("Runtime confidence")
    st.caption(f"{recent_complete}/12 most recent cycles are COMPLETED. Brain truth is read from Neon, not inferred from GitHub's green tick.")

elif selection=="Portfolio":
    observed=[]; missing=[]; observed_value=0.0
    for h in holdings:
        sym=str(h.get("symbol") or "").upper(); r=row_map.get(sym); tokens=fnum(h.get("tokens"))
        if r and r["Price"]>0:
            v_usd=tokens*r["Price"];observed_value+=v_usd
            observed.append({"Asset":sym,"Name":h.get("name"),"Tokens":tokens,"Price AUD":usd_to_aud(r["Price"]),"Value AUD":usd_to_aud(v_usd),"24h %":r["24h"],"Volume":r["Volume"],"Trend":r["Trend"],"Quality":"V22 observed"})
        else:
            missing.append({"Asset":sym,"Name":h.get("name"),"Tokens":tokens,"Narrative":h.get("narrative"),"Status":"Not in current V22 observed universe"})
    c1,c2,c3=st.columns(3)
    with c1:metric_card("Observed portfolio value",money(observed_value),f"AUD display · 1 USD = {AUD_PER_USD:.4f} AUD")
    with c2:metric_card("Holdings observed",f"{len(observed)}/{len(holdings)}","Unobserved positions are not silently estimated")
    with c3:metric_card("Portfolio intelligence","OBJECTIVE","No conviction score")
    section("Observed holdings")
    if observed:
        odf=pd.DataFrame(observed)
        odf["Price AUD"]=odf["Price AUD"].map(lambda x: aud_price_from_usd(fnum(x)/AUD_PER_USD))
        odf["Value AUD"]=odf["Value AUD"].map(lambda x: money(fnum(x), source_currency="AUD"))
        st.dataframe(odf,use_container_width=True,hide_index=True)
    section("Waiting for V22 coverage")
    if missing:
        st.caption("These are retained from your legacy holdings configuration. They will populate automatically when the V22 universe expands; the UI will not fetch a competing price feed just to fill the table.")
        st.dataframe(pd.DataFrame(missing),use_container_width=True,hide_index=True)

elif selection=="Markets":
    section("Observed market")
    if not asset_rows:st.info("No current evidence is available.")
    else:
        df=pd.DataFrame([{k:v for k,v in r.items() if k!="reasons"} for r in asset_rows])
        df["Price AUD"]=df.pop("Price").map(aud_price_from_usd)
        for c in ["15m","1h","4h","24h"]:df[c]=df[c].map(signed)
        st.dataframe(df,use_container_width=True,hide_index=True)
    section("How to read it")
    st.markdown('<div class="notice"><span class="signal-up">Green ↑</span> = positive direction. <span class="signal-down">Red ↓</span> = negative direction. <span class="signal-watch">Blue</span> = elevated/interesting participation. No 0–100 score is generated.</div>',unsafe_allow_html=True)

elif selection=="Watch":
    attention=sorted([r for r in asset_rows if r["reasons"]],key=lambda r:(len(r["reasons"]),abs(r["24h"])),reverse=True)
    c1,c2=st.columns(2)
    with c1:metric_card("Assets flagged",str(len(attention)),"Rule-based deterministic attention")
    with c2:metric_card("Universe",str(len(asset_rows)),"Latest persisted V22 evidence")
    section("Attention desk")
    if not attention:st.success("No current objective attention triggers.")
    for r in attention:
        h=holding_map.get(r["Asset"],{})
        render_attention(r,h.get("name",""),h.get("narrative",""))
        with st.expander(f"{r['Asset']} evidence detail"):
            data=[]
            for m,v in sorted(observations.get(r["Asset"],{}).items()):data.append({"Metric":m,"Value":val(v)})
            st.dataframe(pd.DataFrame(data),use_container_width=True,hide_index=True)

elif selection=="Research":
    c1,c2,c3=st.columns(3)
    with c1:metric_card("Specialist findings",str(len(snapshot.findings)),"Durable specialist_findings rows")
    with c2:metric_card("Syntheses",str(len(snapshot.syntheses)),"Cross-specialist synthesis rows")
    with c3:metric_card("AI calls",str(len(snapshot.ai_calls)),"AI remains off until explicitly activated")
    section("Research layer")
    if snapshot.findings:
        fdf=pd.DataFrame(snapshot.findings)
        st.dataframe(fdf[[c for c in ["created_at","specialist","claim","anomaly_level"] if c in fdf]],use_container_width=True,hide_index=True)
    else:
        st.markdown('<div class="locked"><b>Research specialists are not activated yet.</b><br>V22 is currently building reliable deterministic evidence. This page is ready for the next intelligence phase without falling back to the legacy research engine.</div>',unsafe_allow_html=True)
    if snapshot.syntheses:
        section("Synthesis")
        for x in snapshot.syntheses[:10]:st.markdown(f'<div class="notice">{esc(x.get("summary"))}</div>',unsafe_allow_html=True)

elif selection=="Trading Desk":
    st.markdown('<div class="locked"><b>Execution is intentionally locked.</b><br>The new V22 Brain is observing and persisting evidence, but no live or paper trade permission is being inferred from the old platform. Trading will only be enabled after the decision, risk and outcome-learning gates are validated.</div>',unsafe_allow_html=True)
    section("What the desk can see now")
    for r in sorted(asset_rows,key=lambda x:len(x["reasons"]),reverse=True)[:6]:render_attention(r)

elif selection=="Strategy Lab":
    st.markdown('<div class="locked"><b>Strategy Lab scaffold is restored.</b><br>Challenger strategies are not active yet. The next implementation will run experiments against durable V22 evidence with strict train / validation / holdout separation rather than tuning on live results.</div>',unsafe_allow_html=True)
    section("Required gates")
    st.dataframe(pd.DataFrame([
        {"Gate":"Historical episode memory","State":"NEXT"},
        {"Gate":"Outcome measurement","State":"NEXT"},
        {"Gate":"Train / validation / holdout split","State":"PLANNED"},
        {"Gate":"Challenger promotion rules","State":"PLANNED"},
    ]),use_container_width=True,hide_index=True)

elif selection=="Performance Lab":
    c1,c2=st.columns(2)
    with c1:metric_card("Episodes",str(len(snapshot.episodes)),"Durable learning episodes")
    with c2:metric_card("Measured outcomes",str(len(snapshot.outcomes)),"Outcome rows, not subjective grades")
    section("Recorded outcomes")
    if snapshot.outcomes:
        odf=pd.DataFrame(snapshot.outcomes)
        st.dataframe(odf[[c for c in ["asset_id","horizon","measured_at","metrics_json","source"] if c in odf]],use_container_width=True,hide_index=True)
    else:st.info("No episode outcomes have been measured yet. This is the next learning milestone.")

elif selection=="Learning Evidence":
    c1,c2,c3=st.columns(3)
    with c1:metric_card("Episodes",str(len(snapshot.episodes)),"Setups/events remembered")
    with c2:metric_card("Outcomes",str(len(snapshot.outcomes)),"What happened afterwards")
    with c3:metric_card("Semantic queue",str(len(snapshot.semantic_memory)),"Memory candidates; vector retrieval not activated")
    section("Episodes")
    if snapshot.episodes:
        edf=pd.DataFrame(snapshot.episodes);st.dataframe(edf,use_container_width=True,hide_index=True)
    else:st.markdown('<div class="notice">The durable episode tables are ready but the episode/outcome learning loop has not been activated. This is now the highest-priority intelligence build.</div>',unsafe_allow_html=True)
    if snapshot.semantic_memory:
        section("Semantic memory candidates")
        mdf=pd.DataFrame(snapshot.semantic_memory);st.dataframe(mdf[[c for c in ["memory_type","source_id","text_content","created_at","embedded_at"] if c in mdf]],use_container_width=True,hide_index=True)

elif selection=="Brain Audit":
    ms,_=cycle_text(micro);qs,_=cycle_text(market)
    c1,c2,c3,c4=st.columns(4)
    with c1:metric_card("5m",ms,fmt_time(micro.get("completed_at")) if micro else "")
    with c2:metric_card("15m",qs,fmt_time(market.get("completed_at")) if market else "")
    with c3:metric_card("Scheduler events",str(len(snapshot.schedule_events)),"Durable scheduler ledger")
    with c4:metric_card("Failure records",str(len(snapshot.failures)),"Historical failures retained")
    section("Runtime reliability")
    if snapshot.cycles:
        df=pd.DataFrame(snapshot.cycles);df["Scheduled"]=df["scheduled_at"].map(fmt_time);df["Completed"]=df["completed_at"].map(fmt_time)
        st.dataframe(df[["cycle_type","status","expected_assets","analysed_assets","workflow_id","Scheduled","Completed"]].rename(columns={"cycle_type":"Cycle","status":"Status","expected_assets":"Expected","analysed_assets":"Analysed","workflow_id":"GitHub run"}),use_container_width=True,hide_index=True)
    section("Scheduler events")
    if snapshot.schedule_events:
        sdf=pd.DataFrame(snapshot.schedule_events);sdf["Scheduled"]=sdf["scheduled_at"].map(fmt_time);sdf["Completed"]=sdf["completed_at"].map(fmt_time)
        st.dataframe(sdf[["workflow_name","cycle_type","status","github_run_id","Scheduled","Completed"]].rename(columns={"workflow_name":"Workflow","cycle_type":"Cycle","status":"Status","github_run_id":"GitHub run"}),use_container_width=True,hide_index=True)
    section("Historical failures")
    if snapshot.failures:
        fdf=pd.DataFrame(snapshot.failures);fdf["Occurred"]=fdf["occurred_at"].map(fmt_time)
        st.dataframe(fdf[["asset_id","stage","component","error_type","severity","retryable","Occurred"]].rename(columns={"asset_id":"Asset","stage":"Stage","component":"Component","error_type":"Error","severity":"Severity","retryable":"Retryable"}),use_container_width=True,hide_index=True)

elif selection=="Settings":
    c1,c2,c3=st.columns(3)
    with c1:metric_card("Database",safe_database_label(DB),"Session forced read-only")
    with c2:metric_card("Runtime","GitHub Actions","Free validation runtime")
    with c3:metric_card("AI","OFF" if not snapshot.ai_calls else "RECORDED","No automatic agent activation")
    section("Platform boundaries")
    st.dataframe(pd.DataFrame([
        {"Component":"Streamlit","Role":"Read-only workspace","State":"LIVE"},
        {"Component":"Neon","Role":"Durable Brain memory","State":"LIVE"},
        {"Component":"GitHub Actions","Role":"5m / 15m runtime","State":"LIVE"},
        {"Component":"Deterministic Brain","Role":"Evidence + observations","State":"LIVE"},
        {"Component":"Specialist AI","Role":"Escalated reasoning","State":"OFF"},
        {"Component":"Trading execution","Role":"Action layer","State":"LOCKED"},
        {"Component":"Restate / production orchestrator","Role":"Future durable orchestration","State":"NOT ACTIVATED"},
    ]),use_container_width=True,hide_index=True)
    section("Portfolio configuration")
    st.caption(f"{len(holdings)} legacy holdings migrated without conviction scores. Streamlit does not modify this file or the Neon database.")

st.markdown(f'<div class="small" style="margin-top:1.8rem">V22 platform bridge · Neon read-only · rendered {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}</div>',unsafe_allow_html=True)
