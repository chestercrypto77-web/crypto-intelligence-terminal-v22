from __future__ import annotations
import asyncio,json
from datetime import datetime,timezone
from pathlib import Path

from v22.realtime.config import RealtimeConfig
from v22.realtime.service import RealtimeObserverService

ROOT=Path(__file__).resolve().parents[2]

def test_railway_service_is_persistent_not_cron_and_always_restarts():
    cfg=json.loads((ROOT/'railway.json').read_text())
    deploy=cfg['deploy']
    assert deploy['startCommand']=='python scripts/v22_realtime_observer.py'
    assert deploy['healthcheckPath']=='/health'
    assert deploy['restartPolicyType']=='ON_FAILURE'
    assert deploy['restartPolicyMaxRetries']==10
    assert 'cronSchedule' not in deploy
    assert cfg['build']['dockerfilePath']=='Dockerfile.realtime'
    assert 'python:3.12-slim' in (ROOT/'Dockerfile.realtime').read_text()

def test_realtime_runtime_has_no_paper_execution_import():
    text=(ROOT/'v22/realtime/service.py').read_text()+(ROOT/'v22/realtime/engine.py').read_text()
    assert 'PaperCompetitionEngine' not in text
    assert 'paper_trade_decisions' not in text
    assert 'paper_trades' not in text

def test_health_only_becomes_live_after_feed_and_database_are_fresh(tmp_path):
    async def run():
        service=RealtimeObserverService(f"sqlite:///{tmp_path/'brain.db'}",RealtimeConfig(universe=('BTC',),kraken_enabled=False,health_stale_seconds=30))
        await service.initialise()
        ok,_=service.healthy();assert not ok
        now=datetime.now(timezone.utc)
        await service.on_provider_message('BINANCE',now,'BTC')
        ok,reason=service.healthy();assert ok and reason=='live'
    asyncio.run(run())
