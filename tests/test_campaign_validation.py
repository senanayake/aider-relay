import sys

from aider.relay.campaign import QueueRecord
from aider.relay.validation import run_validation_commands, validation_passed


def test_validation_command_records_pass(tmp_path):
    queue = QueueRecord(
        id="queue-a",
        validation_commands=[f"{sys.executable} -c \"print('ok')\""],
    )

    receipts = run_validation_commands(queue, cwd=tmp_path)

    assert validation_passed(receipts)
    assert receipts[0].queue_id == "queue-a"
    assert receipts[0].passed is True
    assert receipts[0].exit_code == 0
    assert "ok" in receipts[0].stdout
    assert receipts[0].command


def test_validation_command_emits_events(tmp_path):
    events = []
    queue = QueueRecord(
        id="queue-a",
        validation_commands=[f"{sys.executable} -c \"print('ok')\""],
    )

    run_validation_commands(queue, cwd=tmp_path, event_sink=events.append)

    assert [event.type for event in events] == [
        "validation.command.started",
        "validation.command.passed",
    ]
    assert events[0].queue_id == "queue-a"


def test_validation_command_records_failure(tmp_path):
    queue = QueueRecord(
        id="queue-a",
        validation_commands=[f'{sys.executable} -c "import sys; sys.exit(7)"'],
    )

    receipts = run_validation_commands(queue, cwd=tmp_path)

    assert not validation_passed(receipts)
    assert receipts[0].passed is False
    assert receipts[0].exit_code == 7
    assert receipts[0].summary == "validation failed"


def test_validation_command_records_timeout(tmp_path):
    queue = QueueRecord(
        id="queue-a",
        validation_commands=[f'{sys.executable} -c "import time; time.sleep(2)"'],
    )

    receipts = run_validation_commands(queue, cwd=tmp_path, timeout=1)

    assert not validation_passed(receipts)
    assert receipts[0].passed is False
    assert receipts[0].exit_code is None
    assert receipts[0].summary == "validation timed out"
