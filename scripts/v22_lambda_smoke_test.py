from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v22.runtime import lambda_handler, reset_runtime_cache


class FakeContext:
    aws_request_id = "stage4-smoke-request"
    function_name = "v22-stage4-local"
    def __init__(self, remaining_ms: int = 120_000):
        self.remaining_ms = remaining_ms
    def get_remaining_time_in_millis(self) -> int:
        return self.remaining_ms


def _write_snapshot(root: Path, scheduled: datetime) -> None:
    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": scheduled.isoformat(),
        "health": {"assets_requested": 1, "unavailable_assets": []},
        "signals": [{
            "symbol": "BTC", "price": 65000.0, "return_15m": 0.2, "return_1h": 0.8,
            "return_4h": 1.4, "return_24h": 2.5, "rvol": 1.7, "rvol_delta": 0.4,
            "rsi": 58.0, "rsi_delta": 3.0, "macd_histogram": 1.0, "macd_delta": 0.2,
            "breakout": True, "breakdown": False, "candle_time": scheduled.isoformat(),
            "data_source": "stage4 synthetic",
        }],
    }
    (data / "observer_latest.json").write_text(json.dumps(payload), encoding="utf-8")


def main() -> int:
    scheduled = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    with tempfile.TemporaryDirectory(prefix="v22-stage4-") as tmp:
        root = Path(tmp)
        _write_snapshot(root, scheduled)
        db_path = root / "brain.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
        os.environ["V22_DATA_ROOT"] = str(root)
        os.environ["V22_AUTO_MIGRATE"] = "1"
        reset_runtime_cache()

        event = {"cycle": "15m", "scheduled_at": scheduled.isoformat(), "workflow_id": "stage4-smoke"}
        first = lambda_handler(event, FakeContext())
        second = lambda_handler(event, FakeContext())

        conn = sqlite3.connect(db_path)
        cycle_count = conn.execute("SELECT COUNT(*) FROM brain_cycles").fetchone()[0]
        conn.close()
        assert first["cycle"]["cycle_id"] == second["cycle"]["cycle_id"]
        assert cycle_count == 1
        assert first["cycle"]["status"] == "COMPLETED"
        print(json.dumps({"first": first, "warm_retry": second, "canonical_cycles": cycle_count}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
