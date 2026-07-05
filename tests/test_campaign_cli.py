from unittest.mock import patch

import pytest

from aider.providers.codex import CodexProvider
from aider.relay.campaign import CampaignState, QueueRecord, StopAudit
from aider.relay.loop import _watch_campaign_status, campaign_main


def test_campaign_cli_run_scripted_writes_state(tmp_path, capsys):
    manifest = tmp_path / "campaign.yaml"
    state_path = tmp_path / "campaign.json"
    event_log = tmp_path / "campaign.events.jsonl"
    manifest.write_text("""
queues:
  - id: queue-a
    prompt: Do A
""")

    campaign_main(
        [
            "run",
            "--manifest",
            str(manifest),
            "--state",
            str(state_path),
            "--worker",
            "scripted",
            "--event-log",
            str(event_log),
        ]
    )

    out = capsys.readouterr().out
    assert state_path.exists()
    assert event_log.exists()
    assert "[CAMPAIGN] stopped:" in out
    assert CampaignState.read(state_path).queues[0].state.value == "completed"


def test_campaign_cli_resume_scripted(tmp_path, capsys):
    state_path = tmp_path / "campaign.json"
    CampaignState(queues=[QueueRecord(id="queue-a")]).write(state_path)

    campaign_main(["resume", "--state", str(state_path), "--worker", "scripted"])

    out = capsys.readouterr().out
    assert "completed=1" in out
    assert CampaignState.read(state_path).queues[0].state.value == "completed"


def test_campaign_cli_status_prints_summary(tmp_path, capsys):
    state_path = tmp_path / "campaign.json"
    CampaignState(queues=[QueueRecord(id="queue-a")]).write(state_path)

    campaign_main(["status", "--state", str(state_path)])

    out = capsys.readouterr().out
    assert "[CAMPAIGN] id:" in out
    assert "candidate=1" in out


def test_campaign_cli_status_watch_prints_events(tmp_path, capsys):
    state_path = tmp_path / "campaign.json"
    state = CampaignState(queues=[QueueRecord(id="queue-a")])
    state.add_event("queue.started", "started queue", queue_id="queue-a")
    state.stop_audit = StopAudit(stopped=True, reason="done")
    state.write(state_path)

    _watch_campaign_status(state_path, interval=0)

    out = capsys.readouterr().out
    assert "queue.started" in out
    assert "started queue" in out


def test_campaign_cli_status_missing_state_exits(tmp_path):
    with pytest.raises(SystemExit):
        campaign_main(["status", "--state", str(tmp_path / "missing.json")])


def test_codex_provider_dangerous_bypass_command_omits_sandbox():
    provider = CodexProvider(
        cwd=".",
        dangerously_bypass_approvals_and_sandbox=True,
    )
    captured = {}

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        captured["cmd"] = cmd

        class FakeStdout:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

        class FakeStderr:
            async def read(self):
                return b""

        class FakeProc:
            stdout = FakeStdout()
            stderr = FakeStderr()

            async def wait(self):
                return 0

        return FakeProc()

    with patch("asyncio.create_subprocess_exec", fake_create_subprocess_exec):
        import asyncio

        async def drain():
            async for _event in provider.run_turn("prompt"):
                pass

        asyncio.run(drain())

    assert "--dangerously-bypass-approvals-and-sandbox" in captured["cmd"]
    assert "--sandbox" not in captured["cmd"]
