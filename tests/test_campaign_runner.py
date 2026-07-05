import subprocess
import sys

import pytest

from aider.relay.campaign import CampaignState, DryRunWorkerResult, QueueState
from aider.relay.campaign_manifest import campaign_manifest_from_dict
from aider.relay.campaign_runner import (
    ScriptedCampaignWorker,
    parse_duration_seconds,
    run_autonomous_campaign,
)


def test_autonomous_campaign_completes_all_queues_and_writes_state(tmp_path):
    state_path = tmp_path / ".aider-relay" / "campaign.json"
    state = campaign_manifest_from_dict(
        {
            "queues": [
                {"id": "queue-a", "prompt": "Do A"},
                {"id": "queue-b", "prompt": "Do B", "depends_on": ["queue-a"]},
            ]
        }
    ).to_state()
    worker = ScriptedCampaignWorker()

    result = run_autonomous_campaign(state=state, state_path=state_path, worker=worker)

    assert [queue.state for queue in result.queues] == [
        QueueState.COMPLETED,
        QueueState.COMPLETED,
    ]
    assert result.stopped
    assert state_path.exists()
    assert worker.prompts_received == ["Do A", "Do B"]


def test_autonomous_campaign_continues_after_blocked_external_queue():
    state = campaign_manifest_from_dict(
        {
            "queues": [
                {"id": "queue-a"},
                {"id": "queue-b"},
            ]
        }
    ).to_state()
    worker = ScriptedCampaignWorker({"queue-a": "blocked_external", "queue-b": "completed"})

    result = run_autonomous_campaign(state=state, worker=worker)

    assert result.queues[0].state == QueueState.BLOCKED_EXTERNAL
    assert result.queues[1].state == QueueState.COMPLETED
    assert result.stopped


def test_autonomous_campaign_defers_decision_queue_and_runs_independent_queue():
    state = campaign_manifest_from_dict(
        {
            "queues": [
                {"id": "queue-a", "decision_dependent": True},
                {"id": "queue-b"},
            ]
        }
    ).to_state()

    result = run_autonomous_campaign(state=state, worker=ScriptedCampaignWorker())

    assert result.queues[0].state == QueueState.DEFERRED_DECISION
    assert result.queues[1].state == QueueState.COMPLETED
    assert result.stopped


def test_autonomous_campaign_failed_validation_does_not_stop_independent_queue(tmp_path):
    state = campaign_manifest_from_dict(
        {
            "queues": [
                {
                    "id": "queue-a",
                    "validation": [f'{sys.executable} -c "import sys; sys.exit(3)"'],
                },
                {"id": "queue-b"},
            ]
        }
    ).to_state()

    result = run_autonomous_campaign(
        state=state,
        worker=ScriptedCampaignWorker(),
        validation_cwd=tmp_path,
    )

    assert result.queues[0].state == QueueState.FAILED_VALIDATION
    assert result.queues[1].state == QueueState.COMPLETED
    assert any(receipt.command for receipt in result.validation_receipts)
    assert result.stopped


def test_autonomous_campaign_resumes_from_state_path(tmp_path):
    state_path = tmp_path / "campaign.json"
    state = campaign_manifest_from_dict(
        {
            "queues": [
                {"id": "queue-a"},
                {"id": "queue-b"},
            ]
        }
    ).to_state()

    first = run_autonomous_campaign(
        state=state,
        state_path=state_path,
        worker=ScriptedCampaignWorker(),
        max_queues=1,
    )
    resumed = run_autonomous_campaign(
        state_path=state_path,
        worker=ScriptedCampaignWorker(),
    )

    assert first.stop_audit.reason == "max queue limit reached: 1"
    assert resumed.queues[0].state == QueueState.COMPLETED
    assert resumed.queues[1].state == QueueState.COMPLETED
    assert resumed.stopped


def test_scripted_worker_accepts_list_outcomes():
    state = campaign_manifest_from_dict(
        {
            "queues": [
                {"id": "queue-a"},
                {"id": "queue-b"},
            ]
        }
    ).to_state()
    worker = ScriptedCampaignWorker(
        [DryRunWorkerResult.BLOCKED_EXTERNAL, DryRunWorkerResult.COMPLETED]
    )

    result = run_autonomous_campaign(state=state, worker=worker)

    assert result.queues[0].state == QueueState.BLOCKED_EXTERNAL
    assert result.queues[1].state == QueueState.COMPLETED


def test_autonomous_campaign_emits_and_persists_events(tmp_path):
    state_path = tmp_path / "campaign.json"
    events = []
    state = campaign_manifest_from_dict(
        {"queues": [{"id": "queue-a", "prompt": "Do A"}]}
    ).to_state()

    result = run_autonomous_campaign(
        state=state,
        state_path=state_path,
        worker=ScriptedCampaignWorker(),
        event_sink=events.append,
    )
    loaded = CampaignState.read(state_path)

    assert any(event.type == "queue.started" for event in events)
    assert any(event.type == "queue.completed" for event in events)
    assert any(event.type == "campaign.stopped" for event in events)
    assert [event.to_dict() for event in loaded.events] == [
        event.to_dict() for event in result.events
    ]


def test_autonomous_campaign_writes_jsonl_event_log(tmp_path):
    event_log = tmp_path / "campaign.events.jsonl"
    state = campaign_manifest_from_dict({"queues": [{"id": "queue-a"}]}).to_state()

    run_autonomous_campaign(
        state=state,
        worker=ScriptedCampaignWorker(),
        event_log_path=event_log,
    )

    text = event_log.read_text()
    assert "queue.started" in text
    assert "campaign.stopped" in text


def test_autonomous_campaign_interrupt_file_stops_before_queue(tmp_path):
    interrupt = tmp_path / "interrupt"
    interrupt.touch()
    state = campaign_manifest_from_dict({"queues": [{"id": "queue-a"}]}).to_state()

    result = run_autonomous_campaign(
        state=state,
        worker=ScriptedCampaignWorker(),
        interrupt_path=interrupt,
    )

    assert result.stopped
    assert "interrupt requested" in result.stop_audit.reason
    assert result.queues[0].state == QueueState.CANDIDATE


def test_parse_duration_seconds():
    assert parse_duration_seconds("30s") == 30
    assert parse_duration_seconds("2m") == 120
    assert parse_duration_seconds("1h") == 3600
    assert parse_duration_seconds("1d") == 86400
    assert parse_duration_seconds("42") == 42
    assert parse_duration_seconds("0") == 0


def test_require_clean_worktree_rejects_dirty_repo(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "dirty.txt").write_text("dirty")
    state = campaign_manifest_from_dict({"queues": [{"id": "queue-a"}]}).to_state()

    with pytest.raises(RuntimeError, match="not clean"):
        run_autonomous_campaign(
            state=state,
            worker=ScriptedCampaignWorker(),
            validation_cwd=tmp_path,
            require_clean_worktree=True,
        )


def test_checkpoint_command_runs_after_queue(tmp_path):
    marker = tmp_path / "checkpoint.txt"
    state = campaign_manifest_from_dict({"queues": [{"id": "queue-a"}]}).to_state()

    run_autonomous_campaign(
        state=state,
        worker=ScriptedCampaignWorker(),
        validation_cwd=tmp_path,
        checkpoint_command=(
            f"{sys.executable} -c "
            f"\"from pathlib import Path; Path('{marker}').write_text('ok')\""
        ),
    )

    assert marker.read_text() == "ok"
    assert any(event.type == "checkpoint.completed" for event in state.events)
