from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from v22.runtime.lambda_adapter import (
    InvocationRejected,
    LambdaRuntime,
    parse_invocation,
)


class FakeContext:
    aws_request_id = "request-123"
    function_name = "test"
    def __init__(self, remaining_ms: int = 120_000): self.remaining_ms = remaining_ms
    def get_remaining_time_in_millis(self): return self.remaining_ms


def snapshot(root: Path, at: datetime):
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "data" / "observer_latest.json").write_text(json.dumps({
        "generated_at": at.isoformat(),
        "health": {"assets_requested": 1, "unavailable_assets": []},
        "signals": [{
            "symbol":"ETH", "price":3000, "return_15m":0.2, "return_1h":0.6,
            "return_4h":1.1, "return_24h":2.0, "rvol":1.5, "rvol_delta":0.3,
            "rsi":56, "rsi_delta":2, "macd_histogram":1, "macd_delta":0.1,
            "breakout":True, "breakdown":False, "candle_time":at.isoformat(),
            "data_source":"stage4-test"
        }]
    }), encoding="utf-8")


def test_parse_requires_stable_schedule():
    with pytest.raises(InvocationRejected, match="scheduled_at is required"):
        parse_invocation({"cycle":"15m"})


def test_parse_rejects_naive_time():
    with pytest.raises(InvocationRejected, match="timezone"):
        parse_invocation({"cycle":"15m", "scheduled_at":"2026-08-17T05:00:00"})


def test_parse_rejects_runtime_secrets_in_payload():
    with pytest.raises(InvocationRejected, match="environment"):
        parse_invocation({"cycle":"15m", "scheduled_at":"2026-08-17T05:00:00Z", "database_url":"secret"})


def test_parse_accepts_detail_wrapper_and_context_workflow_id():
    parsed = parse_invocation({"detail":{"cycle":"5m", "scheduled_at":"2026-08-17T05:00:00Z"}}, context=FakeContext())
    assert parsed.cycle_type.value == "MICRO_5M"
    assert parsed.workflow_id == "request-123"
    assert parsed.scheduled_at.tzinfo is not None


def test_lambda_runtime_matches_core_and_retry_is_idempotent(tmp_path: Path):
    at = datetime(2026,8,17,5,0,tzinfo=timezone.utc)
    snapshot(tmp_path, at)
    runtime = LambdaRuntime(
        database_url=f"sqlite:///{tmp_path/'brain.db'}",
        data_root=tmp_path,
        minimum_remaining_ms=10_000,
        auto_migrate=True,
    )
    invocation = parse_invocation({"cycle":"15m", "scheduled_at":at.isoformat(), "workflow_id":"wf-1"})
    first = runtime.execute(invocation, context=FakeContext())
    second = runtime.execute(invocation, context=FakeContext())
    assert first["cycle"]["status"] == "COMPLETED"
    assert first["cycle"]["cycle_id"] == second["cycle"]["cycle_id"]
    assert first["cycle"]["analysed_assets"] == 1


def test_lambda_refuses_to_start_without_time_budget(tmp_path: Path):
    at = datetime(2026,8,17,5,0,tzinfo=timezone.utc)
    snapshot(tmp_path, at)
    runtime = LambdaRuntime(
        database_url=f"sqlite:///{tmp_path/'brain.db'}",
        data_root=tmp_path,
        minimum_remaining_ms=10_000,
        auto_migrate=True,
    )
    invocation = parse_invocation({"cycle":"15m", "scheduled_at":at.isoformat()})
    with pytest.raises(TimeoutError, match="refusing to start"):
        runtime.execute(invocation, context=FakeContext(5_000))


def test_warm_runtime_can_process_distinct_slots(tmp_path: Path):
    first_at = datetime(2026,8,17,5,0,tzinfo=timezone.utc)
    second_at = datetime(2026,8,17,5,15,tzinfo=timezone.utc)
    snapshot(tmp_path, first_at)
    runtime = LambdaRuntime(f"sqlite:///{tmp_path/'brain.db'}", tmp_path, 10_000, True)
    one = runtime.execute(parse_invocation({"cycle":"15m", "scheduled_at":first_at.isoformat()}), context=FakeContext())
    snapshot(tmp_path, second_at)
    two = runtime.execute(parse_invocation({"cycle":"15m", "scheduled_at":second_at.isoformat()}), context=FakeContext())
    assert one["cycle"]["cycle_id"] != two["cycle"]["cycle_id"]


def test_lambda_and_direct_core_produce_equivalent_results(tmp_path: Path):
    from v22.core import DeterministicBrainCore, LegacySnapshotCollector
    from v22.storage import BrainRepository, Database

    at = datetime(2026,8,17,6,0,tzinfo=timezone.utc)
    snapshot(tmp_path, at)

    direct_db = Database(f"sqlite:///{tmp_path/'direct.db'}")
    direct_db.migrate()
    direct = DeterministicBrainCore(BrainRepository(direct_db), LegacySnapshotCollector(tmp_path))
    direct_result = direct.run(parse_invocation({"cycle":"15m", "scheduled_at":at.isoformat()}).cycle_type, at, workflow_id="equivalence")

    lambda_runtime = LambdaRuntime(
        database_url=f"sqlite:///{tmp_path/'lambda.db'}",
        data_root=tmp_path,
        minimum_remaining_ms=10_000,
        auto_migrate=True,
    )
    lambda_result = lambda_runtime.execute(
        parse_invocation({"cycle":"15m", "scheduled_at":at.isoformat(), "workflow_id":"equivalence"}),
        context=FakeContext(),
    )["cycle"]

    assert lambda_result["status"] == direct_result.status
    assert lambda_result["expected_assets"] == direct_result.expected_assets
    assert lambda_result["analysed_assets"] == direct_result.analysed_assets
    assert lambda_result["evidence_records"] == direct_result.evidence_records
    assert lambda_result["observation_records"] == direct_result.observation_records
    assert lambda_result["anomalies"] == direct_result.anomalies
    assert lambda_result["failures"] == direct_result.failures
