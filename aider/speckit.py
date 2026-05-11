"""
SpecKit integration for aider.

Provides discovery, status reporting, and planning-snapshot export for
SpecKit-style artifacts.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from aider.planning import (
    ArtifactRef,
    PlanningSnapshot,
    PlanPhase,
    RequirementRef,
    TaskNode,
    TraceLink,
    VerificationObligation,
)


class SpecKitDiscovery:
    """Discovers and reports on SpecKit artifacts in a repository."""

    _IGNORED_TEST_DIRS = {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "site-packages",
    }

    def __init__(self, root_path: str):
        self.root_path = Path(root_path)

    def discover_artifacts(self) -> dict[str, Any]:
        """
        Discover SpecKit artifacts in the repository.

        Returns:
            Dict containing discovered artifacts and their status
        """
        artifacts = {
            "constitution": None,
            "spec_files": [],
            "spec_directories": [],
            "test_files": [],
            "summary": {},
        }

        constitution_path = self.root_path / ".specify" / "memory" / "constitution.md"
        if constitution_path.exists() and constitution_path.is_file():
            artifacts["constitution"] = str(constitution_path.relative_to(self.root_path))

        specs_dir = self.root_path / "specs"
        spec_dirs = []
        spec_files = []

        if specs_dir.exists() and specs_dir.is_dir():
            for item in specs_dir.iterdir():
                if item.is_dir():
                    spec_dir_name = f"specs/{item.name}"
                    spec_dirs.append(spec_dir_name)

                    for artifact in ["spec.md", "plan.md", "tasks.md"]:
                        artifact_path = item / artifact
                        if artifact_path.exists() and artifact_path.is_file():
                            spec_files.append(f"{spec_dir_name}/{artifact}")

        artifacts["spec_directories"] = sorted(spec_dirs)
        artifacts["spec_files"] = sorted(spec_files)

        artifacts["test_files"] = self._discover_test_files()

        mtarp_readiness = self._calculate_mtarp_readiness(artifacts)
        artifacts["summary"] = {
            "total_spec_files": len(artifacts["spec_files"]),
            "total_spec_directories": len(artifacts["spec_directories"]),
            "total_test_files": len(artifacts["test_files"]),
            "has_constitution": bool(artifacts["constitution"]),
            "complete_spec_directories": len(mtarp_readiness["complete_specs"]),
            "mtarp_ready": mtarp_readiness["ready"],
            "has_speckit_artifacts": bool(
                artifacts["constitution"]
                or artifacts["spec_files"]
                or artifacts["spec_directories"]
                or artifacts["test_files"]
            ),
        }

        return artifacts

    def _discover_test_files(self) -> list[str]:
        """Return repo-local python test files while skipping env/dependency trees."""
        test_files = set()
        for current_root, dirnames, filenames in self.root_path.walk(top_down=True):
            dirnames[:] = [
                dirname for dirname in dirnames if dirname not in self._IGNORED_TEST_DIRS
            ]
            for filename in filenames:
                if filename.endswith(".py") and (
                    "test" in filename or filename.startswith("test_")
                ):
                    relpath = current_root.joinpath(filename).relative_to(self.root_path)
                    test_files.add(str(relpath))
        return sorted(test_files)

    def _calculate_mtarp_readiness(self, artifacts: dict[str, Any]) -> dict[str, Any]:
        """Calculate MTARP readiness based on discovered artifacts."""
        has_constitution = bool(artifacts.get("constitution"))

        complete_specs = []
        for spec_dir in artifacts.get("spec_directories", []):
            has_spec = f"{spec_dir}/spec.md" in artifacts.get("spec_files", [])
            has_plan = f"{spec_dir}/plan.md" in artifacts.get("spec_files", [])
            has_tasks = f"{spec_dir}/tasks.md" in artifacts.get("spec_files", [])

            if has_spec and has_plan and has_tasks:
                complete_specs.append(spec_dir)

        return {
            "ready": has_constitution and len(complete_specs) >= 1,
            "constitution": has_constitution,
            "complete_specs": complete_specs,
            "total_specs": len(artifacts.get("spec_directories", [])),
        }

    def format_status_report(self, artifacts: dict[str, Any]) -> str:
        """Format the artifacts into a human-readable status report."""
        summary = artifacts["summary"]

        if not summary["has_speckit_artifacts"]:
            return "No SpecKit artifacts found in the repository."

        report = ["SpecKit Status Report", "=" * 20, ""]

        if artifacts["constitution"]:
            report.append(f"Constitution: Found ({artifacts['constitution']})")
        else:
            report.append("Constitution: Not found (.specify/memory/constitution.md)")
        report.append("")

        if artifacts["spec_directories"]:
            report.append(f"Spec Directories ({len(artifacts['spec_directories'])}):")
            for spec_dir in artifacts["spec_directories"]:
                has_spec = f"{spec_dir}/spec.md" in artifacts["spec_files"]
                has_plan = f"{spec_dir}/plan.md" in artifacts["spec_files"]
                has_tasks = f"{spec_dir}/tasks.md" in artifacts["spec_files"]

                if has_spec and has_plan and has_tasks:
                    report.append(f"  - {spec_dir}/ Complete (spec.md, plan.md, tasks.md)")
                else:
                    missing = []
                    if not has_spec:
                        missing.append("spec.md")
                    if not has_plan:
                        missing.append("plan.md")
                    if not has_tasks:
                        missing.append("tasks.md")
                    report.append(f"  - {spec_dir}/ Incomplete (missing {', '.join(missing)})")
            report.append("")

        if artifacts["test_files"]:
            report.append(f"Test Files ({len(artifacts['test_files'])}):")
            for test_file in artifacts["test_files"]:
                report.append(f"  - {test_file}")
            report.append("")

        report.append("Summary:")
        report.append(f"  Total spec files: {summary['total_spec_files']}")
        report.append(f"  Total spec directories: {summary['total_spec_directories']}")
        report.append(f"  Complete spec directories: {summary['complete_spec_directories']}")
        report.append(f"  Total test files: {summary['total_test_files']}")

        if summary["mtarp_ready"]:
            report.append("  MTARP Ready: Yes (constitution + 1 complete spec)")
        else:
            reasons = []
            if not summary["has_constitution"]:
                reasons.append("missing constitution")
            if summary["complete_spec_directories"] == 0:
                reasons.append("no complete specs")
            report.append(f"  MTARP Ready: No ({', '.join(reasons)})")

        return "\n".join(report)


class SpecKitAdapter:
    """Map SpecKit-compatible repo artifacts into a planning snapshot."""

    def __init__(self, root_path: str):
        self.root_path = Path(root_path)

    def list_features(self) -> list[str]:
        specs_dir = self.root_path / "specs"
        if not specs_dir.exists() or not specs_dir.is_dir():
            return []
        return sorted(item.name for item in specs_dir.iterdir() if item.is_dir())

    def build_snapshot(self, feature: str | None = None) -> PlanningSnapshot:
        feature_name, feature_dir = self._resolve_feature(feature)
        artifact_paths = self._artifact_paths(feature_dir)
        artifact_refs = self._build_artifact_refs(artifact_paths)

        spec_path = artifact_paths["spec"]
        plan_path = artifact_paths.get("plan")
        if plan_path is not None and not plan_path.exists():
            plan_path = None
        tasks_path = artifact_paths.get("tasks")
        if tasks_path is not None and not tasks_path.exists():
            tasks_path = None

        spec_text = spec_path.read_text()
        plan_text = plan_path.read_text() if plan_path else ""
        tasks_text = tasks_path.read_text() if tasks_path else ""

        spec_relpath = str(spec_path.relative_to(self.root_path))
        plan_relpath = str(plan_path.relative_to(self.root_path)) if plan_path else spec_relpath
        tasks_relpath = str(tasks_path.relative_to(self.root_path)) if tasks_path else spec_relpath

        requirements = self._parse_requirements(spec_text, spec_relpath)
        plan_phases = self._parse_plan_phases(plan_text, plan_relpath)
        task_nodes = self._parse_task_nodes(tasks_text, tasks_relpath)
        verification_obligations = self._parse_verification_obligations(spec_text, spec_relpath)

        return PlanningSnapshot(
            feature_id=feature_name,
            feature_title=self._extract_title(spec_text) or feature_name,
            feature_root=str(feature_dir.relative_to(self.root_path)),
            artifact_refs=artifact_refs,
            summary=self._extract_summary(spec_text),
            requirements=requirements,
            plan_phases=plan_phases,
            tasks=task_nodes,
            verification_obligations=verification_obligations,
            trace_links=self._build_trace_links(
                requirements, plan_phases, task_nodes, verification_obligations
            ),
        )

    def _resolve_feature(self, feature: str | None) -> tuple[str, Path]:
        feature_path = self._resolve_feature_path(feature)
        return feature_path.name, feature_path

    def _resolve_feature_path(self, feature: str | None) -> Path:
        if feature:
            explicit = self._coerce_feature_path(feature)
            if explicit is not None:
                return explicit

        features = self.list_features()
        if not features:
            current_feature = self._load_current_feature_dir()
            if current_feature is not None:
                return current_feature
            raise ValueError("No spec directories found.")

        if feature:
            if feature in features:
                return self.root_path / "specs" / feature
            matches = [name for name in features if name.startswith(feature)]
            if len(matches) == 1:
                return self.root_path / "specs" / matches[0]
            if len(matches) > 1:
                raise ValueError(f"Feature '{feature}' is ambiguous. Matches: {', '.join(matches)}")
            raise ValueError(
                f"Unknown feature '{feature}'. Available features: {', '.join(features)}"
            )

        current_feature = self._load_current_feature_dir()
        if current_feature is not None:
            return current_feature

        if len(features) == 1:
            return self.root_path / "specs" / features[0]
        raise ValueError(
            "Multiple spec directories found. Please specify one of: " + ", ".join(features)
        )

    def _coerce_feature_path(self, feature: str) -> Path | None:
        candidate = Path(feature)
        if not candidate.is_absolute():
            candidate = self.root_path / candidate
        candidate = candidate.resolve(strict=False)

        if candidate.exists() and candidate.is_dir() and (candidate / "spec.md").exists():
            return candidate
        return None

    def _load_current_feature_dir(self) -> Path | None:
        feature_file = self.root_path / ".specify" / "feature.json"
        if not feature_file.exists():
            return None

        try:
            data = json.loads(feature_file.read_text())
        except (json.JSONDecodeError, OSError):
            return None

        feature_dir = data.get("feature_directory")
        if not feature_dir:
            return None

        path = Path(feature_dir)
        if not path.is_absolute():
            path = self.root_path / path
        path = path.resolve(strict=False)

        if path.exists() and path.is_dir() and (path / "spec.md").exists():
            return path
        return None

    def _artifact_paths(self, feature_dir: Path) -> dict[str, Path]:
        paths = {
            "constitution": self.root_path / ".specify" / "memory" / "constitution.md",
            "spec": feature_dir / "spec.md",
            "plan": feature_dir / "plan.md",
            "tasks": feature_dir / "tasks.md",
            "research": feature_dir / "research.md",
            "data-model": feature_dir / "data-model.md",
            "quickstart": feature_dir / "quickstart.md",
        }
        missing = [name for name in ("spec",) if not paths[name].exists()]
        if missing:
            raise ValueError(
                f"Feature '{feature_dir.name}' is missing required artifacts: {', '.join(missing)}"
            )

        contracts_dir = feature_dir / "contracts"
        if contracts_dir.exists() and contracts_dir.is_dir():
            paths["contracts_dir"] = contracts_dir

        return paths

    def _build_artifact_refs(self, artifact_paths: dict[str, Path]) -> list[ArtifactRef]:
        refs = []
        for kind in (
            "constitution",
            "spec",
            "plan",
            "tasks",
            "research",
            "data-model",
            "quickstart",
        ):
            path = artifact_paths[kind]
            if not path.exists():
                continue
            refs.append(
                ArtifactRef(
                    kind=kind,
                    path=str(path.relative_to(self.root_path)),
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                )
            )

        contracts_dir = artifact_paths.get("contracts_dir")
        if contracts_dir:
            for contract_path in sorted(
                path for path in contracts_dir.rglob("*") if path.is_file()
            ):
                refs.append(
                    ArtifactRef(
                        kind="contract",
                        path=str(contract_path.relative_to(self.root_path)),
                        sha256=hashlib.sha256(contract_path.read_bytes()).hexdigest(),
                    )
                )
        return refs

    def _extract_title(self, text: str) -> str:
        for line in text.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return ""

    def _extract_summary(self, text: str) -> str:
        overview = self._extract_overview(text)
        if overview:
            return overview

        story_summary = self._extract_first_story_summary(text)
        if story_summary:
            return story_summary

        requirements = self._parse_requirements(text, "")
        if requirements:
            return requirements[0].text

        return self._extract_title(text)

    def _extract_overview(self, text: str) -> str:
        lines = text.splitlines()
        in_overview = False
        collected = []
        for line in lines:
            if line.startswith("## "):
                if in_overview:
                    break
                in_overview = line.strip().lower() == "## overview"
                continue
            if in_overview:
                if line.strip():
                    collected.append(line.strip())
                elif collected:
                    break
        return " ".join(collected)

    def _extract_first_story_summary(self, text: str) -> str:
        lines = text.splitlines()
        in_story = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("### User Story"):
                in_story = True
                continue
            if not in_story:
                continue
            if stripped.startswith("### ") or stripped.startswith("## "):
                break
            if not stripped:
                continue
            if stripped.startswith("**"):
                continue
            return stripped
        return ""

    def _parse_requirements(self, text: str, source_path: str) -> list[RequirementRef]:
        pattern = re.compile(r"^- \*\*([A-Z]+-\d+)\*\*:\s*(.+)$")
        requirements = []
        for line in text.splitlines():
            match = pattern.match(line.strip())
            if match:
                requirements.append(
                    RequirementRef(id=match.group(1), text=match.group(2), source_path=source_path)
                )
        return requirements

    def _parse_plan_phases(self, text: str, source_path: str) -> list[PlanPhase]:
        phases = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("## ") or stripped.startswith("### "):
                title = stripped.lstrip("#").strip()
                phases.append(
                    PlanPhase(
                        id=f"PHASE-{len(phases) + 1:03d}",
                        title=title,
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
        self, text: str, source_path: str
    ) -> list[VerificationObligation]:
        obligations = self._parse_acceptance_criteria(text, source_path)
        obligations.extend(self._parse_success_criteria(text, source_path))
        obligations.extend(self._parse_independent_tests(text, source_path))
        return obligations

    def _parse_acceptance_criteria(
        self, text: str, source_path: str
    ) -> list[VerificationObligation]:
        obligations = []
        in_acceptance = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("## "):
                if in_acceptance and stripped.lower() != "## acceptance criteria":
                    break
                in_acceptance = stripped.lower() == "## acceptance criteria"
                continue
            if not in_acceptance:
                continue
            match = re.match(r"^- \[( |x|X)\]\s+(.+)$", stripped)
            if match:
                status = "completed" if match.group(1).lower() == "x" else "pending"
                obligations.append(
                    VerificationObligation(
                        id=f"AC-{len(obligations) + 1:03d}",
                        kind="acceptance_criterion",
                        text=match.group(2).strip(),
                        status=status,
                        source_path=source_path,
                    )
                )
        return obligations

    def _parse_success_criteria(self, text: str, source_path: str) -> list[VerificationObligation]:
        obligations = []
        in_success = False
        pattern = re.compile(r"^- \*\*([A-Z]+-\d+)\*\*:\s*(.+)$")

        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("## "):
                if in_success and stripped.lower() != "## success criteria":
                    break
                in_success = stripped.lower() == "## success criteria"
                continue
            if not in_success:
                continue
            match = pattern.match(stripped)
            if match:
                obligations.append(
                    VerificationObligation(
                        id=match.group(1),
                        kind="success_criterion",
                        text=match.group(2),
                        status="pending",
                        source_path=source_path,
                    )
                )
        return obligations

    def _parse_independent_tests(self, text: str, source_path: str) -> list[VerificationObligation]:
        obligations = []
        story_id = 0

        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("### User Story"):
                story_id += 1
                continue
            if stripped.startswith("**Independent Test**:"):
                test_text = stripped.split(":", 1)[1].strip()
                obligations.append(
                    VerificationObligation(
                        id=f"US{story_id:02d}-TEST",
                        kind="independent_test",
                        text=test_text,
                        status="pending",
                        source_path=source_path,
                    )
                )
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
                    source_kind="requirement", source_id=item.id, target_path=item.source_path
                )
            )
        for item in plan_phases:
            links.append(
                TraceLink(source_kind="plan_phase", source_id=item.id, target_path=item.source_path)
            )
        for item in task_nodes:
            links.append(
                TraceLink(source_kind="task", source_id=item.id, target_path=item.source_path)
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
