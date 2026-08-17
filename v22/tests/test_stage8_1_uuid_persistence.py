from __future__ import annotations

import sys
import types
import uuid

from v22.contracts import CoverageContract, EvidenceContract, DataQuality
from v22.storage.database import Database
from datetime import datetime, timezone


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.rowcount = 1
    def execute(self, sql, params=()):
        return None
    def fetchall(self):
        return list(self.rows)
    def fetchone(self):
        return self.rows[0] if self.rows else None


class FakeConn:
    def __init__(self, rows):
        self.rows = rows
    def cursor(self):
        return FakeCursor(self.rows)
    def commit(self):
        pass
    def rollback(self):
        pass
    def close(self):
        pass


def install_fake_psycopg(monkeypatch, rows):
    fake = types.ModuleType("psycopg")
    fake.connect = lambda dsn, row_factory=None: FakeConn(rows)
    rows_module = types.ModuleType("psycopg.rows")
    rows_module.dict_row = object()
    monkeypatch.setitem(sys.modules, "psycopg", fake)
    monkeypatch.setitem(sys.modules, "psycopg.rows", rows_module)


def test_postgres_query_normalises_native_uuid_to_contract_string(monkeypatch):
    cycle_id = uuid.uuid4()
    install_fake_psycopg(monkeypatch, [{"cycle_id": cycle_id, "status": "SCHEDULED"}])
    db = Database("postgresql://u:p@ep-test-pooler.ap-southeast-2.aws.neon.tech/neondb")
    row = db.query("SELECT cycle_id,status FROM brain_cycles")[0]
    assert row["cycle_id"] == str(cycle_id)
    assert isinstance(row["cycle_id"], str)

    # This is the exact contract boundary that failed in the first live V22.8 run.
    coverage = CoverageContract(cycle_id=row["cycle_id"], asset_id="BTC")
    assert coverage.cycle_id == str(cycle_id)


def test_postgres_scalar_normalises_native_evidence_uuid(monkeypatch):
    evidence_id = uuid.uuid4()
    install_fake_psycopg(monkeypatch, [{"evidence_id": evidence_id}])
    db = Database("postgresql://u:p@ep-test-pooler.ap-southeast-2.aws.neon.tech/neondb")
    value = db.scalar("SELECT evidence_id FROM evidence_records")
    assert value == str(evidence_id)
    assert isinstance(value, str)

    # A returned Postgres evidence UUID must remain valid input for later contracts.
    cycle_id = str(uuid.uuid4())
    ev = EvidenceContract(
        cycle_id=cycle_id,
        asset_id="BTC",
        metric="price",
        value=1.0,
        source="fixture",
        source_timestamp=datetime(2026, 8, 17, 9, 15, tzinfo=timezone.utc),
        retrieved_at=datetime(2026, 8, 17, 9, 15, tzinfo=timezone.utc),
        quality=DataQuality.GOOD,
        evidence_id=value,
    )
    assert ev.evidence_id == str(evidence_id)
