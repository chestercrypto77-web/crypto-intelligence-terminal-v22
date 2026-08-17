from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from v22.contracts import CycleType
from v22.core import DeterministicBrainCore, LiveAssetSpec, LiveEvidenceCollector, RateLimited
from v22.runtime.lambda_adapter import runtime_from_environment, reset_runtime_cache, InvocationRejected
from v22.storage import BrainRepository, Database


class FakeBinance:
    def __init__(self, *, fail_symbols=None, rate_limit_symbol=None, malformed_symbol=None, stale_seconds=0):
        self.fail_symbols=set(fail_symbols or [])
        self.rate_limit_symbol=rate_limit_symbol
        self.malformed_symbol=malformed_symbol
        self.stale_seconds=stale_seconds
        self.calls=[]

    def get_json(self, path, params):
        self.calls.append((path,dict(params)))
        symbol=params['symbol']
        if symbol == self.rate_limit_symbol:
            raise RateLimited('rate limited test','30')
        if symbol in self.fail_symbols:
            raise RuntimeError('provider outage test')
        if symbol == self.malformed_symbol:
            return {'not':'klines'}
        interval=params['interval']
        step={'1m':60_000,'5m':300_000,'15m':900_000}[interval]
        end=int(params['endTime']) - self.stale_seconds*1000
        limit=int(params['limit'])
        rows=[]
        start=end-(limit*step)
        for i in range(limit):
            open_ms=start+i*step
            close_ms=open_ms+step-1
            base=100 + i*0.2
            volume=1000 + (i%7)*25
            rows.append([open_ms,str(base),str(base+1),str(base-1),str(base+0.4),str(volume),close_ms,"0",1,"0","0","0"])
        return rows


def repo(tmp_path: Path):
    db=Database(f"sqlite:///{tmp_path/'brain.db'}")
    db.migrate()
    return BrainRepository(db)


def specs():
    return (LiveAssetSpec('ETH','ETHUSDT'),LiveAssetSpec('LINK','LINKUSDT'))


def test_live_market_collection_normalises_metrics(tmp_path: Path):
    at=datetime(2026,8,17,6,15,tzinfo=timezone.utc)
    collector=LiveEvidenceCollector(tmp_path,http_client=FakeBinance(),asset_specs=specs())
    batch=collector.collect(CycleType.MARKET_15M,at)
    assert batch.requested_assets == ('ETH','LINK')
    assert not batch.unavailable_assets
    assert len(batch.assets)==2
    names={m.name for m in batch.assets[0].metrics}
    assert {'price_usd','return_15m_pct','return_24h_pct','relative_volume','rsi','macd_histogram','breakout','breakdown'} <= names
    assert batch.source_health['provider']=='binance-public-market-data'


def test_live_micro_collection_has_one_and_five_minute_evidence(tmp_path: Path):
    at=datetime(2026,8,17,6,15,tzinfo=timezone.utc)
    collector=LiveEvidenceCollector(tmp_path,http_client=FakeBinance(),asset_specs=(specs()[0],))
    batch=collector.collect(CycleType.MICRO_5M,at)
    names={m.name for m in batch.assets[0].metrics}
    assert {'relative_volume_1m','relative_volume_5m','ema9_1m','ema21_5m','atr_1m_pct','atr_5m_pct'} <= names


def test_provider_outage_isolated_to_asset_and_cycle_partial(tmp_path: Path):
    at=datetime(2026,8,17,6,15,tzinfo=timezone.utc)
    collector=LiveEvidenceCollector(tmp_path,http_client=FakeBinance(fail_symbols={'LINKUSDT'}),asset_specs=specs())
    result=DeterministicBrainCore(repo(tmp_path),collector).run(CycleType.MARKET_15M,at)
    assert result.status=='PARTIAL'
    assert result.expected_assets==2
    assert result.analysed_assets==1
    assert 'LINK' in result.failures


def test_malformed_provider_response_is_partial_not_false_complete(tmp_path: Path):
    at=datetime(2026,8,17,6,15,tzinfo=timezone.utc)
    collector=LiveEvidenceCollector(tmp_path,http_client=FakeBinance(malformed_symbol='LINKUSDT'),asset_specs=specs())
    result=DeterministicBrainCore(repo(tmp_path),collector).run(CycleType.MARKET_15M,at)
    assert result.status=='PARTIAL'
    assert result.analysed_assets==1


def test_stale_live_bars_are_rejected_by_existing_validator(tmp_path: Path):
    at=datetime(2026,8,17,6,15,tzinfo=timezone.utc)
    collector=LiveEvidenceCollector(tmp_path,http_client=FakeBinance(stale_seconds=7200),asset_specs=(specs()[0],))
    result=DeterministicBrainCore(repo(tmp_path),collector).run(CycleType.MARKET_15M,at)
    assert result.status=='PARTIAL'
    assert result.analysed_assets==0
    assert 'stale' in result.failures['ETH']


def test_rate_limit_stops_extra_requests_and_marks_remaining_unavailable(tmp_path: Path):
    at=datetime(2026,8,17,6,15,tzinfo=timezone.utc)
    three=(LiveAssetSpec('ETH','ETHUSDT'),LiveAssetSpec('LINK','LINKUSDT'),LiveAssetSpec('BTC','BTCUSDT'))
    http=FakeBinance(rate_limit_symbol='LINKUSDT')
    batch=LiveEvidenceCollector(tmp_path,http_client=http,asset_specs=three).collect(CycleType.MARKET_15M,at)
    assert batch.source_health['rate_limited'] is True
    assert batch.unavailable_assets == ('LINK','BTC')
    assert [c[1]['symbol'] for c in http.calls] == ['ETHUSDT','LINKUSDT']


def test_live_end_to_end_completed_when_all_assets_fresh(tmp_path: Path):
    at=datetime(2026,8,17,6,15,tzinfo=timezone.utc)
    collector=LiveEvidenceCollector(tmp_path,http_client=FakeBinance(),asset_specs=specs())
    result=DeterministicBrainCore(repo(tmp_path),collector).run(CycleType.MARKET_15M,at)
    assert result.status=='COMPLETED'
    assert result.analysed_assets==2
    assert result.evidence_records==26
    assert result.observation_records==10


def test_lambda_runtime_env_can_select_live_collector(monkeypatch,tmp_path: Path):
    monkeypatch.setenv('DATABASE_URL',f"sqlite:///{tmp_path/'brain.db'}")
    monkeypatch.setenv('V22_DATA_ROOT',str(tmp_path))
    monkeypatch.setenv('V22_COLLECTOR_MODE','live')
    runtime=runtime_from_environment()
    assert runtime.collector_factory is LiveEvidenceCollector


def test_lambda_runtime_rejects_unknown_collector(monkeypatch,tmp_path: Path):
    monkeypatch.setenv('DATABASE_URL',f"sqlite:///{tmp_path/'brain.db'}")
    monkeypatch.setenv('V22_DATA_ROOT',str(tmp_path))
    monkeypatch.setenv('V22_COLLECTOR_MODE','mystery')
    with pytest.raises(InvocationRejected,match='snapshot or live'):
        runtime_from_environment()
