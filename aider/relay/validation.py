"""
Deterministic validation command execution for relay campaigns.
"""

import subprocess
from pathlib import Path

from aider.relay.campaign import CampaignEvent, QueueRecord, ValidationReceipt, _utc_now

_MAX_CAPTURE_CHARS = 4_000


def run_validation_commands(
    queue: QueueRecord,
    *,
    cwd: str | Path | None = None,
    timeout: int = 120,
    event_sink=None,
) -> list[ValidationReceipt]:
    receipts = []
    for command in queue.validation_commands:
        receipts.append(
            run_validation_command(
                queue_id=queue.id,
                command=command,
                cwd=cwd,
                timeout=timeout,
                event_sink=event_sink,
            )
        )
    return receipts


def run_validation_command(
    *,
    queue_id: str,
    command: str,
    cwd: str | Path | None = None,
    timeout: int = 120,
    event_sink=None,
) -> ValidationReceipt:
    started_at = _utc_now()
    _emit(
        event_sink,
        "validation.command.started",
        f"started validation command: {command}",
        queue_id=queue_id,
        data={"command": command},
    )
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            shell=True,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        ended_at = _utc_now()
        passed = completed.returncode == 0
        _emit(
            event_sink,
            "validation.command.passed" if passed else "validation.command.failed",
            f"validation command exited {completed.returncode}: {command}",
            queue_id=queue_id,
            data={"command": command, "exit_code": completed.returncode},
        )
        return ValidationReceipt(
            queue_id=queue_id,
            passed=passed,
            summary="validation passed" if passed else "validation failed",
            command=command,
            exit_code=completed.returncode,
            stdout=_tail(completed.stdout),
            stderr=_tail(completed.stderr),
            started_at=started_at,
            ended_at=ended_at,
        )
    except subprocess.TimeoutExpired as exc:
        _emit(
            event_sink,
            "validation.command.timeout",
            f"validation command timed out after {timeout}s: {command}",
            queue_id=queue_id,
            data={"command": command, "timeout": timeout},
        )
        return ValidationReceipt(
            queue_id=queue_id,
            passed=False,
            summary="validation timed out",
            command=command,
            exit_code=None,
            stdout=_tail(_coerce_output(exc.stdout)),
            stderr=_tail(_coerce_output(exc.stderr)),
            started_at=started_at,
            ended_at=_utc_now(),
        )


def validation_passed(receipts: list[ValidationReceipt]) -> bool:
    return all(receipt.passed for receipt in receipts)


def _tail(value: str) -> str:
    if len(value) <= _MAX_CAPTURE_CHARS:
        return value
    return value[-_MAX_CAPTURE_CHARS:]


def _coerce_output(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return str(value)


def _emit(event_sink, event_type: str, message: str, *, queue_id: str, data: dict) -> None:
    if event_sink:
        event_sink(
            CampaignEvent(
                type=event_type,
                message=message,
                queue_id=queue_id,
                data=data,
            )
        )
