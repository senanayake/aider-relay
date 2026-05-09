import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch

from aider.relay.loop import handoff_prompt, main, relay
from aider.relay.session import MTARPSession
from aider.speckit import SpecKitAdapter
from tests.helpers import MockProvider, exhausted_turn, success_turn


def _write_sample_feature(root: Path, feature_name: str = "001-feature") -> Path:
    constitution_dir = root / ".specify" / "memory"
    constitution_dir.mkdir(parents=True, exist_ok=True)
    (constitution_dir / "constitution.md").write_text(
        "# Constitution\n\n- Treat specs as intent.\n- Keep MTARP separate.\n"
    )

    feature_dir = root / "specs" / feature_name
    feature_dir.mkdir(parents=True)
    (feature_dir / "spec.md").write_text(
        "# Feature Title\n\n"
        "## Overview\n\n"
        "Deliver a deterministic snapshot for relay execution.\n\n"
        "## Functional Requirements\n\n"
        "- **FR-001**: Export a deterministic snapshot\n"
        "- **FR-002**: Carry unresolved tasks into execution context\n\n"
        "## Acceptance Criteria\n\n"
        "- [ ] Snapshot can be generated for one feature\n"
        "- [x] Discovery remains read-only\n"
    )
    (feature_dir / "plan.md").write_text(
        "# Plan\n\n"
        "### Stage 1: Parsing\n"
        "Build the adapter.\n\n"
        "### Stage 2: Export\n"
        "Write deterministic JSON.\n"
    )
    (feature_dir / "tasks.md").write_text(
        "# Tasks\n\n"
        "## Stage 1\n"
        "- [x] Rebaseline the old spec\n"
        "- [ ] Add planning-kernel structures\n"
        "## Stage 2\n"
        "- [ ] Add relay integration\n"
    )
    return feature_dir


def _sample_snapshot(root: Path):
    _write_sample_feature(root)
    return SpecKitAdapter(str(root)).build_snapshot()


class TestPlanningSnapshotSpecContext:
    def test_to_spec_context_contains_framework_neutral_fields(self, tmp_path):
        snapshot = _sample_snapshot(tmp_path)

        context = snapshot.to_spec_context()

        assert context["spec_framework"] == "speckit"
        assert context["change_id"] == "001-feature"
        assert context["feature"]["title"] == "Feature Title"
        assert (
            context["capability_summary"] == "Deliver a deterministic snapshot for relay execution."
        )
        assert len(context["artifact_refs"]) == 4
        assert len(context["execution_context_pack"]["unresolved_tasks"]) == 2
        assert len(context["verification_refs"]) == 2
        assert len(context["trace_refs"]) >= 1


class TestMTARPSessionSpecContext:
    def test_round_trip_preserves_spec_context(self, tmp_path):
        snapshot = _sample_snapshot(tmp_path)
        session = MTARPSession(task_description="test", spec_context=snapshot.to_spec_context())

        path = tmp_path / "session.json"
        session.write(path)
        loaded = MTARPSession.read(path)

        assert loaded.spec_context["spec_framework"] == "speckit"
        assert loaded.spec_context["change_id"] == "001-feature"


class TestHandoffPromptSpecContext:
    def test_handoff_prompt_includes_planning_context(self, tmp_path):
        snapshot = _sample_snapshot(tmp_path)
        session = MTARPSession(task_description="test", spec_context=snapshot.to_spec_context())

        with patch("subprocess.check_output", return_value="(clean)"):
            prompt = handoff_prompt("test", session=session, git_repo=None)

        assert "## Planning Context" in prompt
        assert "Feature Title" in prompt
        assert "Add planning-kernel structures" in prompt
        assert "Snapshot can be generated for one feature" in prompt


class TestRelaySpecContext:
    def test_initial_prompt_includes_planning_context_when_snapshot_provided(self, tmp_path):
        snapshot = _sample_snapshot(tmp_path)
        primary = MockProvider([success_turn()], session_id="primary-session")
        fallback = MockProvider([], session_id="fallback-session")

        with patch("aider.relay.loop.make_provider") as mock_make:
            mock_make.side_effect = lambda name: primary if name == "claude" else fallback
            with patch("builtins.input", side_effect=EOFError()):
                asyncio.run(
                    relay(
                        "test task",
                        "claude",
                        "codex",
                        session_dir=str(tmp_path),
                        snapshot=snapshot,
                    )
                )

        prompt = primary.prompts_received[0]
        assert "## Planning Context" in prompt
        assert "Add planning-kernel structures" in prompt
        assert "Snapshot can be generated for one feature" in prompt

    def test_session_json_and_handoff_prompt_carry_spec_context(self, tmp_path):
        snapshot = _sample_snapshot(tmp_path)
        primary = MockProvider([exhausted_turn()], session_id="primary-session")
        fallback = MockProvider([success_turn()], session_id="fallback-session")

        with patch("aider.relay.loop.make_provider") as mock_make:
            mock_make.side_effect = lambda name: primary if name == "claude" else fallback
            with patch("builtins.input", side_effect=EOFError()):
                asyncio.run(
                    relay(
                        "test task",
                        "claude",
                        "codex",
                        session_dir=str(tmp_path),
                        snapshot=snapshot,
                    )
                )

        session_data = json.loads((tmp_path / "session.json").read_text())
        assert session_data["spec_context"]["spec_framework"] == "speckit"
        assert session_data["spec_context"]["change_id"] == "001-feature"

        handoff = fallback.prompts_received[0]
        assert "## Planning Context" in handoff
        assert "Feature Title" in handoff
        assert "Add relay integration" in handoff


class TestRelayMainSpecLoading:
    def test_main_loads_snapshot_from_file(self, tmp_path, monkeypatch):
        snapshot = _sample_snapshot(tmp_path)
        snapshot_path = tmp_path / "snapshot.json"
        snapshot.write_json(snapshot_path)

        captured = {}

        async def fake_relay(task, primary, fallback, sim_exhaust_after=0, **kwargs):
            captured["task"] = task
            captured["snapshot"] = kwargs.get("snapshot")

        monkeypatch.setattr(
            sys,
            "argv",
            ["aider-relay", "--spec-snapshot", str(snapshot_path), "test task"],
        )

        with patch("aider.relay.loop.relay", side_effect=fake_relay):
            main()

        assert captured["task"] == "test task"
        assert captured["snapshot"].feature_id == "001-feature"

    def test_main_builds_snapshot_from_spec_feature(self, tmp_path, monkeypatch):
        _write_sample_feature(tmp_path)
        captured = {}

        async def fake_relay(task, primary, fallback, sim_exhaust_after=0, **kwargs):
            captured["task"] = task
            captured["snapshot"] = kwargs.get("snapshot")

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["aider-relay", "--spec", "001-feature", "test task"])

        with patch("aider.relay.loop.relay", side_effect=fake_relay):
            main()

        assert captured["task"] == "test task"
        assert captured["snapshot"].feature_id == "001-feature"
