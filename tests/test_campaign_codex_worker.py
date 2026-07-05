import os
import shutil
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from aider.providers.base import BaseProvider, ProviderEvent
from aider.relay.campaign import QueueRecord, QueueState
from aider.relay.campaign_manifest import campaign_manifest_from_dict
from aider.relay.campaign_runner import run_autonomous_campaign
from aider.relay.codex_worker import CodexCliCampaignWorker, campaign_prompt_for_codex


class FakeProvider(BaseProvider):
    def __init__(self, events: list[ProviderEvent]):
        self.events = events
        self.prompts_received: list[str] = []

    async def run_turn(self, prompt: str) -> AsyncIterator[ProviderEvent]:
        self.prompts_received.append(prompt)
        for event in self.events:
            yield event

    @property
    def current_session_id(self) -> str | None:
        return "fake-session"


def test_codex_campaign_worker_maps_done_to_completed():
    provider = FakeProvider(
        [
            ProviderEvent(type="text", content="done"),
            ProviderEvent(type="done"),
        ]
    )
    worker = CodexCliCampaignWorker(provider_factory=lambda: provider)
    queue = QueueRecord(id="queue-a", title="Queue A", prompt="Say done")

    result = worker.run_queue(queue, campaign_manifest_from_dict({"queues": []}).to_state())

    assert result.outcome == "completed"
    assert result.provider == "codex"
    assert "done" in result.summary
    assert [event.type for event in result.events] == [
        "provider.started",
        "provider.text",
        "provider.completed",
    ]
    assert "bounded worker" in provider.prompts_received[0]


def test_codex_campaign_worker_maps_exhaustion_to_external_block():
    worker = CodexCliCampaignWorker(
        provider_factory=lambda: FakeProvider(
            [ProviderEvent(type="exhausted", reset_at="2026-07-06T00:00:00Z")]
        )
    )
    queue = QueueRecord(id="queue-a", prompt="Do work")

    result = worker.run_queue(queue, campaign_manifest_from_dict({"queues": []}).to_state())

    assert result.outcome == "blocked_external"
    assert "exhausted" in result.summary
    assert result.reset_at == "2026-07-06T00:00:00Z"
    assert result.events[-1].data["reset_at"] == "2026-07-06T00:00:00Z"


def test_codex_worker_integrates_with_autonomous_campaign_loop():
    worker = CodexCliCampaignWorker(
        provider_factory=lambda: FakeProvider(
            [
                ProviderEvent(type="text", content="ok"),
                ProviderEvent(type="done"),
            ]
        )
    )
    state = campaign_manifest_from_dict(
        {"queues": [{"id": "queue-a", "prompt": "Do A"}]}
    ).to_state()

    result = run_autonomous_campaign(state=state, worker=worker)

    assert result.queues[0].state == QueueState.COMPLETED
    assert result.stopped


def test_campaign_prompt_for_codex_keeps_orchestrator_in_control():
    prompt = campaign_prompt_for_codex(QueueRecord(id="queue-a", prompt="Do A"))

    assert "bounded worker" in prompt
    assert "orchestrator decides what runs next" in prompt
    assert "Do A" in prompt


@pytest.mark.skipif(
    os.environ.get("AIDER_RELAY_RUN_CODEX_CLI") != "1",
    reason="set AIDER_RELAY_RUN_CODEX_CLI=1 to run the real Codex CLI smoke test",
)
@pytest.mark.skipif(shutil.which("codex") is None, reason="codex CLI is not installed")
def test_real_codex_cli_campaign_dry_run(tmp_path):
    state_path = tmp_path / "campaign.json"
    state = campaign_manifest_from_dict(
        {
            "queues": [
                {
                    "id": "codex-smoke",
                    "title": "Codex CLI smoke",
                    "prompt": (
                        "Dry-run only. Do not edit files. Reply with exactly "
                        "AIDER_RELAY_CODEX_CAMPAIGN_OK."
                    ),
                }
            ]
        }
    ).to_state()

    result = run_autonomous_campaign(
        state=state,
        state_path=state_path,
        worker=CodexCliCampaignWorker(cwd=Path.cwd(), sandbox="read-only", turn_timeout=120),
    )

    assert result.queues[0].state == QueueState.COMPLETED
    assert state_path.exists()
