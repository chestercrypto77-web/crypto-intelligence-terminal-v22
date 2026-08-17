from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any

from v22 import __version__
from v22.contracts import (
    CoverageContract, CycleContract, CycleStatus, CycleType, DataQuality,
    EvidenceContract, ObservationContract, Provenance,
)
from v22.storage import BrainRepository
from .deterministic import anomaly_level, calculate
from .sources import LegacySnapshotCollector
from .validation import validate_asset


@dataclass(frozen=True)
class CycleResult:
    cycle_id: str
    status: str
    expected_assets: int
    analysed_assets: int
    evidence_records: int
    observation_records: int
    anomalies: dict[str, str]
    failures: dict[str, str]


class DeterministicBrainCore:
    """Stage-2 deterministic collection -> validation -> calculation -> persistence."""

    def __init__(self, repo: BrainRepository, collector: LegacySnapshotCollector, *, software_commit: str | None = None):
        self.repo = repo
        self.collector = collector
        self.provenance = Provenance(
            brain_version=__version__, software_commit=software_commit or os.getenv("GITHUB_SHA", "local"),
            calculation_version="stage2-v1", schema_version="002",
        )

    def run(self, cycle_type: CycleType, scheduled_at: datetime, *, workflow_id: str | None = None) -> CycleResult:
        if scheduled_at.tzinfo is None:
            raise ValueError("scheduled_at must be timezone-aware")
        # Collect first so the canonical cycle records the true requested asset count.
        try:
            batch = self.collector.collect(cycle_type, scheduled_at)
            expected_assets = len(batch.requested_assets)
        except Exception:
            # We still persist the failed cycle for auditability.
            cycle = CycleContract(cycle_type=cycle_type, scheduled_at=scheduled_at, expected_assets=0,
                                  workflow_id=workflow_id, provenance=self.provenance)
            stored = self.repo.create_cycle(cycle)
            if stored["status"] == CycleStatus.SCHEDULED.value:
                self.repo.transition_cycle(stored["cycle_id"], CycleStatus.STARTED)
                self.repo.transition_cycle(stored["cycle_id"], CycleStatus.COLLECTING)
                self.repo.transition_cycle(stored["cycle_id"], CycleStatus.FAILED, error="collection failed")
            raise

        cycle = CycleContract(cycle_type=cycle_type, scheduled_at=scheduled_at, expected_assets=expected_assets,
                              workflow_id=workflow_id, provenance=self.provenance)
        stored = self.repo.create_cycle(cycle)
        cycle_id = stored["cycle_id"]
        if stored["status"] in {CycleStatus.COMPLETED.value, CycleStatus.PARTIAL.value, CycleStatus.FAILED.value}:
            return self._result(cycle_id, {}, {})
        if stored["status"] != CycleStatus.SCHEDULED.value:
            raise RuntimeError(f"cycle {cycle_id} is already in progress: {stored['status']}")

        self.repo.transition_cycle(cycle_id, CycleStatus.STARTED)
        self.repo.transition_cycle(cycle_id, CycleStatus.COLLECTING)
        self.repo.transition_cycle(cycle_id, CycleStatus.VALIDATING)

        evidence_count = 0
        observation_count = 0
        failures: dict[str, str] = {}
        anomalies: dict[str, str] = {}
        asset_map = {a.asset_id: a for a in batch.assets}

        # Unavailable or unnamed requested assets are explicit coverage failures.
        for asset_id in batch.requested_assets:
            if asset_id not in asset_map:
                reason = "source unavailable" if asset_id in batch.unavailable_assets else "requested asset missing from snapshot"
                failures[asset_id] = reason
                self.repo.upsert_coverage(CoverageContract(
                    cycle_id=cycle_id, asset_id=asset_id, evidence_collected=False,
                    deterministic_completed=False, quality=DataQuality.PARTIAL, failure_reason=reason,
                ))

        validated: list[tuple[Any, Any]] = []
        for asset in batch.assets:
            result = validate_asset(asset, cycle_type, scheduled_at)
            if result.quality in {DataQuality.INVALID, DataQuality.STALE}:
                reason = "; ".join(result.reasons) or result.quality.value
                failures[asset.asset_id] = reason
                self.repo.upsert_coverage(CoverageContract(
                    cycle_id=cycle_id, asset_id=asset.asset_id, evidence_collected=bool(asset.metrics),
                    deterministic_completed=False, quality=result.quality, failure_reason=reason,
                ))
                continue
            validated.append((asset, result))

        self.repo.transition_cycle(cycle_id, CycleStatus.CALCULATING)
        for asset, validation in validated:
            try:
                metric_values: dict[str, Any] = {}
                evidence_ids: dict[str, str] = {}
                for metric in asset.metrics:
                    ev = EvidenceContract(
                        cycle_id=cycle_id, asset_id=asset.asset_id, metric=metric.name, value=metric.value,
                        source=asset.source, source_timestamp=metric.source_timestamp,
                        retrieved_at=batch.generated_at, quality=validation.quality, unit=metric.unit,
                        raw_reference=asset.raw_reference, metadata={**dict(asset.metadata), **dict(metric.metadata)},
                    )
                    evidence_ids[metric.name] = self.repo.record_evidence(ev)
                    metric_values[metric.name] = metric.value
                    evidence_count += 1

                derived = calculate(cycle_type, metric_values)
                level, reasons = anomaly_level(cycle_type, metric_values, derived)
                for item in derived:
                    refs = tuple(evidence_ids[n] for n in item.evidence_metrics if n in evidence_ids)
                    obs = ObservationContract(
                        cycle_id=cycle_id, asset_id=asset.asset_id, metric=item.metric, value=item.value,
                        observed_at=asset.source_timestamp, calculation=item.calculation,
                        quality=validation.quality, evidence_ids=refs, metadata=item.metadata,
                    )
                    self.repo.record_observation(obs); observation_count += 1

                # Anomaly classification is deterministic and stored as an observation, not an AI finding.
                anomaly_refs = tuple(evidence_ids.values())
                self.repo.record_observation(ObservationContract(
                    cycle_id=cycle_id, asset_id=asset.asset_id, metric="anomaly_level", value=level.value,
                    observed_at=asset.source_timestamp, calculation="deterministic_anomaly_v1",
                    quality=validation.quality, evidence_ids=anomaly_refs,
                    metadata={"reasons": list(reasons)},
                ))
                observation_count += 1
                anomalies[asset.asset_id] = level.value
                self.repo.upsert_coverage(CoverageContract(
                    cycle_id=cycle_id, asset_id=asset.asset_id, evidence_collected=True,
                    deterministic_completed=True, quality=validation.quality,
                ))
            except Exception as exc:
                reason = f"deterministic calculation failed: {type(exc).__name__}: {exc}"
                failures[asset.asset_id] = reason
                self.repo.upsert_coverage(CoverageContract(
                    cycle_id=cycle_id, asset_id=asset.asset_id, evidence_collected=bool(asset.metrics),
                    deterministic_completed=False, quality=DataQuality.PARTIAL, failure_reason=reason,
                ))

        self.repo.transition_cycle(cycle_id, CycleStatus.PERSISTING)
        final = self.repo.finalise_cycle(cycle_id)
        return CycleResult(
            cycle_id=cycle_id, status=final["status"], expected_assets=int(final.get("expected_assets") or 0),
            analysed_assets=int(final.get("analysed_assets") or 0), evidence_records=evidence_count,
            observation_records=observation_count, anomalies=anomalies, failures=failures,
        )

    def _result(self, cycle_id: str, anomalies: dict[str, str], failures: dict[str, str]) -> CycleResult:
        row = self.repo.get_cycle(cycle_id)
        ph = "?" if self.repo.db.kind == "sqlite" else "%s"
        e = int(self.repo.db.scalar(f"SELECT COUNT(*) FROM evidence_records WHERE cycle_id={ph}", (cycle_id,), 0) or 0)
        o = int(self.repo.db.scalar(f"SELECT COUNT(*) FROM observation_records WHERE cycle_id={ph}", (cycle_id,), 0) or 0)
        return CycleResult(cycle_id=cycle_id, status=row["status"], expected_assets=int(row.get("expected_assets") or 0),
                           analysed_assets=int(row.get("analysed_assets") or 0), evidence_records=e,
                           observation_records=o, anomalies=anomalies, failures=failures)
