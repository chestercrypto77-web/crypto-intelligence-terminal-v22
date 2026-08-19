from __future__ import annotations
import argparse,json,os,sys
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

from v22.storage import Database

UTC=timezone.utc

def dt(v):
    if not v:return None
    if isinstance(v,datetime):return v.astimezone(UTC)
    return datetime.fromisoformat(str(v).replace('Z','+00:00')).astimezone(UTC)

def main():
    ap=argparse.ArgumentParser(description='Evaluate V22 realtime observer POC against strict acceptance gates.')
    ap.add_argument('--min-hours',type=float,default=72.0)
    ap.add_argument('--min-coverage',type=float,default=99.5)
    ap.add_argument('--max-feed-gap',type=float,default=15.0)
    ap.add_argument('--max-missing-bar-gap',type=float,default=60.0)
    ap.add_argument('--max-heartbeat-age',type=float,default=30.0)
    args=ap.parse_args()
    url=os.getenv('DATABASE_URL','').strip()
    if not url:raise SystemExit('DATABASE_URL is required')
    db=Database(url);ph='?' if db.kind=='sqlite' else '%s';now=datetime.now(UTC)
    sessions=db.query('SELECT * FROM realtime_runtime_sessions ORDER BY started_at DESC LIMIT 1')
    if not sessions:
        print(json.dumps({'status':'NOT_STARTED','passed':False},indent=2));return 2
    s=sessions[0];sid=s['session_id'];started=dt(s['started_at']);hb=dt(s['last_heartbeat_at'])
    runtime_h=(now-started).total_seconds()/3600.0;heartbeat_age=(now-hb).total_seconds()
    assets=db.query(f'SELECT * FROM realtime_asset_health WHERE session_id={ph} ORDER BY asset_id',(sid,))
    providers=db.query(f'SELECT * FROM realtime_provider_health WHERE session_id={ph} ORDER BY provider',(sid,))
    metrics=s.get('metrics_json') or {}
    if isinstance(metrics,str):
        try:metrics=json.loads(metrics)
        except Exception:metrics={}
    gates=[]
    def gate(name,passed,value,limit):gates.append({'gate':name,'passed':bool(passed),'value':value,'limit':limit})
    gate('runtime_duration',runtime_h>=args.min_hours,round(runtime_h,3),f'>={args.min_hours}h')
    gate('heartbeat_fresh',heartbeat_age<=args.max_heartbeat_age,round(heartbeat_age,2),f'<={args.max_heartbeat_age}s')
    primary=next((p for p in providers if p.get('provider')=='BINANCE'),None)
    if primary:
        gate('primary_message_gap',float(primary.get('max_message_gap_seconds') or 0)<=args.max_feed_gap,float(primary.get('max_message_gap_seconds') or 0),f'<={args.max_feed_gap}s')
        gate('primary_status',str(primary.get('status')) in {'CONNECTED','ROTATING'},primary.get('status'),'CONNECTED/ROTATING')
    else:
        gate('primary_present',False,None,'BINANCE provider row required')
    for a in assets:
        sym=a['asset_id'];cov=float(a.get('coverage_pct') or 0);feed_gap=float(a.get('max_message_gap_seconds') or 0);bar_gap=float(a.get('max_gap_seconds') or 0)
        gate(f'{sym}_coverage',cov>=args.min_coverage,round(cov,4),f'>={args.min_coverage}%')
        gate(f'{sym}_feed_gap',feed_gap<=args.max_feed_gap,round(feed_gap,3),f'<={args.max_feed_gap}s')
        gate(f'{sym}_bar_gap',bar_gap<=args.max_missing_bar_gap,round(bar_gap,3),f'<={args.max_missing_bar_gap}s')
        gate(f'{sym}_status',str(a.get('status'))=='LIVE',a.get('status'),'LIVE')
    gate('db_errors',int(metrics.get('db_errors') or 0)==0,int(metrics.get('db_errors') or 0),'0')
    mixed=db.scalar("SELECT COUNT(*) FROM realtime_bars_1m WHERE decision_eligible=0",default=0)
    # Transition minutes may legitimately be ineligible. What must remain zero is backfill masquerading as eligible.
    if db.kind=='sqlite':
        bad=db.scalar("SELECT COUNT(*) FROM realtime_bars_1m WHERE provenance LIKE 'BACKFILL%' AND decision_eligible=1",default=0)
    else:
        bad=db.scalar("SELECT COUNT(*) FROM realtime_bars_1m WHERE provenance LIKE 'BACKFILL%' AND decision_eligible=TRUE",default=0)
    gate('backfill_never_decision_eligible',int(bad or 0)==0,int(bad or 0),'0')
    passed=all(x['passed'] for x in gates)
    status='PASSED' if passed else ('RUNNING' if runtime_h<args.min_hours else 'FAILED')
    out={'status':status,'passed':passed,'session_id':str(sid),'runtime_hours':round(runtime_h,3),'heartbeat_age_seconds':round(heartbeat_age,2),
         'assets':len(assets),'provider_rows':len(providers),'ineligible_transition_or_gap_bars':int(mixed or 0),'gates':gates}
    print(json.dumps(out,indent=2,default=str));return 0 if passed else 1

if __name__=='__main__':raise SystemExit(main())
