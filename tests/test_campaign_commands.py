from unittest.mock import Mock

import pytest

pytest.importorskip("pyperclip")

from aider.commands import Commands  # noqa: E402


def _commands(root):
    io = Mock()
    coder = Mock()
    coder.root = str(root)
    return Commands(io=io, coder=coder), io


def test_campaign_command_requires_subcommand(tmp_path):
    commands, io = _commands(tmp_path)

    commands.cmd_campaign("")

    io.tool_error.assert_called_once()
    assert "Usage: /campaign" in io.tool_error.call_args[0][0]


def test_campaign_run_scripted_streams_events(tmp_path):
    manifest = tmp_path / "campaign.yaml"
    manifest.write_text("""
queues:
  - id: queue-a
    prompt: Do A
""")
    commands, io = _commands(tmp_path)

    commands.cmd_campaign(f"run {manifest.name} --worker scripted")

    outputs = "\n".join(call.args[0] for call in io.tool_output.call_args_list)
    assert "queue.started" in outputs
    assert "queue.completed" in outputs
    assert "completed=1" in outputs
    assert (tmp_path / ".aider-relay" / "campaign.json").exists()


def test_campaign_status_prints_summary_and_recent_events(tmp_path):
    manifest = tmp_path / "campaign.yaml"
    manifest.write_text("queues:\n  - id: queue-a\n")
    commands, io = _commands(tmp_path)
    commands.cmd_campaign(f"run {manifest.name} --worker scripted")
    io.tool_output.reset_mock()

    commands.cmd_campaign("status --events 2")

    outputs = "\n".join(call.args[0] for call in io.tool_output.call_args_list)
    assert "[CAMPAIGN] id:" in outputs
    assert "campaign.stopped" in outputs


def test_campaign_pause_unpause_stop_create_control_files(tmp_path):
    commands, io = _commands(tmp_path)

    commands.cmd_campaign("pause")
    assert (tmp_path / ".aider-relay" / "pause").exists()

    commands.cmd_campaign("unpause")
    assert not (tmp_path / ".aider-relay" / "pause").exists()

    commands.cmd_campaign("stop")
    assert (tmp_path / ".aider-relay" / "interrupt").exists()

    outputs = "\n".join(call.args[0] for call in io.tool_output.call_args_list)
    assert "pause requested" in outputs
    assert "pause cleared" in outputs
    assert "stop requested" in outputs


def test_campaign_status_missing_state_reports_error(tmp_path):
    commands, io = _commands(tmp_path)

    commands.cmd_campaign("status")

    io.tool_error.assert_called_once()
    assert "Campaign state not found" in io.tool_error.call_args[0][0]
