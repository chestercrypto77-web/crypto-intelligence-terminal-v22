from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import types

from v22.contracts import CycleContract, CycleType, Provenance
from v22.storage import BrainRepository, Database


def test_database_detects_neon_pooled_endpoint_and_adds_safe_defaults():
    db = Database("postgresql://u:p@ep-test-pooler.us-east-2.aws.neon.tech/neondb")
    assert db.is_neon is True
    assert db.uses_pooled_endpoint is True
    safe = db._postgres_url()
    assert "sslmode=require" in safe
    assert "connect_timeout=10" in safe


def test_database_preserves_explicit_postgres_connection_options():
    db = Database("postgresql://u:p@example.com/db?sslmode=verify-full&connect_timeout=3")
    safe = db._postgres_url()
    assert "sslmode=verify-full" in safe
    assert "connect_timeout=3" in safe


def test_execute_returns_rowcount_not_closed_cursor(tmp_path: Path):
    db = Database(f"sqlite:///{tmp_path/'brain.db'}")
    db.migrate()
    count = db.execute("INSERT INTO supervisor_state(key,value,updated_at) VALUES (?,?,?)", ("x", "1", 1.0))
    assert count == 1


def test_reconnect_recovers_same_durable_cycle(tmp_path: Path):
    url = f"sqlite:///{tmp_path/'brain.db'}"
    db = Database(url); db.migrate()
    cycle = CycleContract(
        cycle_type=CycleType.MANUAL_TEST,
        scheduled_at=datetime(2026,8,17,7,0,tzinfo=timezone.utc),
        provenance=Provenance(brain_version="22.6.0"),
    )
    first = BrainRepository(db).create_cycle(cycle)
    del db
    second = BrainRepository(Database(url)).get_cycle_by_key(cycle.cycle_key)
    assert second is not None
    assert str(first["cycle_id"]) == str(second["cycle_id"])


def test_postgres_driver_is_lazy_and_receives_hardened_dsn(monkeypatch):
    captured = {}
    class FakeConn:
        def commit(self): pass
        def rollback(self): pass
        def close(self): pass
    def connect(dsn, row_factory=None):
        captured["dsn"] = dsn
        return FakeConn()
    fake = types.ModuleType("psycopg")
    fake.connect = connect
    rows = types.ModuleType("psycopg.rows")
    rows.dict_row = object()
    monkeypatch.setitem(sys.modules, "psycopg", fake)
    monkeypatch.setitem(sys.modules, "psycopg.rows", rows)
    db = Database("postgresql://u:p@ep-x-pooler.us-east-2.aws.neon.tech/neondb")
    with db.connect():
        pass
    assert "sslmode=require" in captured["dsn"]
    assert "connect_timeout=10" in captured["dsn"]
