import json
import tempfile
from pathlib import Path

import pytest

from aider.speckit import SpecKitAdapter


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
        "### Snapshot Export\n"
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


class TestSpecKitAdapter:
    def test_snapshot_defaults_to_only_feature(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_sample_feature(root)

            adapter = SpecKitAdapter(temp_dir)
            snapshot = adapter.build_snapshot()

            assert snapshot.feature_id == "001-feature"
            assert snapshot.spec_framework == "speckit"

    def test_snapshot_requires_feature_when_multiple_spec_directories_exist(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_sample_feature(root, "001-feature")
            _write_sample_feature(root, "002-feature")

            adapter = SpecKitAdapter(temp_dir)

            with pytest.raises(ValueError) as exc:
                adapter.build_snapshot()

            assert "Multiple spec directories found" in str(exc.value)

    def test_snapshot_contains_planning_kernel_sections(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_sample_feature(root)

            adapter = SpecKitAdapter(temp_dir)
            snapshot = adapter.build_snapshot()
            data = snapshot.to_dict()

            assert data["schema_version"] == "1.0"
            assert data["spec_framework"] == "speckit"
            assert data["feature"]["id"] == "001-feature"
            assert "artifact_refs" in data
            assert "capability_spec" in data
            assert "implementation_plan" in data
            assert "task_graph" in data
            assert "execution_context_pack" in data
            assert "verification_obligations" in data
            assert "trace_links" in data

    def test_snapshot_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_sample_feature(root)

            adapter = SpecKitAdapter(temp_dir)

            first = adapter.build_snapshot().to_json()
            second = adapter.build_snapshot().to_json()

            assert first == second

    def test_snapshot_carries_unresolved_tasks_and_acceptance_obligations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_sample_feature(root)

            adapter = SpecKitAdapter(temp_dir)
            data = adapter.build_snapshot().to_dict()

            assert data["task_graph"]["summary"]["completed"] == 1
            assert data["task_graph"]["summary"]["pending"] == 2
            assert len(data["execution_context_pack"]["unresolved_tasks"]) == 2
            assert len(data["verification_obligations"]) == 2
            assert data["verification_obligations"][0]["kind"] == "acceptance_criterion"

    def test_snapshot_can_round_trip_via_json_file(self, tmp_path):
        _write_sample_feature(tmp_path)

        adapter = SpecKitAdapter(str(tmp_path))
        snapshot = adapter.build_snapshot()
        output_path = tmp_path / "snapshot.json"
        snapshot.write_json(output_path)

        data = json.loads(output_path.read_text())
        assert data["feature"]["id"] == "001-feature"
        assert data["execution_context_pack"]["unresolved_tasks"][0]["status"] == "pending"
