"""Empirical smoke test for the upstream OpenSpec consumption bridge."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from aider.openspec import OpenSpecAdapter


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a command and return captured text output."""
    return subprocess.run(cmd, cwd=cwd, check=True, text=True, capture_output=True)


def write_change_artifacts(project_dir: Path, change_name: str) -> Path:
    """Populate the OpenSpec change shell with planning artifacts."""
    change_dir = project_dir / "openspec" / "changes" / change_name
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
    (change_dir / "tasks.md").write_text(
        "## 1. Adapter\n\n"
        "- [x] 1.1 Add OpenSpecAdapter module\n"
        "- [ ] 1.2 Add relay snapshot loading support\n\n"
        "## 2. Validation\n\n"
        "- [ ] 2.1 Add adapter tests\n"
    )

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

    baseline_dir = project_dir / "openspec" / "specs" / "relay-planning"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    (baseline_dir / "spec.md").write_text(
        "# relay-planning Specification\n\n"
        "## Purpose\n\n"
        "Provide framework-neutral planning context to relay runs.\n"
    )

    return change_dir


def main() -> None:
    openspec_version = os.environ.get("OPENSPEC_VERSION", "1.3.1")
    package_ref = f"@fission-ai/openspec@{openspec_version}"
    change_name = "add-openspec-adapter"

    with tempfile.TemporaryDirectory() as tmp_dir:
        project_dir = Path(tmp_dir)
        run(["npx", "-y", package_ref, "init", "--tools", "codex"], cwd=project_dir)
        run(["npx", "-y", package_ref, "new", "change", change_name], cwd=project_dir)

        change_dir = project_dir / "openspec" / "changes" / change_name
        change_meta_exists = (change_dir / ".openspec.yaml").exists()
        write_change_artifacts(project_dir, change_name)

        snapshot = OpenSpecAdapter(str(project_dir)).build_snapshot()
        artifact_paths = {item.path for item in snapshot.artifact_refs}

        checks = {
            "codex_skills": (
                project_dir / ".codex" / "skills" / "openspec-propose" / "SKILL.md"
            ).exists(),
            "change_shell": change_meta_exists,
            "snapshot_selected_change": snapshot.feature_id == change_name,
            "summary": (
                snapshot.summary == "Bridge OpenSpec changes into aider-relay planning context."
            ),
            "supporting_artifacts": {
                f"openspec/changes/{change_name}/proposal.md",
                f"openspec/changes/{change_name}/design.md",
                f"openspec/changes/{change_name}/tasks.md",
                f"openspec/changes/{change_name}/specs/relay-planning/spec.md",
                "openspec/specs/relay-planning/spec.md",
            }.issubset(artifact_paths),
            "scenario_obligations": len(snapshot.verification_obligations) == 2,
        }

        print(
            "SMOKE OPENSPEC: "
            f"version={openspec_version} "
            f"change={snapshot.feature_id} "
            f"requirements={len(snapshot.requirements)} "
            f"tasks={len(snapshot.tasks)} "
            f"verification={len(snapshot.verification_obligations)}"
        )
        print(
            "SMOKE OPENSPEC CHECKS: "
            + ", ".join(f"{key}={'yes' if value else 'no'}" for key, value in checks.items())
        )

        if not all(checks.values()):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
