import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from aider.commands import Commands
from aider.openspec import OpenSpecAdapter


def _write_openspec_change(
    root: Path,
    change_name: str = "add-openspec-adapter",
    include_design: bool = True,
    include_tasks: bool = True,
    include_specs: bool = True,
    include_baseline_spec: bool = True,
) -> Path:
    change_dir = root / "openspec" / "changes" / change_name
    change_dir.mkdir(parents=True, exist_ok=True)
    (change_dir / ".openspec.yaml").write_text("schema: spec-driven\n")
    (change_dir / "proposal.md").write_text(
        "## Why\n\n"
        "Bridge OpenSpec changes into aider-relay planning context.\n\n"
        "## What Changes\n\n"
        "- Add an OpenSpec adapter to the planning kernel\n"
        "- Allow relay to load OpenSpec changes directly\n\n"
        "## Capabilities\n\n"
        "### New Capabilities\n"
        "- `relay-planning`: OpenSpec-backed planning snapshots\n\n"
        "### Modified Capabilities\n"
        "- `relay-runtime`: Accept OpenSpec change context in relay\n\n"
        "## Impact\n\n"
        "- aider/relay/loop.py\n"
    )

    if include_design:
        (change_dir / "design.md").write_text(
            "## Context\n\n"
            "Spec-driven context needs to stay framework-neutral.\n\n"
            "## Goals / Non-Goals\n\n"
            "**Goals:**\n"
            "- Load OpenSpec changes as planning snapshots\n\n"
            "**Non-Goals:**\n"
            "- Reimplement the OpenSpec workflow\n\n"
            "## Decisions\n\n"
            "- Use change directories as the planning unit.\n"
        )

    if include_tasks:
        (change_dir / "tasks.md").write_text(
            "## 1. Adapter\n\n"
            "- [x] 1.1 Add OpenSpecAdapter module\n"
            "- [ ] 1.2 Add relay snapshot loading support\n\n"
            "## 2. Validation\n\n"
            "- [ ] 2.1 Add adapter tests\n"
        )

    if include_specs:
        delta_dir = change_dir / "specs" / "relay-planning"
        delta_dir.mkdir(parents=True, exist_ok=True)
        (delta_dir / "spec.md").write_text(
            "## ADDED Requirements\n\n"
            "### Requirement: Load OpenSpec changes into relay\n"
            "The system MUST build a planning snapshot from an OpenSpec change directory.\n\n"
            "#### Scenario: Snapshot from explicit change\n"
            "- **WHEN** the user passes an OpenSpec change id\n"
            "- **THEN** the snapshot loads that change deterministically\n\n"
            "## MODIFIED Requirements\n\n"
            "### Requirement: Load spec context into relay\n"
            "The system MUST accept both SpecKit and OpenSpec planning context.\n\n"
            "#### Scenario: OpenSpec relay prompt\n"
            "- **WHEN** a relay run starts with an OpenSpec change\n"
            "- **THEN** unresolved tasks and scenarios appear in the prompt\n"
        )

    if include_baseline_spec:
        base_dir = root / "openspec" / "specs" / "relay-planning"
        base_dir.mkdir(parents=True, exist_ok=True)
        (base_dir / "spec.md").write_text(
            "# relay-planning Specification\n\n"
            "## Purpose\n\n"
            "Provide framework-neutral planning context to relay runs.\n"
        )

    return change_dir


class TestOpenSpecAdapter:
    def test_snapshot_defaults_to_only_change(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_openspec_change(root)

            adapter = OpenSpecAdapter(temp_dir)
            snapshot = adapter.build_snapshot()

            assert snapshot.feature_id == "add-openspec-adapter"
            assert snapshot.spec_framework == "openspec"
            assert snapshot.feature_root == "openspec/changes/add-openspec-adapter"

    def test_snapshot_requires_change_when_multiple_changes_exist(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_openspec_change(root, "add-openspec-adapter")
            _write_openspec_change(root, "add-vmodel-overlay")

            adapter = OpenSpecAdapter(temp_dir)

            with pytest.raises(ValueError) as exc:
                adapter.build_snapshot()

            assert "Multiple OpenSpec changes found" in str(exc.value)

    def test_snapshot_supports_proposal_only_change(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_openspec_change(
                root,
                include_design=False,
                include_tasks=False,
                include_specs=False,
                include_baseline_spec=False,
            )

            adapter = OpenSpecAdapter(temp_dir)
            data = adapter.build_snapshot().to_dict()

            assert data["spec_framework"] == "openspec"
            assert (
                data["capability_spec"]["summary"]
                == "Bridge OpenSpec changes into aider-relay planning context."
            )
            assert data["task_graph"]["summary"]["total"] == 0
            assert data["capability_spec"]["requirements"] == []
            assert data["verification_obligations"] == []

    def test_snapshot_includes_delta_and_baseline_specs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_openspec_change(root)

            adapter = OpenSpecAdapter(temp_dir)
            data = adapter.build_snapshot().to_dict()
            artifact_paths = {item["path"] for item in data["artifact_refs"]}

            assert (
                "openspec/changes/add-openspec-adapter/specs/relay-planning/spec.md"
                in artifact_paths
            )
            assert "openspec/specs/relay-planning/spec.md" in artifact_paths
            assert "openspec/changes/add-openspec-adapter/proposal.md" in artifact_paths

    def test_snapshot_parses_requirements_tasks_and_scenarios(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_openspec_change(root)

            adapter = OpenSpecAdapter(temp_dir)
            data = adapter.build_snapshot().to_dict()

            assert data["capability_spec"]["requirements"][0]["text"].startswith(
                "ADDED Requirements:"
            )
            assert data["task_graph"]["summary"]["completed"] == 1
            assert data["task_graph"]["summary"]["pending"] == 2
            assert len(data["verification_obligations"]) == 2
            assert data["verification_obligations"][0]["kind"] == "scenario"

    def test_snapshot_supports_explicit_change_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            change_dir = _write_openspec_change(root)

            adapter = OpenSpecAdapter(temp_dir)
            snapshot = adapter.build_snapshot(change=str(change_dir))

            assert snapshot.feature_id == "add-openspec-adapter"


class TestOpenSpecCommands:
    def setup_method(self):
        self.mock_io = Mock()
        self.mock_coder = Mock()
        self.mock_coder.root = None
        self.commands = Commands(io=self.mock_io, coder=self.mock_coder)

    def test_openspec_snapshot_with_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.mock_coder.root = temp_dir
            _write_openspec_change(root)

            self.commands.cmd_openspec("snapshot")

            self.mock_io.tool_output.assert_called_once()
            output = self.mock_io.tool_output.call_args[0][0]
            assert '"spec_framework": "openspec"' in output
            assert '"feature"' in output

    def test_openspec_snapshot_requires_change_for_multiple_changes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.mock_coder.root = temp_dir
            _write_openspec_change(root, "add-openspec-adapter")
            _write_openspec_change(root, "add-vmodel-overlay")

            self.commands.cmd_openspec("snapshot")

            self.mock_io.tool_error.assert_called_once()
            assert "Multiple OpenSpec changes found" in self.mock_io.tool_error.call_args[0][0]
