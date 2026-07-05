"""
Deterministic campaign state for relay dry runs.

This module models the owned orchestrator's queue scheduler. It does not call
provider CLIs, scrape usage analytics, or depend on worker prompt compliance.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

CAMPAIGN_SCHEMA_VERSION = "1.0"


class QueueState(str, Enum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    COMPLETED = "completed"
    DEFERRED_DECISION = "deferred_decision"
    BLOCKED_EXTERNAL = "blocked_external"
    FAILED_VALIDATION = "failed_validation"
    ABANDONED_LOW_VALUE = "abandoned_low_value"


class DryRunWorkerResult(str, Enum):
    COMPLETED = "completed"
    BLOCKED_DECISION = "blocked_decision"
    BLOCKED_EXTERNAL = "blocked_external"
    FAILED_VALIDATION = "failed_validation"
    LOW_VALUE = "low_value"


TERMINAL_QUEUE_STATES = {
    QueueState.COMPLETED,
    QueueState.DEFERRED_DECISION,
    QueueState.BLOCKED_EXTERNAL,
    QueueState.FAILED_VALIDATION,
    QueueState.ABANDONED_LOW_VALUE,
}


@dataclass
class UsageSnapshot:
    known: bool = True
    conservative_mode: bool = False
    provider: str = ""
    summary: str = ""
    exhausted: bool = False
    reset_at: str | None = None

    @classmethod
    def unknown(cls, provider: str = "", summary: str = "usage unknown") -> "UsageSnapshot":
        return cls(
            known=False,
            conservative_mode=True,
            provider=provider,
            summary=summary,
        )

    @classmethod
    def exhausted_provider(
        cls, provider: str, reset_at: str | None = None, summary: str = "provider exhausted"
    ) -> "UsageSnapshot":
        return cls(
            known=True,
            conservative_mode=True,
            provider=provider,
            summary=summary,
            exhausted=True,
            reset_at=reset_at,
        )

    def to_dict(self) -> dict:
        return {
            "known": self.known,
            "conservative_mode": self.conservative_mode,
            "provider": self.provider,
            "summary": self.summary,
            "exhausted": self.exhausted,
            "reset_at": self.reset_at,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "UsageSnapshot":
        data = data or {}
        return cls(
            known=data.get("known", True),
            conservative_mode=data.get("conservative_mode", False),
            provider=data.get("provider", ""),
            summary=data.get("summary", ""),
            exhausted=data.get("exhausted", False),
            reset_at=data.get("reset_at"),
        )


@dataclass
class ValidationReceipt:
    queue_id: str
    passed: bool
    summary: str = ""
    command: str = ""
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    started_at: str = ""
    ended_at: str = ""

    def to_dict(self) -> dict:
        return {
            "queue_id": self.queue_id,
            "passed": self.passed,
            "summary": self.summary,
            "command": self.command,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ValidationReceipt":
        return cls(
            queue_id=data["queue_id"],
            passed=data["passed"],
            summary=data.get("summary", ""),
            command=data.get("command", ""),
            exit_code=data.get("exit_code"),
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
            started_at=data.get("started_at", ""),
            ended_at=data.get("ended_at", ""),
        )


@dataclass
class WorkerTurn:
    queue_id: str
    result: DryRunWorkerResult
    summary: str = ""
    provider: str = ""
    reset_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "queue_id": self.queue_id,
            "result": self.result.value,
            "summary": self.summary,
            "provider": self.provider,
            "reset_at": self.reset_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorkerTurn":
        return cls(
            queue_id=data["queue_id"],
            result=DryRunWorkerResult(data["result"]),
            summary=data.get("summary", ""),
            provider=data.get("provider", ""),
            reset_at=data.get("reset_at"),
        )


@dataclass
class CampaignEvent:
    type: str
    message: str
    at: str = field(default_factory=lambda: _utc_now())
    queue_id: str = ""
    provider: str = ""
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "message": self.message,
            "at": self.at,
            "queue_id": self.queue_id,
            "provider": self.provider,
            "data": dict(self.data),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CampaignEvent":
        return cls(
            type=data["type"],
            message=data.get("message", ""),
            at=data.get("at", ""),
            queue_id=data.get("queue_id", ""),
            provider=data.get("provider", ""),
            data=dict(data.get("data", {})),
        )


@dataclass
class StopAudit:
    stopped: bool
    reason: str
    completed_queue_ids: list[str] = field(default_factory=list)
    deferred_queue_ids: list[str] = field(default_factory=list)
    blocked_queue_ids: list[str] = field(default_factory=list)
    failed_queue_ids: list[str] = field(default_factory=list)
    low_value_queue_ids: list[str] = field(default_factory=list)
    explicit_stop_queue_ids: list[str] = field(default_factory=list)
    candidate_queue_ids: list[str] = field(default_factory=list)
    conservative_mode: bool = False

    def to_dict(self) -> dict:
        return {
            "stopped": self.stopped,
            "reason": self.reason,
            "completed_queue_ids": list(self.completed_queue_ids),
            "deferred_queue_ids": list(self.deferred_queue_ids),
            "blocked_queue_ids": list(self.blocked_queue_ids),
            "failed_queue_ids": list(self.failed_queue_ids),
            "low_value_queue_ids": list(self.low_value_queue_ids),
            "explicit_stop_queue_ids": list(self.explicit_stop_queue_ids),
            "candidate_queue_ids": list(self.candidate_queue_ids),
            "conservative_mode": self.conservative_mode,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "StopAudit | None":
        if not data:
            return None
        return cls(
            stopped=data.get("stopped", False),
            reason=data.get("reason", ""),
            completed_queue_ids=list(data.get("completed_queue_ids", [])),
            deferred_queue_ids=list(data.get("deferred_queue_ids", [])),
            blocked_queue_ids=list(data.get("blocked_queue_ids", [])),
            failed_queue_ids=list(data.get("failed_queue_ids", [])),
            low_value_queue_ids=list(data.get("low_value_queue_ids", [])),
            explicit_stop_queue_ids=list(data.get("explicit_stop_queue_ids", [])),
            candidate_queue_ids=list(data.get("candidate_queue_ids", [])),
            conservative_mode=data.get("conservative_mode", False),
        )


@dataclass
class QueueRecord:
    id: str
    title: str = ""
    prompt: str = ""
    depends_on: list[str] = field(default_factory=list)
    validation_commands: list[str] = field(default_factory=list)
    state: QueueState = QueueState.CANDIDATE
    decision_dependent: bool = False
    useful: bool = True
    explicit_stop: bool = False
    last_result: DryRunWorkerResult | None = None
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "prompt": self.prompt,
            "depends_on": list(self.depends_on),
            "validation_commands": list(self.validation_commands),
            "state": self.state.value,
            "decision_dependent": self.decision_dependent,
            "useful": self.useful,
            "explicit_stop": self.explicit_stop,
            "last_result": self.last_result.value if self.last_result else None,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "QueueRecord":
        last_result = data.get("last_result")
        return cls(
            id=data["id"],
            title=data.get("title", ""),
            prompt=data.get("prompt", ""),
            depends_on=list(data.get("depends_on", [])),
            validation_commands=list(data.get("validation_commands", [])),
            state=QueueState(data.get("state", QueueState.CANDIDATE.value)),
            decision_dependent=data.get("decision_dependent", False),
            useful=data.get("useful", True),
            explicit_stop=data.get("explicit_stop", False),
            last_result=DryRunWorkerResult(last_result) if last_result else None,
            reason=data.get("reason", ""),
        )


@dataclass
class CampaignState:
    queues: list[QueueRecord]
    schema_version: str = CAMPAIGN_SCHEMA_VERSION
    campaign_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: _utc_now())
    updated_at: str = field(default_factory=lambda: _utc_now())
    active_queue_id: str | None = None
    worker_turns: list[WorkerTurn] = field(default_factory=list)
    validation_receipts: list[ValidationReceipt] = field(default_factory=list)
    events: list[CampaignEvent] = field(default_factory=list)
    usage_snapshot: UsageSnapshot = field(default_factory=UsageSnapshot)
    stop_audit: StopAudit | None = None

    @property
    def stopped(self) -> bool:
        return bool(self.stop_audit and self.stop_audit.stopped)

    def active_queue(self) -> QueueRecord | None:
        if self.active_queue_id is None:
            return None
        return _find_queue(self.queues, self.active_queue_id)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "campaign_id": self.campaign_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "active_queue_id": self.active_queue_id,
            "queues": [queue.to_dict() for queue in self.queues],
            "worker_turns": [turn.to_dict() for turn in self.worker_turns],
            "validation_receipts": [receipt.to_dict() for receipt in self.validation_receipts],
            "events": [event.to_dict() for event in self.events],
            "usage_snapshot": self.usage_snapshot.to_dict(),
            "stop_audit": self.stop_audit.to_dict() if self.stop_audit else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CampaignState":
        return cls(
            schema_version=data.get("schema_version", CAMPAIGN_SCHEMA_VERSION),
            campaign_id=data.get("campaign_id", str(uuid.uuid4())),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            active_queue_id=data.get("active_queue_id"),
            queues=[QueueRecord.from_dict(item) for item in data.get("queues", [])],
            worker_turns=[WorkerTurn.from_dict(item) for item in data.get("worker_turns", [])],
            validation_receipts=[
                ValidationReceipt.from_dict(item) for item in data.get("validation_receipts", [])
            ],
            events=[CampaignEvent.from_dict(item) for item in data.get("events", [])],
            usage_snapshot=UsageSnapshot.from_dict(data.get("usage_snapshot")),
            stop_audit=StopAudit.from_dict(data.get("stop_audit")),
        )

    def add_event(
        self,
        event_type: str,
        message: str,
        *,
        queue_id: str = "",
        provider: str = "",
        data: dict | None = None,
    ) -> CampaignEvent:
        event = CampaignEvent(
            type=event_type,
            message=message,
            queue_id=queue_id,
            provider=provider,
            data=data or {},
        )
        self.events.append(event)
        return event

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False)

    def write(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json())

    @classmethod
    def read(cls, path: str | Path) -> "CampaignState":
        return cls.from_dict(json.loads(Path(path).read_text()))


def run_dry_worker_turn(
    state: CampaignState,
    result: DryRunWorkerResult | str | None = None,
    summary: str = "",
    record_validation_receipt: bool = True,
    provider: str = "",
    reset_at: str | None = None,
) -> CampaignState:
    """Apply one dry-run worker result and schedule the next queue.

    If ``result`` is None, the function only schedules the next candidate. This
    is useful for starting a campaign from all-candidate state.
    """

    if state.stopped:
        return state

    if result is None:
        return schedule_next_queue(state)

    active = state.active_queue()
    if active is None:
        raise ValueError("cannot apply worker result without an active queue")

    result = DryRunWorkerResult(result)
    active.last_result = result
    active.reason = summary
    state.worker_turns.append(
        WorkerTurn(
            queue_id=active.id,
            result=result,
            summary=summary,
            provider=provider,
            reset_at=reset_at,
        )
    )

    if result == DryRunWorkerResult.COMPLETED:
        active.state = QueueState.COMPLETED
        if record_validation_receipt:
            state.validation_receipts.append(
                ValidationReceipt(queue_id=active.id, passed=True, summary=summary)
            )
    elif result == DryRunWorkerResult.BLOCKED_DECISION:
        active.state = QueueState.DEFERRED_DECISION
    elif result == DryRunWorkerResult.BLOCKED_EXTERNAL:
        active.state = QueueState.BLOCKED_EXTERNAL
    elif result == DryRunWorkerResult.FAILED_VALIDATION:
        active.state = QueueState.FAILED_VALIDATION
        if record_validation_receipt:
            state.validation_receipts.append(
                ValidationReceipt(queue_id=active.id, passed=False, summary=summary)
            )
    elif result == DryRunWorkerResult.LOW_VALUE:
        active.state = QueueState.ABANDONED_LOW_VALUE

    state.active_queue_id = None
    return schedule_next_queue(state)


def schedule_next_queue(state: CampaignState) -> CampaignState:
    """Promote the next deterministic candidate or record a stop audit."""

    if state.stopped:
        return state

    active = state.active_queue()
    if active is not None and active.state == QueueState.ACTIVE:
        return state

    state.active_queue_id = None
    for queue in state.queues:
        if queue.state != QueueState.CANDIDATE:
            continue
        if queue.explicit_stop:
            continue
        if not queue.useful:
            queue.state = QueueState.ABANDONED_LOW_VALUE
            queue.reason = queue.reason or "not useful enough to schedule"
            continue
        if not _dependencies_completed(state, queue):
            continue
        if queue.decision_dependent:
            queue.state = QueueState.DEFERRED_DECISION
            queue.reason = queue.reason or "requires an external decision"
            continue

        queue.state = QueueState.ACTIVE
        state.active_queue_id = queue.id
        state.stop_audit = None
        return state

    state.stop_audit = build_stop_audit(state)
    return state


def build_stop_audit(state: CampaignState) -> StopAudit:
    return StopAudit(
        stopped=True,
        reason=(
            "no decision-independent useful candidate queues remain; "
            "blocked queues were not treated as campaign-blocking while alternatives existed"
        ),
        completed_queue_ids=_ids_with_state(state, QueueState.COMPLETED),
        deferred_queue_ids=_ids_with_state(state, QueueState.DEFERRED_DECISION),
        blocked_queue_ids=_ids_with_state(state, QueueState.BLOCKED_EXTERNAL),
        failed_queue_ids=_ids_with_state(state, QueueState.FAILED_VALIDATION),
        low_value_queue_ids=_ids_with_state(state, QueueState.ABANDONED_LOW_VALUE),
        explicit_stop_queue_ids=[queue.id for queue in state.queues if queue.explicit_stop],
        candidate_queue_ids=_ids_with_state(state, QueueState.CANDIDATE),
        conservative_mode=state.usage_snapshot.conservative_mode,
    )


def _ids_with_state(state: CampaignState, queue_state: QueueState) -> list[str]:
    return [queue.id for queue in state.queues if queue.state == queue_state]


def _find_queue(queues: list[QueueRecord], queue_id: str) -> QueueRecord | None:
    for queue in queues:
        if queue.id == queue_id:
            return queue
    return None


def _dependencies_completed(state: CampaignState, queue: QueueRecord) -> bool:
    for dependency_id in queue.depends_on:
        dependency = _find_queue(state.queues, dependency_id)
        if dependency is None or dependency.state != QueueState.COMPLETED:
            return False
    return True


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()
