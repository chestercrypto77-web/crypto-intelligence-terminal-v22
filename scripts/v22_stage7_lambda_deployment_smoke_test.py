#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v22.runtime.lambda_adapter import InvocationRejected, reset_runtime_cache, runtime_from_environment
from v22.runtime.lambda_entry import lambda_handler


class Context:
    aws_request_id = "stage7-smoke-request"
    function_name = "v22-brain-stage7-smoke"
    def get_remaining_time_in_millis(self): return 120_000


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # prove AWS guard prevents disposable SQLite from becoming durable truth
        os.environ["AWS_LAMBDA_FUNCTION_NAME"] = "v22-test"
        os.environ["DATABASE_URL"] = f"sqlite:///{root/'bad.db'}"
        os.environ.pop("V22_ALLOW_EPHEMERAL_SQLITE", None)
        try:
            runtime_from_environment()
        except InvocationRejected as exc:
            assert "Postgres/Neon" in str(exc)
        else:
            raise AssertionError("AWS runtime accepted ephemeral SQLite")

        # local invocation remains supported for deterministic smoke tests
        os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
        os.environ["DATABASE_URL"] = f"sqlite:///{root/'local.db'}"
        os.environ["V22_AUTO_MIGRATE"] = "1"
        os.environ["V22_COLLECTOR_MODE"] = "snapshot"
        os.environ["V22_DATA_ROOT"] = str(root)
        data = root / "data"; data.mkdir()
        at = datetime(2026, 8, 17, 8, 0, tzinfo=timezone.utc)
        (data / "observer_latest.json").write_text(json.dumps({
            "generated_at": at.isoformat(),
            "health": {"assets_requested": 1, "unavailable_assets": []},
            "signals": [{
                "symbol":"ETH", "price":3000, "return_15m":0.1, "return_1h":0.4,
                "return_4h":0.7, "return_24h":1.0, "rvol":1.4, "rvol_delta":0.2,
                "rsi":55, "rsi_delta":1, "macd_histogram":0.2, "macd_delta":0.1,
                "breakout":False, "breakdown":False,
                "candle_time":at.isoformat(), "data_source":"stage7 synthetic"
            }]
        }), encoding="utf-8")
        reset_runtime_cache()
        result = lambda_handler({"cycle":"15m", "scheduled_at":at.isoformat(), "workflow_id":"stage7-smoke"}, Context())
        assert result["ok"] is True
        assert result["adapter_version"] == "stage7-v1"
        assert result["cycle"]["status"] == "COMPLETED"
    print("PASS v22.7 lambda deployment smoke")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
