import pytest

from aider.relay.campaign import QueueState, schedule_next_queue
from aider.relay.campaign_manifest import (
    campaign_manifest_from_dict,
    load_campaign_manifest,
)


def test_manifest_loads_queues_in_order(tmp_path):
    path = tmp_path / "campaign.yaml"
    path.write_text("""
campaign:
  title: Demo
queues:
  - id: queue-a
    title: Queue A
    prompt: Do A
    validation:
      - python3 -m pytest tests/test_campaign.py -q
  - id: queue-b
    depends_on: [queue-a]
    decision_dependent: true
""")

    manifest = load_campaign_manifest(path)
    state = manifest.to_state()

    assert manifest.title == "Demo"
    assert [queue.id for queue in state.queues] == ["queue-a", "queue-b"]
    assert state.queues[0].prompt == "Do A"
    assert state.queues[0].validation_commands == ["python3 -m pytest tests/test_campaign.py -q"]
    assert state.queues[1].depends_on == ["queue-a"]
    assert state.queues[1].decision_dependent is True


def test_manifest_rejects_duplicate_queue_ids():
    with pytest.raises(ValueError, match="duplicate"):
        campaign_manifest_from_dict(
            {
                "queues": [
                    {"id": "queue-a"},
                    {"id": "queue-a"},
                ]
            }
        )


def test_manifest_rejects_unknown_dependency():
    with pytest.raises(ValueError, match="unknown queue id"):
        campaign_manifest_from_dict(
            {
                "queues": [
                    {"id": "queue-a", "depends_on": ["missing"]},
                ]
            }
        )


def test_scheduler_skips_candidate_with_unmet_dependency():
    state = campaign_manifest_from_dict(
        {
            "queues": [
                {"id": "queue-a", "depends_on": ["queue-b"]},
                {"id": "queue-b"},
            ]
        }
    ).to_state()

    schedule_next_queue(state)

    assert state.active_queue_id == "queue-b"
    assert state.queues[0].state == QueueState.CANDIDATE
    assert state.queues[1].state == QueueState.ACTIVE
