from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
from typing import Any, Callable


class FailureStage(str, Enum):
    COLLECTION = "COLLECTION"
    VALIDATION = "VALIDATION"
    EVIDENCE_PERSIST = "EVIDENCE_PERSIST"
    CALCULATION = "CALCULATION"
    OBSERVATION_PERSIST = "OBSERVATION_PERSIST"
    COVERAGE_PERSIST = "COVERAGE_PERSIST"
    FINALISE = "FINALISE"
    DUPLICATE_EXECUTION = "DUPLICATE_EXECUTION"


class FailureSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class FailureEvent:
    cycle_id: str
    stage: FailureStage
    component: str
    error_type: str
    message: str
    severity: FailureSeverity
    retryable: bool
    asset_id: str | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    details: dict[str, Any] | None = None

    @property
    def fingerprint(self) -> str:
        canonical = "|".join([
            self.stage.value,
            self.component,
            self.asset_id or "",
            self.error_type,
            self.message,
        ])
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class FailureEngine:
    """Classifies and persists truthful failure evidence.

    The engine is deliberately small. It does not retry work itself; orchestration
    will own retries later. Its job is to make every recoverable failure observable
    and to keep status semantics consistent before Restate/Lambda are introduced.
    """

    def __init__(self, repo):
        self.repo = repo

    def classify(
        self,
        *,
        cycle_id: str,
        stage: FailureStage,
        component: str,
        exc: Exception,
        asset_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> FailureEvent:
        error_type = type(exc).__name__
        message = str(exc) or error_type

        if isinstance(exc, (FileNotFoundError, ValueError, TypeError, KeyError)):
            retryable = False
        elif isinstance(exc, (TimeoutError, ConnectionError, OSError)):
            retryable = True
        else:
            retryable = stage in {
                FailureStage.EVIDENCE_PERSIST,
                FailureStage.OBSERVATION_PERSIST,
                FailureStage.COVERAGE_PERSIST,
                FailureStage.FINALISE,
            }

        severity = FailureSeverity.ERROR
        if stage == FailureStage.FINALISE:
            severity = FailureSeverity.CRITICAL
        elif stage == FailureStage.DUPLICATE_EXECUTION:
            severity = FailureSeverity.WARNING

        return FailureEvent(
            cycle_id=cycle_id,
            stage=stage,
            component=component,
            error_type=error_type,
            message=message,
            severity=severity,
            retryable=retryable,
            asset_id=asset_id,
            occurred_at=datetime.now(timezone.utc),
            details=details or {},
        )

    def record(self, event: FailureEvent) -> str | None:
        return self.repo.record_failure_event(event)

    def capture(self, **kwargs) -> FailureEvent:
        event = self.classify(**kwargs)
        self.record(event)
        return event


class FaultInjector:
    """Test-only deterministic fault hook.

    Production code passes no injector. Tests can request a one-shot failure at a
    named stage and optional asset, allowing failure semantics to be proven without
    depending on flaky external services.
    """

    def __init__(self, stage: FailureStage, *, asset_id: str | None = None, exc_factory: Callable[[], Exception] | None = None):
        self.stage = stage
        self.asset_id = asset_id
        self.exc_factory = exc_factory or (lambda: RuntimeError(f"injected failure at {stage.value}"))
        self.used = False

    def __call__(self, stage: FailureStage, asset_id: str | None = None) -> None:
        if self.used or stage != self.stage:
            return
        if self.asset_id is not None and self.asset_id != asset_id:
            return
        self.used = True
        raise self.exc_factory()
