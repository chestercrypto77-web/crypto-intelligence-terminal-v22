from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v22.contracts import CycleType
from v22.core import DeterministicBrainCore, LegacySnapshotCollector
from v22.failure import FailureStage, FaultInjector
from v22.storage import BrainRepository, Database

NOW = datetime(2026, 8, 17, 6, 0, tzinfo=timezone.utc)


def row(symbol="BTC"):
    return {
        "symbol": symbol,
        "data_source": "stage3-smoke",
        "candle_time": NOW.isoformat(),
        "price": 65000,
        "return_15m": 0.5,
        "return_1h": 1.1,
        "return_4h": 2.3,
        "return_24h": 3.5,
        "rvol": 1.6,
        "rvol_delta": 0.4,
        "rsi": 61,
        "rsi_delta": 3,
        "macd_histogram": 1.2,
        "macd_delta": 0.3,
        "breakout": False,
        "breakdown": False,
    }


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "data").mkdir()
        (root / "data" / "observer_latest.json").write_text(json.dumps({
            "generated_at": NOW.isoformat(),
            "signals": [row()],
            "health": {"assets_requested": 1, "assets_analysed": 1, "unavailable_assets": []},
        }), encoding="utf-8")

        db = Database("sqlite:///" + str(root / "brain.db"))
        db.migrate()
        repo = BrainRepository(db)
        fault = FaultInjector(
            FailureStage.OBSERVATION_PERSIST,
            asset_id="BTC",
            exc_factory=lambda: OSError("stage3 smoke persistence failure"),
        )
        result = DeterministicBrainCore(
            repo,
            LegacySnapshotCollector(root),
            fault_injector=fault,
        ).run(CycleType.MARKET_15M, NOW)

        event = db.query("SELECT * FROM brain_failure_events")[0]
        coverage = db.query("SELECT * FROM cycle_asset_coverage")[0]
        assert result.status == "PARTIAL"
        assert result.analysed_assets == 0
        assert event["stage"] == "OBSERVATION_PERSIST"
        assert bool(event["retryable"])
        assert not bool(coverage["deterministic_completed"])
        assert db.scalar("SELECT COUNT(*) FROM ai_calls") == 0

        print(json.dumps({
            "status": "passed",
            "cycle_status": result.status,
            "analysed_assets": result.analysed_assets,
            "failure_stage": event["stage"],
            "retryable": bool(event["retryable"]),
            "failure_events": result.failure_events,
            "ai_calls": 0,
        }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
