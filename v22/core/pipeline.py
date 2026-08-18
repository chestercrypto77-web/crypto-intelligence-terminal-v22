from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import os
import time
from typing import Any, Callable

from v22 import __version__
from v22.contracts import (
    CoverageContract, CycleContract, CycleStatus, CycleType, DataQuality,
    EvidenceContract, ObservationContract, Provenance,
)
from v22.failure import FailureEngine, FailureStage
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
    failure_events: int = 0
    timings: dict[str, float] = field(default_factory=dict)


class DeterministicBrainCore:
    """Stage-3 deterministic Brain Core with truthful failure semantics.

    The core remains normal Python. Restate/Lambda/AI are intentionally absent.
    FailureEngine records structured failure evidence wherever persistence remains
    reachable, while cycle coverage determines COMPLETED/PARTIAL/FAILED truth.
    """

    def __init__(
        self,
        repo: BrainRepository,
        collector: Any,
        *,
        software_commit: str | None = None,
        fault_injector: Callable[[FailureStage, str | None], None] | None = None,
    ):
        self.repo = repo
        self.collector = collector
        self.failure_engine = FailureEngine(repo)
        self.fault_injector = fault_injector
        self.provenance = Provenance(
            brain_version=__version__,
            software_commit=software_commit or os.getenv("GITHUB_SHA", "local"),
            calculation_version="stage9-scalable-v1",
            schema_version="004",
        )

    def _trip(self, stage: FailureStage, asset_id: str | None = None) -> None:
        if self.fault_injector:
            self.fault_injector(stage, asset_id)

    def _capture(self, cycle_id: str, stage: FailureStage, component: str, exc: Exception, *, asset_id: str | None = None, details: dict[str, Any] | None = None) -> None:
        try:
            self.failure_engine.capture(
                cycle_id=cycle_id,
                stage=stage,
                component=component,
                exc=exc,
                asset_id=asset_id,
                details=details,
            )
        except Exception:
            # A database outage can make the failure ledger unreachable. Never hide
            # the original fault with a secondary audit-write exception.
            pass

    def _mark_failed(self, cycle_id: str, message: str) -> None:
        try:
            current = self.repo.get_cycle(cycle_id)
            if current and current["status"] not in {CycleStatus.COMPLETED.value, CycleStatus.PARTIAL.value, CycleStatus.FAILED.value}:
                self.repo.transition_cycle(cycle_id, CycleStatus.FAILED, error=message)
        except Exception:
            pass

    def run(
        self,
        cycle_type: CycleType,
        scheduled_at: datetime,
        *,
        workflow_id: str | None = None,
        soft_deadline_seconds: float | None = None,
    ) -> CycleResult:
        if scheduled_at.tzinfo is None:
            raise ValueError("scheduled_at must be timezone-aware")
        run_started = time.monotonic()
        deadline = run_started + soft_deadline_seconds if soft_deadline_seconds and soft_deadline_seconds > 0 else None
        timings: dict[str, float] = {}

        # Collection happens first so expected_assets reflects the source's own
        # coverage declaration. Collection failures still receive a canonical cycle.
        try:
            self._trip(FailureStage.COLLECTION)
            collection_started = time.monotonic()
            batch = self.collector.collect(cycle_type, scheduled_at)
            timings["collection_seconds"] = round(time.monotonic() - collection_started, 3)
            expected_assets = len(batch.requested_assets)
        except Exception as exc:
            cycle = CycleContract(
                cycle_type=cycle_type,
                scheduled_at=scheduled_at,
                expected_assets=0,
                workflow_id=workflow_id,
                provenance=self.provenance,
            )
            stored = self.repo.create_cycle(cycle)
            cycle_id = stored["cycle_id"]
            if stored["status"] == CycleStatus.SCHEDULED.value:
                self.repo.transition_cycle(cycle_id, CycleStatus.STARTED)
                self.repo.transition_cycle(cycle_id, CycleStatus.COLLECTING)
            self._capture(cycle_id, FailureStage.COLLECTION, self.collector.__class__.__name__, exc)
            self._mark_failed(cycle_id, "collection failed")
            raise

        cycle = CycleContract(
            cycle_type=cycle_type,
            scheduled_at=scheduled_at,
            expected_assets=expected_assets,
            workflow_id=workflow_id,
            provenance=self.provenance,
        )
        stored = self.repo.create_cycle(cycle)
        cycle_id = stored["cycle_id"]
        if stored["status"] in {CycleStatus.COMPLETED.value, CycleStatus.PARTIAL.value, CycleStatus.FAILED.value}:
            return self._result(cycle_id, {}, {})
        if stored["status"] != CycleStatus.SCHEDULED.value:
            exc = RuntimeError(f"cycle {cycle_id} is already in progress: {stored['status']}")
            self._capture(cycle_id, FailureStage.DUPLICATE_EXECUTION, "CycleController", exc)
            raise exc

        self.repo.transition_cycle(cycle_id, CycleStatus.STARTED)
        self.repo.transition_cycle(cycle_id, CycleStatus.COLLECTING)
        self.repo.transition_cycle(cycle_id, CycleStatus.VALIDATING)

        evidence_count = 0
        observation_count = 0
        failures: dict[str, str] = {}
        anomalies: dict[str, str] = {}
        asset_map = {a.asset_id: a for a in batch.assets}

        # Missing/unavailable requested assets are explicit failure evidence.
        for asset_id in batch.requested_assets:
            if asset_id not in asset_map:
                reason = "source unavailable" if asset_id in batch.unavailable_assets else "requested asset missing from snapshot"
                failures[asset_id] = reason
                exc = RuntimeError(reason)
                self._capture(cycle_id, FailureStage.COLLECTION, self.collector.__class__.__name__, exc, asset_id=asset_id)
                try:
                    self._trip(FailureStage.COVERAGE_PERSIST, asset_id)
                    self.repo.upsert_coverage(CoverageContract(
                        cycle_id=cycle_id,
                        asset_id=asset_id,
                        evidence_collected=False,
                        deterministic_completed=False,
                        quality=DataQuality.PARTIAL,
                        failure_reason=reason,
                    ))
                except Exception as coverage_exc:
                    self._capture(cycle_id, FailureStage.COVERAGE_PERSIST, "BrainRepository", coverage_exc, asset_id=asset_id)

        validation_started = time.monotonic()
        validated: list[tuple[Any, Any]] = []
        for asset in batch.assets:
            try:
                self._trip(FailureStage.VALIDATION, asset.asset_id)
                validation = validate_asset(asset, cycle_type, scheduled_at)
            except Exception as exc:
                reason = f"validation failed: {type(exc).__name__}: {exc}"
                failures[asset.asset_id] = reason
                self._capture(cycle_id, FailureStage.VALIDATION, "EvidenceValidator", exc, asset_id=asset.asset_id)
                try:
                    self.repo.upsert_coverage(CoverageContract(
                        cycle_id=cycle_id,
                        asset_id=asset.asset_id,
                        evidence_collected=bool(asset.metrics),
                        deterministic_completed=False,
                        quality=DataQuality.INVALID,
                        failure_reason=reason,
                    ))
                except Exception as coverage_exc:
                    self._capture(cycle_id, FailureStage.COVERAGE_PERSIST, "BrainRepository", coverage_exc, asset_id=asset.asset_id)
                continue

            if validation.quality in {DataQuality.INVALID, DataQuality.STALE}:
                reason = "; ".join(validation.reasons) or validation.quality.value
                failures[asset.asset_id] = reason
                exc = ValueError(reason)
                self._capture(cycle_id, FailureStage.VALIDATION, "EvidenceValidator", exc, asset_id=asset.asset_id, details={"quality": validation.quality.value})
                try:
                    self.repo.upsert_coverage(CoverageContract(
                        cycle_id=cycle_id,
                        asset_id=asset.asset_id,
                        evidence_collected=bool(asset.metrics),
                        deterministic_completed=False,
                        quality=validation.quality,
                        failure_reason=reason,
                    ))
                except Exception as coverage_exc:
                    self._capture(cycle_id, FailureStage.COVERAGE_PERSIST, "BrainRepository", coverage_exc, asset_id=asset.asset_id)
                continue
            validated.append((asset, validation))
        timings["validation_seconds"] = round(time.monotonic() - validation_started, 3)

        self.repo.transition_cycle(cycle_id, CycleStatus.CALCULATING)
        calculating_started = time.monotonic()
        for index, (asset, validation) in enumerate(validated):
            if deadline is not None and time.monotonic() >= deadline:
                reason = "soft runtime deadline reached before asset processing"
                for remaining, _ in validated[index:]:
                    failures.setdefault(remaining.asset_id, reason)
                    self._record_failed_coverage(cycle_id, remaining.asset_id, False, reason)
                break
            metric_values: dict[str, Any] = {}
            evidence_ids: dict[str, str] = {}
            try:
                for metric in asset.metrics:
                    ev = EvidenceContract(
                        cycle_id=cycle_id,
                        asset_id=asset.asset_id,
                        metric=metric.name,
                        value=metric.value,
                        source=asset.source,
                        source_timestamp=metric.source_timestamp,
                        retrieved_at=batch.generated_at,
                        quality=validation.quality,
                        unit=metric.unit,
                        raw_reference=asset.raw_reference,
                        metadata={**dict(asset.metadata), **dict(metric.metadata)},
                    )
                    self._trip(FailureStage.EVIDENCE_PERSIST, asset.asset_id)
                    evidence_ids[metric.name] = self.repo.record_evidence(ev)
                    metric_values[metric.name] = metric.value
                    evidence_count += 1
            except Exception as exc:
                reason = f"evidence persistence failed: {type(exc).__name__}: {exc}"
                failures[asset.asset_id] = reason
                self._capture(cycle_id, FailureStage.EVIDENCE_PERSIST, "BrainRepository", exc, asset_id=asset.asset_id)
                self._record_failed_coverage(cycle_id, asset.asset_id, bool(evidence_ids), reason)
                continue

            try:
                self._trip(FailureStage.CALCULATION, asset.asset_id)
                observation_depth = str(asset.metadata.get("observation_depth") or "FULL").upper()
                observation_tier = str(asset.metadata.get("observation_tier") or "A").upper()
                derived = calculate(cycle_type, metric_values, observation_depth=observation_depth)
                level, reasons = anomaly_level(cycle_type, metric_values, derived)
            except Exception as exc:
                reason = f"deterministic calculation failed: {type(exc).__name__}: {exc}"
                failures[asset.asset_id] = reason
                self._capture(cycle_id, FailureStage.CALCULATION, "DeterministicIntelligence", exc, asset_id=asset.asset_id)
                self._record_failed_coverage(cycle_id, asset.asset_id, True, reason)
                continue

            try:
                for item in derived:
                    refs = tuple(evidence_ids[n] for n in item.evidence_metrics if n in evidence_ids)
                    obs = ObservationContract(
                        cycle_id=cycle_id,
                        asset_id=asset.asset_id,
                        metric=item.metric,
                        value=item.value,
                        observed_at=asset.source_timestamp,
                        calculation=item.calculation,
                        quality=validation.quality,
                        evidence_ids=refs,
                        metadata={**dict(item.metadata), "observation_tier": observation_tier, "observation_depth": observation_depth},
                    )
                    self._trip(FailureStage.OBSERVATION_PERSIST, asset.asset_id)
                    self.repo.record_observation(obs)
                    observation_count += 1

                anomaly_refs = tuple(evidence_ids.values())
                self._trip(FailureStage.OBSERVATION_PERSIST, asset.asset_id)
                self.repo.record_observation(ObservationContract(
                    cycle_id=cycle_id,
                    asset_id=asset.asset_id,
                    metric="anomaly_level",
                    value=level.value,
                    observed_at=asset.source_timestamp,
                    calculation="deterministic_anomaly_v1",
                    quality=validation.quality,
                    evidence_ids=anomaly_refs,
                    metadata={"reasons": list(reasons), "observation_tier": observation_tier, "observation_depth": observation_depth},
                ))
                observation_count += 1
            except Exception as exc:
                reason = f"observation persistence failed: {type(exc).__name__}: {exc}"
                failures[asset.asset_id] = reason
                self._capture(cycle_id, FailureStage.OBSERVATION_PERSIST, "BrainRepository", exc, asset_id=asset.asset_id)
                self._record_failed_coverage(cycle_id, asset.asset_id, True, reason)
                continue

            anomalies[asset.asset_id] = level.value
            try:
                self._trip(FailureStage.COVERAGE_PERSIST, asset.asset_id)
                self.repo.upsert_coverage(CoverageContract(
                    cycle_id=cycle_id,
                    asset_id=asset.asset_id,
                    evidence_collected=True,
                    deterministic_completed=True,
                    quality=validation.quality,
                ))
                self.repo.refresh_cycle_progress(cycle_id)
            except Exception as exc:
                reason = f"coverage persistence failed: {type(exc).__name__}: {exc}"
                failures[asset.asset_id] = reason
                self._capture(cycle_id, FailureStage.COVERAGE_PERSIST, "BrainRepository", exc, asset_id=asset.asset_id)

        timings["calculating_seconds"] = round(time.monotonic() - calculating_started, 3)
        self.repo.transition_cycle(cycle_id, CycleStatus.PERSISTING)
        finalise_started = time.monotonic()
        try:
            self._trip(FailureStage.FINALISE)
            final = self.repo.finalise_cycle(cycle_id)
            timings["finalise_seconds"] = round(time.monotonic() - finalise_started, 3)
            timings["total_seconds"] = round(time.monotonic() - run_started, 3)
        except Exception as exc:
            self._capture(cycle_id, FailureStage.FINALISE, "BrainRepository", exc)
            self._mark_failed(cycle_id, "finalisation failed")
            raise

        return CycleResult(
            cycle_id=cycle_id,
            status=final["status"],
            expected_assets=int(final.get("expected_assets") or 0),
            analysed_assets=int(final.get("analysed_assets") or 0),
            evidence_records=evidence_count,
            observation_records=observation_count,
            anomalies=anomalies,
            failures=failures,
            failure_events=len(self.repo.list_failure_events(cycle_id)),
            timings=timings,
        )

    def _record_failed_coverage(self, cycle_id: str, asset_id: str, evidence_collected: bool, reason: str) -> None:
        try:
            self._trip(FailureStage.COVERAGE_PERSIST, asset_id)
            self.repo.upsert_coverage(CoverageContract(
                cycle_id=cycle_id,
                asset_id=asset_id,
                evidence_collected=evidence_collected,
                deterministic_completed=False,
                quality=DataQuality.PARTIAL,
                failure_reason=reason,
            ))
        except Exception as exc:
            self._capture(cycle_id, FailureStage.COVERAGE_PERSIST, "BrainRepository", exc, asset_id=asset_id)

    def _result(self, cycle_id: str, anomalies: dict[str, str], failures: dict[str, str]) -> CycleResult:
        row = self.repo.get_cycle(cycle_id)
        ph = "?" if self.repo.db.kind == "sqlite" else "%s"
        e = int(self.repo.db.scalar(f"SELECT COUNT(*) FROM evidence_records WHERE cycle_id={ph}", (cycle_id,), 0) or 0)
        o = int(self.repo.db.scalar(f"SELECT COUNT(*) FROM observation_records WHERE cycle_id={ph}", (cycle_id,), 0) or 0)
        f = int(self.repo.db.scalar(f"SELECT COUNT(*) FROM brain_failure_events WHERE cycle_id={ph}", (cycle_id,), 0) or 0)
        return CycleResult(
            cycle_id=cycle_id,
            status=row["status"],
            expected_assets=int(row.get("expected_assets") or 0),
            analysed_assets=int(row.get("analysed_assets") or 0),
            evidence_records=e,
            observation_records=o,
            anomalies=anomalies,
            failures=failures,
            failure_events=f,
        )
