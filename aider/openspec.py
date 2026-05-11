"""
OpenSpec integration for aider.

Provides planning-snapshot export for OpenSpec change artifacts.
"""

import hashlib
import re
from pathlib import Path

from aider.planning import (
    ArtifactRef,
    PlanningSnapshot,
    PlanPhase,
    RequirementRef,
    TaskNode,
    TraceLink,
    VerificationObligation,
)


class OpenSpecAdapter:
    """Map OpenSpec change artifacts into a planning snapshot."""

    def __init__(self, root_path: str):
        self.root_path = Path(root_path)

    def list_changes(self) -> list[str]:
        changes_dir = self.root_path / "openspec" / "changes"
        if not changes_dir.exists() or not changes_dir.is_dir():
            return []

        return sorted(
            item.name
            for item in changes_dir.iterdir()
            if item.is_dir() and item.name != "archive" and not item.name.startswith(".")
        )

    def build_snapshot(self, change: str | None = None) -> PlanningSnapshot:
        change_name, change_dir = self._resolve_change(change)
        artifact_paths = self._artifact_paths(change_dir)
        artifact_refs = self._build_artifact_refs(artifact_paths)

        proposal_path = artifact_paths.get("proposal")
        design_path = artifact_paths.get("design")
        tasks_path = artifact_paths.get("tasks")

        proposal_text = (
            proposal_path.read_text() if proposal_path and proposal_path.exists() else ""
        )
        design_text = design_path.read_text() if design_path and design_path.exists() else ""
        tasks_text = tasks_path.read_text() if tasks_path and tasks_path.exists() else ""

        requirements: list[RequirementRef] = []
        verification_obligations: list[VerificationObligation] = []
        for spec_path in artifact_paths["delta_specs"]:
            spec_text = spec_path.read_text()
            source_path = str(spec_path.relative_to(self.root_path))
            requirements.extend(
                self._parse_requirements(
                    spec_text,
                    source_path,
                    starting_index=len(requirements) + 1,
                )
            )
            verification_obligations.extend(
                self._parse_verification_obligations(
                    spec_text,
                    source_path,
                    starting_index=len(verification_obligations) + 1,
                )
            )

        source_path = (
            str(tasks_path.relative_to(self.root_path))
            if tasks_path and tasks_path.exists()
            else (
                str(design_path.relative_to(self.root_path))
                if design_path and design_path.exists()
                else str(change_dir.relative_to(self.root_path))
            )
        )
        plan_phases = self._parse_plan_phases(tasks_text, source_path)
        if not plan_phases:
            plan_phases = self._parse_plan_phases(design_text, source_path)

        tasks = self._parse_task_nodes(tasks_text, source_path)

        return PlanningSnapshot(
            feature_id=change_name,
            feature_title=self._extract_title(change_name, proposal_text),
            feature_root=str(change_dir.relative_to(self.root_path)),
            artifact_refs=artifact_refs,
            summary=self._extract_summary(change_name, proposal_text, requirements),
            requirements=requirements,
            plan_phases=plan_phases,
            tasks=tasks,
            verification_obligations=verification_obligations,
            trace_links=self._build_trace_links(
                requirements, plan_phases, tasks, verification_obligations
            ),
            spec_framework="openspec",
        )

    def _resolve_change(self, change: str | None) -> tuple[str, Path]:
        change_path = self._resolve_change_path(change)
        return change_path.name, change_path

    def _resolve_change_path(self, change: str | None) -> Path:
        if change:
            explicit = self._coerce_change_path(change)
            if explicit is not None:
                return explicit

        changes = self.list_changes()
        if not changes:
            raise ValueError("No OpenSpec change directories found.")

        if change:
            if change in changes:
                return self.root_path / "openspec" / "changes" / change
            matches = [name for name in changes if name.startswith(change)]
            if len(matches) == 1:
                return self.root_path / "openspec" / "changes" / matches[0]
            if len(matches) > 1:
                raise ValueError(f"Change '{change}' is ambiguous. Matches: {', '.join(matches)}")
            raise ValueError(f"Unknown change '{change}'. Available changes: {', '.join(changes)}")

        if len(changes) == 1:
            return self.root_path / "openspec" / "changes" / changes[0]

        raise ValueError(
            "Multiple OpenSpec changes found. Please specify one of: " + ", ".join(changes)
        )

    def _coerce_change_path(self, change: str) -> Path | None:
        candidate = Path(change)
        if not candidate.is_absolute():
            candidate = self.root_path / candidate
        candidate = candidate.resolve(strict=False)

        if candidate.exists() and candidate.is_dir() and (candidate / ".openspec.yaml").exists():
            return candidate
        return None

    def _artifact_paths(self, change_dir: Path) -> dict[str, object]:
        paths: dict[str, object] = {
            "change_meta": change_dir / ".openspec.yaml",
            "proposal": change_dir / "proposal.md",
            "design": change_dir / "design.md",
            "tasks": change_dir / "tasks.md",
            "delta_specs": sorted(change_dir.glob("specs/*/spec.md")),
            "baseline_specs": [],
        }

        baseline_specs = []
        for delta_path in paths["delta_specs"]:
            capability = delta_path.parent.name
            baseline_path = self.root_path / "openspec" / "specs" / capability / "spec.md"
            if baseline_path.exists():
                baseline_specs.append(baseline_path)
        paths["baseline_specs"] = baseline_specs

        return paths

    def _build_artifact_refs(self, artifact_paths: dict[str, object]) -> list[ArtifactRef]:
        refs = []

        singular_artifacts = (
            ("change_meta", artifact_paths["change_meta"]),
            ("proposal", artifact_paths["proposal"]),
            ("design", artifact_paths["design"]),
            ("tasks", artifact_paths["tasks"]),
        )
        for kind, path in singular_artifacts:
            if not path.exists():
                continue
            refs.append(
                ArtifactRef(
                    kind=kind,
                    path=str(path.relative_to(self.root_path)),
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                )
            )

        for spec_path in artifact_paths["delta_specs"]:
            refs.append(
                ArtifactRef(
                    kind="delta_spec",
                    path=str(spec_path.relative_to(self.root_path)),
                    sha256=hashlib.sha256(spec_path.read_bytes()).hexdigest(),
                )
            )

        for spec_path in artifact_paths["baseline_specs"]:
            refs.append(
                ArtifactRef(
                    kind="baseline_spec",
                    path=str(spec_path.relative_to(self.root_path)),
                    sha256=hashlib.sha256(spec_path.read_bytes()).hexdigest(),
                )
            )

        return refs

    def _extract_title(self, change_name: str, proposal_text: str) -> str:
        bullet = self._extract_first_bullet(self._extract_section(proposal_text, "What Changes"))
        if bullet:
            return bullet

        why = self._extract_first_paragraph(self._extract_section(proposal_text, "Why"))
        if why:
            return why

        return change_name.replace("-", " ")

    def _extract_summary(
        self, change_name: str, proposal_text: str, requirements: list[RequirementRef]
    ) -> str:
        why = self._extract_first_paragraph(self._extract_section(proposal_text, "Why"))
        if why:
            return why

        if requirements:
            return requirements[0].text

        return change_name.replace("-", " ")

    def _extract_section(self, text: str, heading: str) -> str:
        lines = text.splitlines()
        target = f"## {heading}".lower()
        in_section = False
        collected = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("## "):
                if in_section and stripped.lower() != target:
                    break
                in_section = stripped.lower() == target
                continue
            if not in_section:
                continue
            if stripped.startswith("<!--"):
                continue
            collected.append(line.rstrip())
        return "\n".join(collected).strip()

    def _extract_first_paragraph(self, text: str) -> str:
        lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                if lines:
                    break
                continue
            if stripped.startswith("- ") or stripped.startswith("### "):
                break
            lines.append(stripped)
        return " ".join(lines)

    def _extract_first_bullet(self, text: str) -> str:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("- "):
                return stripped[2:].strip()
        return ""

    def _parse_requirements(
        self, text: str, source_path: str, starting_index: int = 1
    ) -> list[RequirementRef]:
        requirements = []
        current_operation = ""
        current_name = ""
        description_lines: list[str] = []

        def flush_requirement():
            if not current_name:
                return
            text_value = " ".join(
                line.strip() for line in description_lines if line.strip()
            ).strip()
            if not text_value:
                text_value = current_name
            requirement_id = f"REQ-{starting_index + len(requirements) - 1:03d}"
            if current_operation:
                text_value = f"{current_operation}: {text_value}"
            requirements.append(
                RequirementRef(id=requirement_id, text=text_value, source_path=source_path)
            )

        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("## "):
                flush_requirement()
                current_name = ""
                description_lines = []
                current_operation = stripped[3:].strip()
                continue
            if stripped.startswith("### Requirement: "):
                flush_requirement()
                current_name = stripped[len("### Requirement: ") :].strip()
                description_lines = []
                continue
            if current_name and not stripped.startswith("#### Scenario: "):
                description_lines.append(line)

        flush_requirement()
        return requirements

    def _parse_plan_phases(self, text: str, source_path: str) -> list[PlanPhase]:
        phases = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("## "):
                phases.append(
                    PlanPhase(
                        id=f"PHASE-{len(phases) + 1:03d}",
                        title=stripped[3:].strip(),
                        source_path=source_path,
                    )
                )
        return phases

    def _parse_task_nodes(self, text: str, source_path: str) -> list[TaskNode]:
        tasks = []
        current_section = ""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("## "):
                current_section = stripped[3:].strip()
                continue
            match = re.match(r"^- \[( |x|X)\]\s+(.+)$", stripped)
            if match:
                status = "completed" if match.group(1).lower() == "x" else "pending"
                tasks.append(
                    TaskNode(
                        id=f"TASK-{len(tasks) + 1:03d}",
                        title=match.group(2).strip(),
                        status=status,
                        section=current_section,
                        source_path=source_path,
                    )
                )
        return tasks

    def _parse_verification_obligations(
        self, text: str, source_path: str, starting_index: int = 1
    ) -> list[VerificationObligation]:
        obligations = []
        current_title = ""
        current_steps: list[str] = []

        def flush_scenario():
            if not current_title:
                return
            detail = " ".join(step.strip() for step in current_steps if step.strip())
            scenario_text = current_title if not detail else f"{current_title}: {detail}"
            obligations.append(
                VerificationObligation(
                    id=f"SCENARIO-{starting_index + len(obligations) - 1:03d}",
                    kind="scenario",
                    text=scenario_text,
                    status="pending",
                    source_path=source_path,
                )
            )

        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#### Scenario: "):
                flush_scenario()
                current_title = stripped[len("#### Scenario: ") :].strip()
                current_steps = []
                continue
            if current_title and stripped.startswith("- "):
                current_steps.append(stripped[2:].strip())
                continue
            if current_title and stripped.startswith("### Requirement: "):
                flush_scenario()
                current_title = ""
                current_steps = []

        flush_scenario()
        return obligations

    def _build_trace_links(
        self,
        requirements: list[RequirementRef],
        plan_phases: list[PlanPhase],
        task_nodes: list[TaskNode],
        verification_obligations: list[VerificationObligation],
    ) -> list[TraceLink]:
        links = []
        for item in requirements:
            links.append(
                TraceLink(
                    source_kind="requirement",
                    source_id=item.id,
                    target_path=item.source_path,
                )
            )
        for item in plan_phases:
            links.append(
                TraceLink(
                    source_kind="plan_phase",
                    source_id=item.id,
                    target_path=item.source_path,
                )
            )
        for item in task_nodes:
            links.append(
                TraceLink(
                    source_kind="task",
                    source_id=item.id,
                    target_path=item.source_path,
                )
            )
        for item in verification_obligations:
            links.append(
                TraceLink(
                    source_kind="verification_obligation",
                    source_id=item.id,
                    target_path=item.source_path,
                )
            )
        return links
