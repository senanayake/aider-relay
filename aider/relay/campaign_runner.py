"""
Top-level deterministic campaign runner.

This runner owns the campaign loop. Workers are bounded executors that return
normalized outcomes. This module intentionally does not invoke real provider
CLIs; real providers can be adapted later behind the Worker protocol.
"""

import json
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from aider.relay.campaign import (
    CampaignEvent,
    CampaignState,
    DryRunWorkerResult,
    QueueRecord,
    QueueState,
    StopAudit,
    UsageSnapshot,
    _utc_now,
    run_dry_worker_turn,
    schedule_next_queue,
)
from aider.relay.campaign_manifest import load_campaign_manifest
from aider.relay.validation import run_validation_commands, validation_passed


@dataclass
class WorkerResult:
    outcome: DryRunWorkerResult
    summary: str = ""
    provider: str = "dry-run"
    events: list[CampaignEvent] | None = None
    reset_at: str | None = None


class CampaignWorker(Protocol):
    def run_queue(self, queue: QueueRecord, state: CampaignState) -> WorkerResult:
        raise NotImplementedError


class ScriptedCampaignWorker:
    """Deterministic worker for tests and dry runs."""

    def __init__(
        self,
        outcomes: (
            dict[str, DryRunWorkerResult | str] | list[DryRunWorkerResult | str] | None
        ) = None,
        *,
        default: DryRunWorkerResult | str = DryRunWorkerResult.COMPLETED,
        provider: str = "scripted",
    ):
        self.outcomes = outcomes or {}
        self.default = DryRunWorkerResult(default)
        self.provider = provider
        self.prompts_received: list[str] = []

    def run_queue(self, queue: QueueRecord, state: CampaignState) -> WorkerResult:
        self.prompts_received.append(queue.prompt)
        if isinstance(self.outcomes, list):
            raw_outcome = self.outcomes.pop(0) if self.outcomes else self.default
        else:
            raw_outcome = self.outcomes.get(queue.id, self.default)
        outcome = DryRunWorkerResult(raw_outcome)
        return WorkerResult(
            outcome=outcome,
            summary=f"{self.provider} returned {outcome.value}",
            provider=self.provider,
        )


