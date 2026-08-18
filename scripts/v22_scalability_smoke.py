#!/usr/bin/env python3
"""Offline V22.9 100-asset scalability smoke test.

No external network or credentials are used. The test verifies the production
collector's bounded concurrency/tier policy and then runs a full 100-asset
MICRO_5M deterministic cycle into temporary SQLite memory.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v22.contracts import CycleType
from v22.core import DeterministicBrainCore, LiveAssetSpec, LiveEvidenceCollector
from v22.storage import BrainRepository, Database


class FakeMarket:
    def __init__(self, delay=0.001):
        self.delay = delay
        self.active = 0
        self.max_active = 0
        self.calls = 0
        self.lock = threading.Lock()

    def get_json(self, path, params):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.calls += 1
        try:
            time.sleep(self.delay)
            step = {"1m": 60_000, "5m": 300_000, "15m": 900_000}[params["interval"]]
            end = int(params["endTime"])
            limit = int(params["limit"])
            start = end - limit * step
            return [[
                start + i * step, str(100 + i * .1), str(101 + i * .1), str(99 + i * .1),
                str(100.25 + i * .1), str(1000 + i % 11 * 10), start + (i + 1) * step - 1,
                "0", 1, "0", "0", "0"
            ] for i in range(limit)]
        finally:
            with self.lock:
                self.active -= 1


def specs():
    out = []
    for i in range(100):
        tier = "A" if i < 20 else "B" if i < 60 else "C"
        depth = "FULL" if tier == "A" else "SCREEN"
        out.append(LiveAssetSpec(f"T{i:03d}", f"T{i:03d}USDT", tier, depth))
    return tuple(out)


def main():
    at = datetime(2026, 8, 18, 2, 30, tzinfo=timezone.utc)
    fake = FakeMarket()
    collector = LiveEvidenceCollector(Path.cwd(), http_client=fake, asset_specs=specs(), max_workers=8, batch_size=8)
    with tempfile.TemporaryDirectory() as td:
        db = Database(f"sqlite:///{Path(td)/'brain.db'}")
        db.migrate()
        started = time.monotonic()
        result = DeterministicBrainCore(BrainRepository(db), collector).run(CycleType.MICRO_5M, at, soft_deadline_seconds=210)
        elapsed = time.monotonic() - started
        payload = {
            "status": result.status,
            "expected_assets": result.expected_assets,
            "analysed_assets": result.analysed_assets,
            "http_calls": fake.calls,
            "max_concurrent_http": fake.max_active,
            "elapsed_seconds": round(elapsed, 3),
            "evidence_records": result.evidence_records,
            "observation_records": result.observation_records,
            "ai_calls": int(db.scalar("SELECT COUNT(*) FROM ai_calls", default=0) or 0),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        assert payload["status"] == "COMPLETED"
        assert payload["analysed_assets"] == 100
        assert payload["http_calls"] == 120
        assert 1 < payload["max_concurrent_http"] <= 8
        assert payload["ai_calls"] == 0


if __name__ == "__main__":
    main()
