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
APP_VERSION = "22.12-trade-journey-ui"
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
.asset-row-wide{display:grid;grid-template-columns:1.30fr .55fr .55fr .55fr .55fr .72fr .78fr 1.48fr;gap:9px;align-items:center;background:#171c23;border:1px solid #29313c;border-radius:12px;padding:11px 12px;margin:.38rem 0}
.brain-card{background:linear-gradient(180deg,#1d2530,#171c23);border:1px solid #303947;border-radius:14px;padding:13px 14px;min-height:170px}
.brain-name{font-size:1.02rem;font-weight:900;color:#fff;margin:.08rem 0 .15rem}.brain-method{font-size:.67rem;text-transform:uppercase;letter-spacing:.12em;color:#8fb6e8;font-weight:850}
.brain-big{font-size:1.26rem;font-weight:900;color:#fff;margin:.42rem 0}.brain-line{display:flex;justify-content:space-between;gap:.65rem;color:#b8c4d2;font-size:.76rem;padding:.18rem 0;border-top:1px solid rgba(255,255,255,.05)}
.time-up{color:#49d17d;font-weight:850}.time-down{color:#ff6f76;font-weight:850}.time-flat{color:#e4c45c;font-weight:850}
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


def timeframe_html(v):
    x=fnum(v)
    cls="time-up" if x>0 else ("time-down" if x<0 else "time-flat")
    arrow="↑" if x>0 else ("↓" if x<0 else "→")
    return f'<span class="{cls}">{arrow} {abs(x):.2f}%</span>'


def render_attention(row, name="", narrative=""):
    vol_cls,vol_arrow=flow_class(row["Volume"])
    reason=" · ".join(row["reasons"]) if row["reasons"] else "No unusual deterministic condition"
    st.markdown(
        f'<div class="asset-row-wide"><div><div class="asset-name">{esc(row["Asset"])} {("· "+esc(name)) if name else ""}</div><div class="asset-sub">{esc(narrative)}</div></div>'
        f'<div><div class="label">15m</div>{timeframe_html(row["15m"])}</div>'
        f'<div><div class="label">1h</div>{timeframe_html(row["1h"])}</div>'
        f'<div><div class="label">4h</div>{timeframe_html(row["4h"])}</div>'
        f'<div><div class="label">24h</div>{timeframe_html(row["24h"])}</div>'
        f'<div><div class="label">Volume</div><div class="{vol_cls}">{vol_arrow} {esc(row["Volume"])}</div></div>'
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
        "paper_brains": ("paper_brains",),
        "paper_positions": ("paper_positions",),
        "paper_trades": ("paper_trades",),
        "paper_decisions": ("paper_decisions",),
        "paper_lessons": ("paper_lessons",),
        "paper_marks": ("paper_marks",),
        "paper_outcomes": ("paper_outcomes",),
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
    section("Fast timeframe pulse")
    if asset_rows:
        pulse=[]
        for label,key in [("15m","15m"),("1h","1h"),("4h","4h"),("24h","24h")]:
            leader=max(asset_rows,key=lambda r:r[key]); laggard=min(asset_rows,key=lambda r:r[key])
            pulse.append({"Window":label,"Strongest":f"{leader['Asset']} {signed(leader[key])}","Weakest":f"{laggard['Asset']} {signed(laggard[key])}"})
        st.dataframe(pd.DataFrame(pulse),use_container_width=True,hide_index=True)
    section("Moves now")
    movers=sorted(asset_rows,key=lambda r:(len(r["reasons"]),abs(r["15m"]),abs(r["1h"]),abs(r["24h"])),reverse=True)[:8]
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
    st.markdown('<div class="notice"><b>PAPER ONLY · V22 fresh competition</b><br>Four isolated wallets compete on the same evidence. Initial entries are 1.5%, scale-ins are capped, at least 70% cash is protected, and live execution remains locked.</div>',unsafe_allow_html=True)

    if snapshot.paper_brains:
        latest_mark={}
        for m in snapshot.paper_marks:
            pid=str(m.get("position_id"))
            if pid not in latest_mark: latest_mark[pid]=m
        open_by_brain=defaultdict(list)
        for p in snapshot.paper_positions:
            if str(p.get("status"))=="OPEN": open_by_brain[str(p.get("brain_id"))].append(p)
        cols=st.columns(4)
        for idx,b in enumerate(snapshot.paper_brains):
            bid=str(b.get("brain_id")); opens=open_by_brain.get(bid,[])
            starting=max(1.0,fnum(b.get("starting_cash_aud"))); cash=fnum(b.get("cash_aud"))
            deployed=sum(fnum(p.get("quantity"))*fnum((latest_mark.get(str(p.get("position_id"))) or {}).get("price_aud") or p.get("last_price_aud") or p.get("avg_entry_price_aud")) for p in opens)
            closed=int(fnum(b.get("trades_closed"))); wins=int(fnum(b.get("wins"))); winrate=100*wins/max(1,closed)
            with cols[idx%4]:
                st.markdown(
                    f'<div class="brain-card"><div class="brain-method">{esc(b.get("strategy_key"))}</div><div class="brain-name">{esc(b.get("name"))}</div>'
                    f'<div class="brain-big">{money(cash,source_currency="AUD")} cash</div>'
                    f'<div class="brain-line"><span>Deployed</span><b>{money(deployed,source_currency="AUD")} · {100*deployed/starting:.1f}%</b></div>'
                    f'<div class="brain-line"><span>Cash reserve</span><b>{100*cash/starting:.1f}%</b></div>'
                    f'<div class="brain-line"><span>Open positions</span><b>{len(opens)}</b></div>'
                    f'<div class="brain-line"><span>Realised P/L</span><b>{money(b.get("realised_pnl_aud"),source_currency="AUD")}</b></div>'
                    f'<div class="brain-line"><span>Closed / win rate</span><b>{closed} / {winrate:.0f}%</b></div>'
                    f'<div class="brain-line"><span>Initial entry now</span><b>{1.5*fnum(b.get("risk_multiplier")):.2f}%</b></div></div>',
                    unsafe_allow_html=True)

    section("Open positions")
    opens=[p for p in snapshot.paper_positions if str(p.get("status"))=="OPEN"]
    if opens:
        latest_mark={}
        for m in snapshot.paper_marks:
            pid=str(m.get("position_id"))
            if pid not in latest_mark: latest_mark[pid]=m
        rows=[]
        for p in opens:
            m=latest_mark.get(str(p.get("position_id")),{})
            mark=fnum(m.get("price_aud") or p.get("last_price_aud") or p.get("avg_entry_price_aud"))
            entry=fnum(p.get("avg_entry_price_aud")); move=((mark/entry)-1)*100 if entry else 0
            rows.append({"Brain":p.get("brain"),"Asset":p.get("asset_id"),"Entry":money(entry,source_currency="AUD"),
                         "Current":money(mark,source_currency="AUD"),"Move":signed(move),"Cost":money(p.get("cost_basis_aud"),source_currency="AUD"),
                         "Adds":p.get("add_count"),"Opened":fmt_time(p.get("opened_at"))})
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    else: st.caption("No open paper positions.")

    section("Recent trade activity")
    if snapshot.paper_trades:
        trows=[{"Time":fmt_time(t.get("executed_at")),"Brain":t.get("brain"),"Asset":t.get("asset_id"),"Side":t.get("side"),
                "Notional":money(t.get("notional_aud"),source_currency="AUD"),"Price":money(t.get("price_aud"),source_currency="AUD"),"Reason":t.get("reason")}
               for t in snapshot.paper_trades[:30]]
        st.dataframe(pd.DataFrame(trows),use_container_width=True,hide_index=True)
    else: st.caption("No paper trades recorded yet.")

elif selection=="Strategy Lab":
    st.markdown('<div class="notice"><b>Four deterministic challenger brains are active in paper mode.</b><br>They all receive the same V22 evidence and equal capital. The contest measures decision quality and capital use rather than allowing different wallet sizes to distort results.</div>',unsafe_allow_html=True)
    st.dataframe(pd.DataFrame([
        {"Brain":"Balanced Evidence","Entry logic":"3 of 4 objective confirmations","Capital rule":"1.5% probe · max 6% asset"},
        {"Brain":"Trend Guardian","Entry logic":"Trend UP + volume not DOWN","Capital rule":"1.5% probe · confirmation adds only"},
        {"Brain":"Breakout Scout","Entry logic":"BREAKOUT + volume UP","Capital rule":"Never average down"},
        {"Brain":"Flow Tracker","Entry logic":"Volume UP + elevated participation + trend not DOWN","Capital rule":"≥70% cash reserve"},
    ]),use_container_width=True,hide_index=True)
    section("Risk Governor")
    st.dataframe(pd.DataFrame([
        {"Rule":"Initial probe","Limit":"1.5% of starting capital"},
        {"Rule":"Scale-in tranche","Limit":"1.0% · max 2 adds"},
        {"Rule":"Single asset","Limit":"6% maximum"},
        {"Rule":"Total deployed","Limit":"30% maximum"},
        {"Rule":"Cash reserve","Limit":"70% minimum"},
        {"Rule":"Open positions","Limit":"6 maximum"},
        {"Rule":"Hard paper stop","Limit":"5% below average entry"},
        {"Rule":"Learning","Limit":"May reduce size; cannot exceed 100% baseline"},
    ]),use_container_width=True,hide_index=True)

elif selection=="Performance Lab":
    c1,c2,c3=st.columns(3)
    with c1:metric_card("Paper trades",str(len(snapshot.paper_trades)),"Fresh V22 competition only")
    with c2:metric_card("Closed trades",str(sum(int(fnum(x.get("trades_closed"))) for x in snapshot.paper_brains)),"Measured exits")
    with c3:metric_card("Learning records",str(len(snapshot.paper_lessons)),"Outcome-driven, not confidence scores")
    section("Brain performance")
    if snapshot.paper_brains:
        rows=[]
        for b in snapshot.paper_brains:
            closed=int(fnum(b.get("trades_closed")));wins=int(fnum(b.get("wins")))
            rows.append({"Brain":b.get("name"),"Closed":closed,"Wins":wins,"Losses":int(fnum(b.get("losses"))),
                         "Win rate %":round(100*wins/max(1,closed),1),"Realised P/L AUD":money(b.get("realised_pnl_aud"),source_currency="AUD"),
                         "Risk multiplier":f"{100*fnum(b.get('risk_multiplier')):.0f}%"})
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    else: st.caption("Competition waiting for its first scheduled run.")
    section("Closed trade journeys")
    if snapshot.paper_outcomes:
        odf=pd.DataFrame([{"Closed":fmt_time(o.get("closed_at")),"Brain":o.get("brain"),"Asset":o.get("asset_id"),
                          "Return":signed(o.get("return_pct")),"Best while held":signed(o.get("max_favourable_pct")),
                          "Worst while held":signed(o.get("max_adverse_pct")),"Held":f"{fnum(o.get('holding_minutes')):.0f} min",
                          "P/L":money(o.get("pnl_aud"),source_currency="AUD"),"Exit reason":o.get("exit_reason")}
                         for o in snapshot.paper_outcomes])
        st.dataframe(odf,use_container_width=True,hide_index=True)
    else: st.caption("No positions have completed a full trade journey yet.")
    section("Measured learning")
    if snapshot.paper_lessons:
        ldf=pd.DataFrame(snapshot.paper_lessons)
        st.dataframe(ldf[[c for c in ["created_at","brain","sample_size","win_rate","avg_return_pct","previous_risk_multiplier","proposed_risk_multiplier","state","reason"] if c in ldf]],use_container_width=True,hide_index=True)
    else: st.caption("A brain needs at least 8 closed trades before sizing can adapt.")

elif selection=="Learning Evidence":
    c1,c2,c3=st.columns(3)
    with c1:metric_card("Episodes",str(len(snapshot.episodes)),"Setups/events remembered")
    with c2:metric_card("Outcomes",str(len(snapshot.outcomes)),"What happened afterwards")
    with c3:metric_card("Semantic queue",str(len(snapshot.semantic_memory)),"Memory candidates; vector retrieval not activated")
    section("Episodes")
    if snapshot.episodes:
        edf=pd.DataFrame(snapshot.episodes);st.dataframe(edf,use_container_width=True,hide_index=True)
    else:st.markdown('<div class="notice">Market episode memory remains available for the broader intelligence layer. The paper brains now also learn from their own measured closed-trade outcomes through bounded risk adaptation.</div>',unsafe_allow_html=True)
    section("Trade journey evidence")
    c1,c2,c3=st.columns(3)
    with c1:metric_card("Position marks",str(len(snapshot.paper_marks)),"15-minute path observations while trades are open")
    with c2:metric_card("Completed journeys",str(len(snapshot.paper_outcomes)),"Entry → path → exit measured")
    with c3:metric_card("Promoted lessons",str(sum(1 for x in snapshot.paper_lessons if str(x.get("state"))=="PROMOTED")),"Bounded learning after enough outcomes")
    section("Paper-brain decision receipts")
    if snapshot.paper_decisions:
        ddf=pd.DataFrame(snapshot.paper_decisions)
        st.dataframe(ddf[[c for c in ["observed_at","brain","asset_id","action","risk_approved","requested_notional_aud","approved_notional_aud","reason"] if c in ddf]],use_container_width=True,hide_index=True)
    else: st.caption("No paper decisions recorded yet.")
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
        {"Component":"Paper trading","Role":"Fresh competing brains + bounded learning","State":"ACTIVE" if snapshot.paper_brains else "INSTALLED"},
        {"Component":"Live trading execution","Role":"Real-money action layer","State":"LOCKED"},
        {"Component":"Restate / production orchestrator","Role":"Future durable orchestration","State":"NOT ACTIVATED"},
    ]),use_container_width=True,hide_index=True)
    section("Portfolio configuration")
    st.caption(f"{len(holdings)} legacy holdings migrated without conviction scores. Streamlit does not modify this file or the Neon database.")

st.markdown(f'<div class="small" style="margin-top:1.8rem">V22 platform bridge · Neon read-only · rendered {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}</div>',unsafe_allow_html=True)
