from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Any

from v22.contracts import CycleType, DataQuality
from .sources import CollectedAsset


@dataclass(frozen=True)
class ValidationResult:
    quality: DataQuality
    reasons: tuple[str, ...]


MAX_AGE_SECONDS = {
    CycleType.MICRO_5M: 15 * 60,
    CycleType.MARKET_15M: 45 * 60,
}


def _finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    return isinstance(value, str)


def validate_asset(asset: CollectedAsset, cycle_type: CycleType, scheduled_at: datetime) -> ValidationResult:
    reasons = []
    if not asset.metrics:
        return ValidationResult(DataQuality.INVALID, ("no metrics collected",))
    age = (scheduled_at - asset.source_timestamp).total_seconds()
    if age > MAX_AGE_SECONDS[cycle_type]:
        reasons.append(f"source stale by {int(age)} seconds")
    invalid = [m.name for m in asset.metrics if not _finite_number(m.value)]
    if invalid:
        reasons.append("non-finite metrics: " + ",".join(invalid))
    if any("stale" in r for r in reasons):
        return ValidationResult(DataQuality.STALE, tuple(reasons))
    if invalid:
        return ValidationResult(DataQuality.INVALID, tuple(reasons))
    # Missing optional metrics are tolerated, but sparse rows are marked degraded.
    minimum = 6 if cycle_type == CycleType.MICRO_5M else 5
    if len(asset.metrics) < minimum:
        reasons.append(f"only {len(asset.metrics)} usable metrics")
        return ValidationResult(DataQuality.DEGRADED, tuple(reasons))
    return ValidationResult(DataQuality.GOOD, tuple(reasons))
