"""Empirical smoke test for the upstream specify-cli consumption bridge."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from aider.speckit import SpecKitAdapter


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a command and return captured text output."""
    return subprocess.run(cmd, cwd=cwd, check=True, text=True, capture_output=True)


def scaffold_feature(project_dir: Path, description: str) -> Path:
    """Run the real upstream feature scaffold script and return the feature directory."""
    result = run(
        ["bash", ".specify/scripts/bash/create-new-feature.sh", "--json", description],
        cwd=project_dir,
    )
    first_line = result.stdout.strip().splitlines()[0]
    spec_file = Path(json.loads(first_line)["SPEC_FILE"])
    return spec_file.parent


def write_feature_artifacts(feature_dir: Path) -> None:
    """Populate the scaffolded feature with upstream-style artifact content."""
    (feature_dir / "spec.md").write_text(
        "# Feature Specification: Relay Spec Bridge\n\n"
        "## User Scenarios & Testing\n\n"
        "### User Story 1 - Consume Upstream Specs (Priority: P1)\n"
        "Relay users load the active upstream Spec Kit feature into aider-relay.\n"
        "**Why this priority**: Relay continuity depends on deterministic spec context.\n"
        "**Independent Test**: Initialize a real upstream Spec Kit project, scaffold two "
        "features, and confirm aider-relay selects the active one.\n\n"
        "## Requirements\n\n"
        "### Functional Requirements\n"
        "- **FR-001**: System MUST load the active feature from .specify/feature.json\n"
        "- **FR-002**: System MUST tolerate upstream staged artifacts when tasks.md is absent\n\n"
        "## Success Criteria\n\n"
        "- **SC-001**: Active feature snapshot loads without passing an explicit feature id\n"
        "- **SC-002**: Supporting artifacts appear as traceable artifact refs\n"
    )
    (feature_dir / "plan.md").write_text(
        "# Implementation Plan: Relay Spec Bridge\n\n"
        "## Summary\n"
        "Bridge real upstream Spec Kit artifacts into aider-relay.\n\n"
        "### Phase 0: Verify Upstream Contract\n"
        "Use the real specify init and scaffold scripts.\n\n"
        "### Phase 1: Consume Active Feature\n"
        "Build a planning snapshot from the active feature pointer.\n"
    )
    (feature_dir / "tasks.md").write_text(
        "# Tasks: Relay Spec Bridge\n\n"
        "## Phase 1: Active Feature Loading\n"
        "- [x] T001 Initialize an upstream Spec Kit project\n"
        "- [ ] T002 Confirm aider-relay loads the active scaffolded feature\n"
    )
    (feature_dir / "research.md").write_text(
        "# Research\n\nDecision: Use upstream specify-cli as the artifact producer.\n"
    )
    (feature_dir / "data-model.md").write_text("# Data Model\n\n- PlanningSnapshot\n")
    (feature_dir / "quickstart.md").write_text(
        "# Quickstart\n\nRun `task dc:specify -- check` in a Spec Kit workspace.\n"
    )
    contracts_dir = feature_dir / "contracts"
    contracts_dir.mkdir(exist_ok=True)
    (contracts_dir / "relay.openapi.yaml").write_text(
        "openapi: 3.1.0\ninfo:\n  title: Relay Spec Bridge\n"
    )


def main() -> None:
    speckit_ref = os.environ.get("SPECKIT_REF", "v0.8.7")
    specify_source = f"git+https://github.com/github/spec-kit.git@{speckit_ref}"

    with tempfile.TemporaryDirectory() as tmp_dir:
        project_dir = Path(tmp_dir)
        run(
            [
                "uvx",
                "--from",
                specify_source,
                "specify",
                "init",
                ".",
                "--integration",
                "codex",
                "--script",
                "sh",
            ],
            cwd=project_dir,
        )

        first_feature_dir = scaffold_feature(project_dir, "Create a placeholder smoke feature")
        active_feature_dir = scaffold_feature(project_dir, "Bridge local relay consumption")
        # The upstream helper script scaffolds the feature directory and reports SPEC_FILE,
        # but the higher-level Spec Kit command flow is what persists .specify/feature.json.
        (project_dir / ".specify" / "feature.json").write_text(
            json.dumps({"feature_directory": str(active_feature_dir.relative_to(project_dir))})
        )
        write_feature_artifacts(active_feature_dir)

        feature_pointer = json.loads((project_dir / ".specify" / "feature.json").read_text())
        snapshot = SpecKitAdapter(str(project_dir)).build_snapshot()
        artifact_paths = {item.path for item in snapshot.artifact_refs}

        checks = {
            "init_structure": (project_dir / ".specify" / "integration.json").exists(),
            "first_feature_distinct": first_feature_dir != active_feature_dir,
            "active_pointer": feature_pointer["feature_directory"] == str(
                active_feature_dir.relative_to(project_dir)
            ),
            "snapshot_selected_active_feature": snapshot.feature_id == active_feature_dir.name,
            "supporting_artifacts": {
                f"specs/{active_feature_dir.name}/research.md",
                f"specs/{active_feature_dir.name}/data-model.md",
                f"specs/{active_feature_dir.name}/quickstart.md",
                f"specs/{active_feature_dir.name}/contracts/relay.openapi.yaml",
            }.issubset(artifact_paths),
            "verification_obligations": len(snapshot.verification_obligations) == 3,
        }

        print(
            "SMOKE SPECIFY: "
            f"ref={speckit_ref} "
            f"feature={snapshot.feature_id} "
            f"requirements={len(snapshot.requirements)} "
            f"tasks={len(snapshot.tasks)} "
            f"verification={len(snapshot.verification_obligations)}"
        )
        print(
            "SMOKE SPECIFY CHECKS: "
            + ", ".join(f"{key}={'yes' if value else 'no'}" for key, value in checks.items())
        )

        if not all(checks.values()):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
