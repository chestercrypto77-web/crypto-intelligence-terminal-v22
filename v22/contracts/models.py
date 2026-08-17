from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any, Mapping, Sequence
import uuid


class StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class CycleType(StrEnum):
    MICRO_5M = "MICRO_5M"
    MARKET_15M = "MARKET_15M"
    NIGHTLY_LEARNING = "NIGHTLY_LEARNING"
    BACKFILL = "BACKFILL"
    MANUAL_TEST = "MANUAL_TEST"


class CycleStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    STARTED = "STARTED"
    COLLECTING = "COLLECTING"
    VALIDATING = "VALIDATING"
    CALCULATING = "CALCULATING"
    ANALYSING = "ANALYSING"
    PERSISTING = "PERSISTING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class DataQuality(StrEnum):
    GOOD = "GOOD"
    DEGRADED = "DEGRADED"
    STALE = "STALE"
    PARTIAL = "PARTIAL"
    INVALID = "INVALID"


class AnomalyLevel(StrEnum):
    NORMAL = "NORMAL"
    INTERESTING = "INTERESTING"
    SIGNIFICANT = "SIGNIFICANT"
    ANOMALOUS = "ANOMALOUS"
    CRITICAL = "CRITICAL"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def stable_key(*parts: Any) -> str:
    canonical = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _json_ready(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return ensure_utc(value).isoformat()
    if isinstance(value, Mapping):
        return {str(k): _json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(v) for v in value]
    return value


@dataclass(frozen=True)
class Provenance:
    brain_version: str
    software_commit: str = "unknown"
    calculation_version: str = "v1"
    schema_version: str = "002"
    model_provider: str | None = None
    model_name: str | None = None
    prompt_version: str | None = None

    def __post_init__(self) -> None:
        if not self.brain_version.strip():
            raise ValueError("brain_version is required")

    def as_json(self) -> str:
        return json.dumps(_json_ready(asdict(self)), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class CycleContract:
    cycle_type: CycleType
    scheduled_at: datetime
    provenance: Provenance
    cycle_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: CycleStatus = CycleStatus.SCHEDULED
    workflow_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    expected_assets: int = 0
    error: str | None = None

    def __post_init__(self) -> None:
        ensure_utc(self.scheduled_at)
        if self.started_at:
            ensure_utc(self.started_at)
        if self.completed_at:
            ensure_utc(self.completed_at)
        if self.expected_assets < 0:
            raise ValueError("expected_assets cannot be negative")
        uuid.UUID(self.cycle_id)

    @property
    def cycle_key(self) -> str:
        return stable_key(self.cycle_type.value, ensure_utc(self.scheduled_at).isoformat())


@dataclass(frozen=True)
class EvidenceContract:
    cycle_id: str
    asset_id: str
    metric: str
    value: float | int | str | bool | None
    source: str
    source_timestamp: datetime
    retrieved_at: datetime
    quality: DataQuality = DataQuality.GOOD
    unit: str | None = None
    raw_reference: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    evidence_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        uuid.UUID(self.cycle_id); uuid.UUID(self.evidence_id)
        ensure_utc(self.source_timestamp); ensure_utc(self.retrieved_at)
        for name, value in (("asset_id", self.asset_id), ("metric", self.metric), ("source", self.source)):
            if not value.strip():
                raise ValueError(f"{name} is required")

    @property
    def idempotency_key(self) -> str:
        return stable_key(self.cycle_id, self.asset_id, self.metric, self.source, ensure_utc(self.source_timestamp).isoformat())


@dataclass(frozen=True)
class ObservationContract:
    cycle_id: str
    asset_id: str
    metric: str
    value: float | int | str | bool | None
    observed_at: datetime
    calculation: str
    quality: DataQuality = DataQuality.GOOD
    evidence_ids: Sequence[str] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    observation_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        uuid.UUID(self.cycle_id); uuid.UUID(self.observation_id); ensure_utc(self.observed_at)
        if not self.asset_id.strip() or not self.metric.strip() or not self.calculation.strip():
            raise ValueError("asset_id, metric and calculation are required")
        for evidence_id in self.evidence_ids:
            uuid.UUID(evidence_id)

    @property
    def idempotency_key(self) -> str:
        return stable_key(self.cycle_id, self.asset_id, self.metric, self.calculation, ensure_utc(self.observed_at).isoformat())


@dataclass(frozen=True)
class CoverageContract:
    cycle_id: str
    asset_id: str
    expected: bool = True
    evidence_collected: bool = False
    deterministic_completed: bool = False
    ai_requested: bool = False
    ai_completed: bool = False
    quality: DataQuality = DataQuality.GOOD
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        uuid.UUID(self.cycle_id)
        if not self.asset_id.strip():
            raise ValueError("asset_id is required")
        if self.ai_completed and not self.ai_requested:
            raise ValueError("ai_completed cannot be true unless ai_requested is true")


@dataclass(frozen=True)
class FindingContract:
    cycle_id: str
    specialist: str
    claim: str
    evidence_ids: Sequence[str]
    created_at: datetime
    provenance: Provenance
    supporting_factors: Sequence[str] = field(default_factory=tuple)
    contradicting_factors: Sequence[str] = field(default_factory=tuple)
    uncertainties: Sequence[str] = field(default_factory=tuple)
    anomaly_level: AnomalyLevel = AnomalyLevel.INTERESTING
    finding_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        uuid.UUID(self.cycle_id); uuid.UUID(self.finding_id); ensure_utc(self.created_at)
        if not self.specialist.strip() or not self.claim.strip():
            raise ValueError("specialist and claim are required")
        if not self.evidence_ids:
            raise ValueError("AI findings must reference at least one evidence record")
        for evidence_id in self.evidence_ids:
            uuid.UUID(evidence_id)


@dataclass(frozen=True)
class SynthesisContract:
    cycle_id: str
    summary: str
    finding_ids: Sequence[str]
    created_at: datetime
    provenance: Provenance
    disagreements: Sequence[str] = field(default_factory=tuple)
    synthesis_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        uuid.UUID(self.cycle_id); uuid.UUID(self.synthesis_id); ensure_utc(self.created_at)
        if not self.summary.strip() or not self.finding_ids:
            raise ValueError("summary and finding_ids are required")
        for finding_id in self.finding_ids:
            uuid.UUID(finding_id)


@dataclass(frozen=True)
class EpisodeContract:
    episode_type: str
    opened_at: datetime
    asset_id: str | None = None
    cycle_id: str | None = None
    description: str | None = None
    closed_at: datetime | None = None
    episode_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        uuid.UUID(self.episode_id); ensure_utc(self.opened_at)
        if self.closed_at:
            ensure_utc(self.closed_at)
        if self.cycle_id:
            uuid.UUID(self.cycle_id)
        if not self.episode_type.strip():
            raise ValueError("episode_type is required")


@dataclass(frozen=True)
class OutcomeContract:
    episode_id: str
    horizon: str
    measured_at: datetime
    metrics: Mapping[str, Any]
    source: str
    outcome_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        uuid.UUID(self.episode_id); uuid.UUID(self.outcome_id); ensure_utc(self.measured_at)
        if not self.horizon.strip() or not self.source.strip():
            raise ValueError("horizon and source are required")


@dataclass(frozen=True)
class AiCallContract:
    cycle_id: str
    specialist: str
    provider: str
    model: str
    invoked_at: datetime
    reason: str
    status: str
    protected_data_check: bool
    call_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    completed_at: datetime | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        uuid.UUID(self.cycle_id); uuid.UUID(self.call_id); ensure_utc(self.invoked_at)
        if self.completed_at:
            ensure_utc(self.completed_at)
        if not self.protected_data_check:
            raise ValueError("AI calls cannot be recorded as approved without protected-data screening")
