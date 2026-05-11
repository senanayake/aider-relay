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


def _write_upstream_style_feature(
    root: Path,
    feature_name: str = "001-user-auth",
    include_tasks: bool = True,
    include_supporting_docs: bool = False,
    feature_dir: Path | None = None,
) -> Path:
    constitution_dir = root / ".specify" / "memory"
    constitution_dir.mkdir(parents=True, exist_ok=True)
    (constitution_dir / "constitution.md").write_text(
        "# Constitution\n\n- Favor testable requirements.\n- Keep plans deterministic.\n"
    )

    if feature_dir is None:
        feature_dir = root / "specs" / feature_name
    feature_dir.mkdir(parents=True, exist_ok=True)
    (feature_dir / "spec.md").write_text(
        "# Feature Specification: User Authentication\n\n## User Scenarios & Testing\n\n### User"
        " Story 1 - Sign In (Priority: P1)\nUsers sign in with email and password to reach"
        " protected areas.\n**Why this priority**: Authentication gates all protected"
        " workflows.\n**Independent Test**: Submit valid credentials and reach the"
        " dashboard.\n**Acceptance Scenarios**:\n1. **Given** a valid user, **When** credentials"
        " are submitted, **Then** access is granted.\n\n## Requirements\n\n### Functional"
        " Requirements\n- **FR-001**: System MUST authenticate users with email and password\n-"
        " **FR-002**: System MUST reject invalid credentials with a clear error\n\n## Success"
        " Criteria\n\n- **SC-001**: 95% of valid users complete sign-in in under 30 seconds\n-"
        " **SC-002**: 100% of invalid credential attempts receive an actionable error message\n"
    )
    (feature_dir / "plan.md").write_text(
        "# Implementation Plan: User Authentication\n\n"
        "## Summary\n"
        "Implement the simplest secure sign-in flow.\n\n"
        "## Technical Context\n"
        "**Language/Version**: Python 3.12\n\n"
        "## Constitution Check\n"
        "Pass.\n\n"
        "## Project Structure\n"
        "Use the existing aider package and pytest suite.\n\n"
        "### Phase 0: Research\n"
        "Document the auth decision.\n\n"
        "### Phase 1: Design\n"
        "Model the session and update contracts.\n"
    )

    if include_tasks:
        (feature_dir / "tasks.md").write_text(
            "# Tasks: User Authentication\n\n"
            "## Phase 1: Setup\n"
            "- [x] T001 Create auth module scaffold in aider/auth.py\n\n"
            "## Phase 2: User Story 1 - Sign In (Priority: P1)\n"
            "- [ ] T002 [US1] Implement credential validation in aider/auth.py\n"
            "- [ ] T003 [P] [US1] Add integration test in tests/test_auth.py\n"
        )

    if include_supporting_docs:
        (feature_dir / "research.md").write_text(
            "# Research\n\nDecision: Password auth.\nRationale: Smallest viable flow.\n"
        )
        (feature_dir / "data-model.md").write_text("# Data Model\n\n- UserSession\n")
        (feature_dir / "quickstart.md").write_text("# Quickstart\n\nRun pytest.\n")
        contracts_dir = feature_dir / "contracts"
        contracts_dir.mkdir()
        (contracts_dir / "auth.openapi.yaml").write_text("openapi: 3.1.0\ninfo:\n  title: Auth\n")

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

    def test_snapshot_uses_feature_pointer_when_multiple_specs_exist(self, tmp_path):
        _write_upstream_style_feature(tmp_path, "001-user-auth")
        feature_dir = _write_upstream_style_feature(tmp_path, "002-billing")
        (tmp_path / ".specify" / "feature.json").write_text(
            json.dumps({"feature_directory": str(feature_dir.relative_to(tmp_path))})
        )

        adapter = SpecKitAdapter(str(tmp_path))
        snapshot = adapter.build_snapshot()

        assert snapshot.feature_id == "002-billing"
        assert snapshot.feature_root == "specs/002-billing"

    def test_snapshot_supports_upstream_style_spec_without_tasks(self, tmp_path):
        _write_upstream_style_feature(tmp_path, include_tasks=False)

        adapter = SpecKitAdapter(str(tmp_path))
        data = adapter.build_snapshot().to_dict()

        assert data["feature"]["id"] == "001-user-auth"
        assert (
            data["capability_spec"]["summary"]
            == "Users sign in with email and password to reach protected areas."
        )
        assert data["task_graph"]["summary"]["total"] == 0
        assert len(data["verification_obligations"]) == 3
        assert data["verification_obligations"][0]["kind"] == "success_criterion"
        assert data["verification_obligations"][-1]["kind"] == "independent_test"

    def test_snapshot_includes_supporting_upstream_artifacts(self, tmp_path):
        _write_upstream_style_feature(tmp_path, include_supporting_docs=True)

        adapter = SpecKitAdapter(str(tmp_path))
        data = adapter.build_snapshot().to_dict()
        artifact_paths = {item["path"] for item in data["artifact_refs"]}

        assert "specs/001-user-auth/research.md" in artifact_paths
        assert "specs/001-user-auth/data-model.md" in artifact_paths
        assert "specs/001-user-auth/quickstart.md" in artifact_paths
        assert "specs/001-user-auth/contracts/auth.openapi.yaml" in artifact_paths

    def test_snapshot_supports_feature_directory_outside_specs(self, tmp_path):
        feature_dir = tmp_path / "docs" / "features" / "auth-track"
        _write_upstream_style_feature(
            tmp_path,
            feature_name="auth-track",
            feature_dir=feature_dir,
        )
        (tmp_path / ".specify" / "feature.json").write_text(
            json.dumps({"feature_directory": "docs/features/auth-track"})
        )

        adapter = SpecKitAdapter(str(tmp_path))
        snapshot = adapter.build_snapshot()

        assert snapshot.feature_id == "auth-track"
        assert snapshot.feature_root == "docs/features/auth-track"