def run_autonomous_campaign(
    *,
    state: CampaignState | None = None,
    manifest_path: str | Path | None = None,
    state_path: str | Path | None = None,
    worker: CampaignWorker | None = None,
    max_queues: int = 0,
    validation_cwd: str | Path | None = None,
    validation_timeout: int = 120,
    event_sink=None,
    event_log_path: str | Path | None = None,
    interrupt_path: str | Path | None = None,
    pause_path: str | Path | None = None,
    pause_poll_interval: float = 5.0,
    max_runtime_seconds: int = 0,
    heartbeat_interval: int = 0,
    require_clean_worktree: bool = False,
    checkpoint_command: str = "",
) -> CampaignState:
    """Run a deterministic campaign loop until stop audit or max_queues.

    At least one of ``state``, ``manifest_path``, or existing ``state_path`` must
    be supplied. ``state_path`` is persisted after every control-plane decision.
    """

    state = _initial_state(state=state, manifest_path=manifest_path, state_path=state_path)
    if require_clean_worktree:
        _require_clean_worktree(validation_cwd)
    if state.stop_audit and state.stop_audit.reason.startswith("max queue limit reached:"):
        state.stop_audit = None
    worker = worker or ScriptedCampaignWorker()
    queues_run = 0
    started_monotonic = time.monotonic()
    last_heartbeat = started_monotonic

    while not state.stopped:
        if _stop_requested(state, event_sink, state_path, event_log_path, interrupt_path):
            break
        _wait_while_paused(
            state,
            event_sink,
            state_path,
            event_log_path,
            pause_path,
            pause_poll_interval,
            interrupt_path,
        )
        if _stop_requested(state, event_sink, state_path, event_log_path, interrupt_path):
            break
        if _runtime_exceeded(started_monotonic, max_runtime_seconds):
            _stop_campaign(
                state,
                event_sink,
                state_path,
                event_log_path,
                f"max runtime reached: {max_runtime_seconds}s",
                "campaign.stopped",
            )
            break
        last_heartbeat = _heartbeat_if_due(
            state,
            event_sink,
            state_path,
            event_log_path,
            last_heartbeat,
            heartbeat_interval,
        )

        schedule_next_queue(state)
        _touch(state)
        _persist(state, state_path)

        if state.stopped:
            _emit(
                state,
                event_sink,
                "campaign.stopped",
                state.stop_audit.reason if state.stop_audit else "campaign stopped",
                event_log_path=event_log_path,
            )
            _touch(state)
            _persist(state, state_path)
            break
        active = state.active_queue()
        if active is None:
            break
        if max_queues and queues_run >= max_queues:
            state.stop_audit = StopAudit(
                stopped=True,
                reason=f"max queue limit reached: {max_queues}",
                candidate_queue_ids=[
                    queue.id for queue in state.queues if queue.id != state.active_queue_id
                ],
                conservative_mode=state.usage_snapshot.conservative_mode,
            )
            state.active_queue_id = None
            active.state = QueueState.CANDIDATE
            _emit(
                state,
                event_sink,
                "campaign.stopped",
                state.stop_audit.reason,
                data={"max_queues": max_queues},
                event_log_path=event_log_path,
            )
            _touch(state)
            _persist(state, state_path)
            break

        _emit(
            state,
            event_sink,
            "queue.started",
            f"started queue {active.id}",
            queue_id=active.id,
            event_log_path=event_log_path,
        )
        worker_result = worker.run_queue(active, state)
        for event in worker_result.events or []:
            state.events.append(event)
            _append_event_log(event_log_path, event)
            if event_sink:
                event_sink(event)
        outcome = worker_result.outcome
        summary = worker_result.summary

        if outcome == DryRunWorkerResult.COMPLETED and active.validation_commands:
            _emit(
                state,
                event_sink,
                "validation.started",
                f"running {len(active.validation_commands)} validation command(s)",
                queue_id=active.id,
                event_log_path=event_log_path,
            )
            receipts = run_validation_commands(
                active,
                cwd=validation_cwd,
                timeout=validation_timeout,
                event_sink=lambda event: _emit_existing(state, event_sink, event, event_log_path),
            )
            state.validation_receipts.extend(receipts)
            if not validation_passed(receipts):
                outcome = DryRunWorkerResult.FAILED_VALIDATION
                summary = "validation failed"
                _emit(
                    state,
                    event_sink,
                    "validation.failed",
                    f"validation failed for queue {active.id}",
                    queue_id=active.id,
                    event_log_path=event_log_path,
                )
            else:
                _emit(
                    state,
                    event_sink,
                    "validation.passed",
                    f"validation passed for queue {active.id}",
                    queue_id=active.id,
                    event_log_path=event_log_path,
                )

        if worker_result.reset_at or (
            worker_result.provider and "exhausted" in worker_result.summary.lower()
        ):
            state.usage_snapshot = UsageSnapshot.exhausted_provider(
                provider=worker_result.provider,
                reset_at=worker_result.reset_at,
                summary=worker_result.summary,
            )

        run_dry_worker_turn(
            state,
            outcome,
            summary,
            record_validation_receipt=not active.validation_commands,
            provider=worker_result.provider,
            reset_at=worker_result.reset_at,
        )
        _emit(
            state,
            event_sink,
            f"queue.{outcome.value}",
            f"queue {active.id} -> {outcome.value}",
            queue_id=active.id,
            provider=worker_result.provider,
            event_log_path=event_log_path,
        )
        if checkpoint_command:
            _run_checkpoint_command(
                state,
                active,
                checkpoint_command,
                validation_cwd,
                event_sink,
                event_log_path,
            )
        queues_run += 1
        if state.stopped:
            _emit(
                state,
                event_sink,
                "campaign.stopped",
                state.stop_audit.reason if state.stop_audit else "campaign stopped",
                event_log_path=event_log_path,
            )
        _touch(state)
        _persist(state, state_path)

    return state


def _initial_state(
    *,
    state: CampaignState | None,
    manifest_path: str | Path | None,
    state_path: str | Path | None,
) -> CampaignState:
    if state is not None:
        return state
    if state_path and Path(state_path).exists():
        return CampaignState.read(state_path)
    if manifest_path:
        return load_campaign_manifest(manifest_path).to_state()
    raise ValueError("state, manifest_path, or existing state_path is required")


def _persist(state: CampaignState, state_path: str | Path | None) -> None:
    if state_path:
        state.write(state_path)


def _touch(state: CampaignState) -> None:
    state.updated_at = _utc_now()


def _emit(
    state: CampaignState,
    event_sink,
    event_type: str,
    message: str,
    *,
    queue_id: str = "",
    provider: str = "",
    data: dict | None = None,
    event_log_path: str | Path | None = None,
) -> CampaignEvent:
    event = state.add_event(
        event_type,
        message,
        queue_id=queue_id,
        provider=provider,
        data=data,
    )
    _append_event_log(event_log_path, event)
    if event_sink:
        event_sink(event)
    return event


