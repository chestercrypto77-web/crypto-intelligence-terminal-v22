from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from v22 import __version__
from v22.contracts import CycleType
from v22.core import DeterministicBrainCore, LegacySnapshotCollector, LiveEvidenceCollector
from v22.storage import BrainRepository, Database


class LambdaContext(Protocol):
    aws_request_id: str
    function_name: str

    def get_remaining_time_in_millis(self) -> int: ...


class InvocationRejected(ValueError):
    """The Lambda invocation is malformed or unsafe to execute."""


@dataclass(frozen=True)
class LambdaInvocation:
    cycle_type: CycleType
    scheduled_at: datetime
    workflow_id: str | None = None


@dataclass(frozen=True)
class LambdaRuntime:
    database_url: str
    data_root: Path
    minimum_remaining_ms: int
    auto_migrate: bool
    collector_factory: Callable[[Path], Any] = LegacySnapshotCollector

    def execute(self, invocation: LambdaInvocation, *, context: LambdaContext | None = None) -> dict[str, Any]:
        _require_time_budget(context, self.minimum_remaining_ms)

        db = Database(self.database_url)
        if self.auto_migrate:
            db.migrate()
        repo = BrainRepository(db)
        collector = self.collector_factory(self.data_root)
        core = DeterministicBrainCore(
            repo,
            collector,
            software_commit=os.getenv("V22_SOFTWARE_COMMIT") or os.getenv("GITHUB_SHA") or "lambda-local",
        )
        result = core.run(
            invocation.cycle_type,
            invocation.scheduled_at,
            workflow_id=invocation.workflow_id,
        )
        return {
            "ok": result.status in {"COMPLETED", "PARTIAL"},
            "adapter_version": "stage7-v1",
            "brain_version": __version__,
            "cycle": asdict(result),
        }


_RUNTIME: LambdaRuntime | None = None


def reset_runtime_cache() -> None:
    """Test/deployment hook: force the next invocation to rebuild config."""
    global _RUNTIME
    _RUNTIME = None


def runtime_from_environment() -> LambdaRuntime:
    database_url = os.getenv("DATABASE_URL", "sqlite:///data/v22_local.db").strip()
    if not database_url:
        raise InvocationRejected("DATABASE_URL must not be empty")

    # Local SQLite remains useful for development/tests, but a deployed Lambda must
    # not silently write durable Brain state into its disposable filesystem.
    in_aws = bool(os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
    if in_aws and not database_url.startswith(("postgres://", "postgresql://")):
        if os.getenv("V22_ALLOW_EPHEMERAL_SQLITE", "0") != "1":
            raise InvocationRejected("AWS Lambda requires a Postgres/Neon DATABASE_URL")

    data_root = Path(os.getenv("V22_DATA_ROOT", ".")).resolve()
    try:
        minimum_remaining_ms = int(os.getenv("V22_LAMBDA_MIN_REMAINING_MS", "10000"))
    except ValueError as exc:
        raise InvocationRejected("V22_LAMBDA_MIN_REMAINING_MS must be an integer") from exc
    if minimum_remaining_ms < 1000:
        raise InvocationRejected("V22_LAMBDA_MIN_REMAINING_MS must be at least 1000")

    collector_default = "live" if in_aws else "snapshot"
    collector_mode = os.getenv("V22_COLLECTOR_MODE", collector_default).strip().lower()
    collector_map = {"snapshot": LegacySnapshotCollector, "live": LiveEvidenceCollector}
    if collector_mode not in collector_map:
        raise InvocationRejected("V22_COLLECTOR_MODE must be snapshot or live")

    return LambdaRuntime(
        database_url=database_url,
        data_root=data_root,
        minimum_remaining_ms=minimum_remaining_ms,
        auto_migrate=os.getenv("V22_AUTO_MIGRATE", "0") == "1",
        collector_factory=collector_map[collector_mode],
    )


def get_runtime() -> LambdaRuntime:
    global _RUNTIME
    if _RUNTIME is None:
        _RUNTIME = runtime_from_environment()
    return _RUNTIME


def parse_invocation(event: Mapping[str, Any] | None, *, context: LambdaContext | None = None) -> LambdaInvocation:
    if not isinstance(event, Mapping):
        raise InvocationRejected("event must be a JSON object")

    # Permit direct invocation and common message wrappers without allowing runtime
    # configuration/secrets to arrive in the event itself.
    payload: Mapping[str, Any] = event
    if isinstance(event.get("detail"), Mapping):
        payload = event["detail"]
    elif isinstance(event.get("body"), str):
        try:
            decoded = json.loads(event["body"])
        except Exception as exc:
            raise InvocationRejected("event body must contain valid JSON") from exc
        if not isinstance(decoded, Mapping):
            raise InvocationRejected("event body JSON must be an object")
        payload = decoded

    raw_cycle = str(payload.get("cycle") or payload.get("cycle_type") or "").strip().lower()
    cycle_map = {
        "5m": CycleType.MICRO_5M,
        "micro_5m": CycleType.MICRO_5M,
        "micro-5m": CycleType.MICRO_5M,
        "15m": CycleType.MARKET_15M,
        "market_15m": CycleType.MARKET_15M,
        "market-15m": CycleType.MARKET_15M,
    }
    if raw_cycle not in cycle_map:
        raise InvocationRejected("cycle must be 5m or 15m")

    raw_scheduled = payload.get("scheduled_at")
    if not raw_scheduled:
        # Never default to now: retrying the same orchestration message must map to
        # the same canonical cycle slot.
        raise InvocationRejected("scheduled_at is required for retry-safe execution")
    try:
        scheduled_at = datetime.fromisoformat(str(raw_scheduled).replace("Z", "+00:00"))
    except Exception as exc:
        raise InvocationRejected("scheduled_at must be valid ISO-8601") from exc
    if scheduled_at.tzinfo is None:
        raise InvocationRejected("scheduled_at must include a timezone")
    scheduled_at = scheduled_at.astimezone(timezone.utc)

    workflow_id = payload.get("workflow_id")
    if workflow_id is not None:
        workflow_id = str(workflow_id).strip() or None
    if workflow_id is None and context is not None:
        workflow_id = getattr(context, "aws_request_id", None)

    forbidden = {"database_url", "DATABASE_URL", "data_root", "V22_DATA_ROOT"}
    supplied_forbidden = sorted(k for k in forbidden if k in payload)
    if supplied_forbidden:
        raise InvocationRejected(
            "runtime configuration must come from environment, not invocation payload: "
            + ", ".join(supplied_forbidden)
        )

    return LambdaInvocation(cycle_type=cycle_map[raw_cycle], scheduled_at=scheduled_at, workflow_id=workflow_id)


def _require_time_budget(context: LambdaContext | None, minimum_remaining_ms: int) -> None:
    if context is None or not hasattr(context, "get_remaining_time_in_millis"):
        return
    remaining = int(context.get_remaining_time_in_millis())
    if remaining < minimum_remaining_ms:
        raise TimeoutError(
            f"refusing to start Brain cycle with only {remaining}ms remaining; "
            f"minimum is {minimum_remaining_ms}ms"
        )


def lambda_handler(event: Mapping[str, Any] | None, context: LambdaContext | None) -> dict[str, Any]:
    """AWS Lambda entry point.

    Intentionally thin: validate the durable invocation contract, obtain runtime
    configuration from environment, then call the existing deterministic Brain.
    Exceptions are allowed to escape so an external durable orchestrator sees a
    failed invocation and can apply its retry policy.
    """
    invocation = parse_invocation(event, context=context)
    runtime = get_runtime()
    return runtime.execute(invocation, context=context)
