from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import uuid

from v22.contracts import CycleContract, CycleStatus, CycleType, Provenance
from v22.runtime.github_validation import ScheduleEventLedger, expected_slots, persist_report, previous_slot, validation_summary
from v22.storage import BrainRepository, Database

UTC=timezone.utc
ROOT=Path(__file__).resolve().parents[2]


def db(tmp_path: Path) -> Database:
    value=Database(f"sqlite:///{tmp_path/'brain.db'}")
    value.migrate()
    return value


def test_previous_slot_uses_offset_schedule_not_top_of_hour():
    assert previous_slot(datetime(2026,8,17,12,7,tzinfo=UTC),CycleType.MICRO_5M)==datetime(2026,8,17,12,4,tzinfo=UTC)
    assert previous_slot(datetime(2026,8,17,12,21,tzinfo=UTC),CycleType.MARKET_15M)==datetime(2026,8,17,12,7,tzinfo=UTC)
    assert previous_slot(datetime(2026,8,17,12,2,tzinfo=UTC),CycleType.MICRO_5M)==datetime(2026,8,17,11,59,tzinfo=UTC)


def test_expected_slot_counts_for_one_hour_window():
    start=datetime(2026,8,17,12,0,tzinfo=UTC)
    end=datetime(2026,8,17,12,59,tzinfo=UTC)
    assert len(expected_slots(start,end,CycleType.MICRO_5M))==12
    assert len(expected_slots(start,end,CycleType.MARKET_15M))==4


def test_schedule_event_ledger_is_retry_safe(tmp_path: Path, monkeypatch):
    database=db(tmp_path); ledger=ScheduleEventLedger(database)
    at=datetime(2026,8,17,12,4,tzinfo=UTC)
    monkeypatch.setenv('GITHUB_RUN_ID','123'); monkeypatch.setenv('GITHUB_RUN_ATTEMPT','1')
    first=ledger.start('five',at,CycleType.MICRO_5M)
    ledger.finish(first,status='SUCCEEDED',details={'ok':True})
    monkeypatch.setenv('GITHUB_RUN_ATTEMPT','2')
    second=ledger.start('five',at,CycleType.MICRO_5M)
    assert first==second
    assert database.scalar('SELECT COUNT(*) FROM runtime_schedule_events')==1


def _insert_terminal(repo: BrainRepository, cycle_type: CycleType, at: datetime, status: CycleStatus):
    cycle=CycleContract(cycle_type=cycle_type,scheduled_at=at,expected_assets=0,provenance=Provenance(brain_version='test',software_commit='test',calculation_version='test',schema_version='004'))
    row=repo.create_cycle(cycle); cid=row['cycle_id']
    repo.transition_cycle(cid,CycleStatus.STARTED); repo.transition_cycle(cid,CycleStatus.COLLECTING)
    if status==CycleStatus.FAILED:
        repo.transition_cycle(cid,CycleStatus.FAILED,error='test')
    else:
        repo.transition_cycle(cid,CycleStatus.VALIDATING); repo.transition_cycle(cid,CycleStatus.CALCULATING); repo.transition_cycle(cid,CycleStatus.PERSISTING); repo.transition_cycle(cid,status)


def test_validation_summary_measures_missing_cycles_not_workflow_claims(tmp_path: Path):
    database=db(tmp_path); repo=BrainRepository(database)
    start=datetime(2026,8,17,12,0,tzinfo=UTC); end=datetime(2026,8,17,12,14,tzinfo=UTC)
    _insert_terminal(repo,CycleType.MICRO_5M,datetime(2026,8,17,12,4,tzinfo=UTC),CycleStatus.COMPLETED)
    _insert_terminal(repo,CycleType.MARKET_15M,datetime(2026,8,17,12,7,tzinfo=UTC),CycleStatus.PARTIAL)
    summary=validation_summary(database,start,end)
    assert summary.expected_5m==3 and summary.actual_5m==1 and summary.missing_5m==2
    assert summary.expected_15m==1 and summary.actual_15m==1 and summary.partial_15m==1
    rid=persist_report(database,'TEST',start,end,summary)
    assert rid and database.scalar('SELECT COUNT(*) FROM runtime_validation_reports')==1


def test_runtime_workflows_are_neon_only_and_read_only():
    names=['microstructure_5m.yml','observer_15m.yml','nightly_deep_learning.yml','hourly_signal_recorder.yml']
    texts=[(ROOT/'.github/workflows'/name).read_text(encoding='utf-8') for name in names]
    for text in texts:
        assert 'contents: read' in text
        assert 'contents: write' not in text
        assert 'git push' not in text
        assert 'DATABASE_URL: ${{ secrets.DATABASE_URL }}' in text
        assert 'aws-actions' not in text.lower()
        assert 'gemini' not in text.lower()
        assert 'openai' not in text.lower()
        assert 'restate' not in text.lower()
    assert '4-59/5 * * * *' in texts[0]
    assert '7,22,37,52 * * * *' in texts[1]
    assert '43 3 * * *' in texts[2]
    assert '26 * * * *' in texts[3]


def test_stage8_migration_exists_for_both_databases():
    assert (ROOT/'v22/migrations/004_github_validation_runtime_sqlite.sql').exists()
    assert (ROOT/'v22/migrations/004_github_validation_runtime_postgres.sql').exists()