def _emit_existing(
    state: CampaignState,
    event_sink,
    event: CampaignEvent,
    event_log_path: str | Path | None = None,
) -> None:
    state.events.append(event)
    _append_event_log(event_log_path, event)
    if event_sink:
        event_sink(event)


def _append_event_log(event_log_path: str | Path | None, event: CampaignEvent) -> None:
    if not event_log_path:
        return
    path = Path(event_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(event.to_dict(), sort_keys=False) + "\n")


def _stop_requested(
    state: CampaignState,
    event_sink,
    state_path: str | Path | None,
    event_log_path: str | Path | None,
    interrupt_path: str | Path | None,
) -> bool:
    if not interrupt_path or not Path(interrupt_path).exists():
        return False
    _stop_campaign(
        state,
        event_sink,
        state_path,
        event_log_path,
        f"interrupt requested: {interrupt_path}",
        "campaign.interrupted",
    )
    return True


def _wait_while_paused(
    state: CampaignState,
    event_sink,
    state_path: str | Path | None,
    event_log_path: str | Path | None,
    pause_path: str | Path | None,
    pause_poll_interval: float,
    interrupt_path: str | Path | None,
) -> None:
    if not pause_path or not Path(pause_path).exists():
        return
    _emit(
        state,
        event_sink,
        "campaign.paused",
        f"pause requested: {pause_path}",
        event_log_path=event_log_path,
    )
    _touch(state)
    _persist(state, state_path)
    while Path(pause_path).exists():
        if _stop_requested(state, event_sink, state_path, event_log_path, interrupt_path):
            return
        time.sleep(pause_poll_interval)
    _emit(
        state,
        event_sink,
        "campaign.resumed",
        f"pause cleared: {pause_path}",
        event_log_path=event_log_path,
    )
    _touch(state)
    _persist(state, state_path)


def _runtime_exceeded(started_monotonic: float, max_runtime_seconds: int) -> bool:
    return bool(max_runtime_seconds and time.monotonic() - started_monotonic >= max_runtime_seconds)


def _heartbeat_if_due(
    state: CampaignState,
    event_sink,
    state_path: str | Path | None,
    event_log_path: str | Path | None,
    last_heartbeat: float,
    heartbeat_interval: int,
) -> float:
    now = time.monotonic()
    if not heartbeat_interval or now - last_heartbeat < heartbeat_interval:
        return last_heartbeat
    _emit(
        state,
        event_sink,
        "campaign.heartbeat",
        "campaign heartbeat",
        data={"active_queue_id": state.active_queue_id},
        event_log_path=event_log_path,
    )
    _touch(state)
    _persist(state, state_path)
    return now


def _stop_campaign(
    state: CampaignState,
    event_sink,
    state_path: str | Path | None,
    event_log_path: str | Path | None,
    reason: str,
    event_type: str,
) -> None:
    state.stop_audit = StopAudit(
        stopped=True,
        reason=reason,
        conservative_mode=state.usage_snapshot.conservative_mode,
    )
    state.active_queue_id = None
    _emit(state, event_sink, event_type, reason, event_log_path=event_log_path)
    _touch(state)
    _persist(state, state_path)


def _require_clean_worktree(cwd: str | Path | None) -> None:
    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "unable to inspect git worktree")
    if completed.stdout.strip():
        raise RuntimeError("git worktree is not clean")


def _run_checkpoint_command(
    state: CampaignState,
    queue: QueueRecord,
    checkpoint_command: str,
    cwd: str | Path | None,
    event_sink,
    event_log_path: str | Path | None,
) -> None:
    command = checkpoint_command.format(queue_id=queue.id)
    _emit(
        state,
        event_sink,
        "checkpoint.started",
        f"started checkpoint command: {command}",
        queue_id=queue.id,
        event_log_path=event_log_path,
    )
    completed = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        shell=True,
        text=True,
        capture_output=True,
        check=False,
    )
    _emit(
        state,
        event_sink,
        "checkpoint.completed" if completed.returncode == 0 else "checkpoint.failed",
        f"checkpoint command exited {completed.returncode}: {command}",
        queue_id=queue.id,
        data={"exit_code": completed.returncode},
        event_log_path=event_log_path,
    )


def parse_duration_seconds(value: str | int | None) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, int):
        return value
    text = str(value).strip().lower()
    if text.isdigit():
        return int(text)
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    suffix = text[-1]
    if suffix not in multipliers:
        raise ValueError(f"invalid duration: {value}")
    return int(float(text[:-1]) * multipliers[suffix])


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
