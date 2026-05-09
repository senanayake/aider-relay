"""
Framework-neutral planning-kernel data structures.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ArtifactRef:
    kind: str
    path: str
    sha256: str

    def to_dict(self) -> dict:
        return {"kind": self.kind, "path": self.path, "sha256": self.sha256}

    @classmethod
    def from_dict(cls, data: dict) -> "ArtifactRef":
        return cls(kind=data["kind"], path=data["path"], sha256=data["sha256"])


@dataclass(frozen=True)
class RequirementRef:
    id: str
    text: str
    source_path: str

    def to_dict(self) -> dict:
        return {"id": self.id, "text": self.text, "source_path": self.source_path}

    @classmethod
    def from_dict(cls, data: dict) -> "RequirementRef":
        return cls(id=data["id"], text=data["text"], source_path=data["source_path"])


@dataclass(frozen=True)
class PlanPhase:
    id: str
    title: str
    source_path: str

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "source_path": self.source_path}

    @classmethod
    def from_dict(cls, data: dict) -> "PlanPhase":
        return cls(id=data["id"], title=data["title"], source_path=data["source_path"])


@dataclass(frozen=True)
class TaskNode:
    id: str
    title: str
    status: str
    section: str
    source_path: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "section": self.section,
            "source_path": self.source_path,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TaskNode":
        return cls(
            id=data["id"],
            title=data["title"],
            status=data["status"],
            section=data["section"],
            source_path=data["source_path"],
        )


@dataclass(frozen=True)
class VerificationObligation:
    id: str
    kind: str
    text: str
    status: str
    source_path: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "text": self.text,
            "status": self.status,
            "source_path": self.source_path,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "VerificationObligation":
        return cls(
            id=data["id"],
            kind=data["kind"],
            text=data["text"],
            status=data["status"],
            source_path=data["source_path"],
        )


@dataclass(frozen=True)
class TraceLink:
    source_kind: str
    source_id: str
    target_path: str

    def to_dict(self) -> dict:
        return {
            "source_kind": self.source_kind,
            "source_id": self.source_id,
            "target_path": self.target_path,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TraceLink":
        return cls(
            source_kind=data["source_kind"],
            source_id=data["source_id"],
            target_path=data["target_path"],
        )


@dataclass
class PlanningSnapshot:
    feature_id: str
    feature_title: str
    feature_root: str
    artifact_refs: list[ArtifactRef]
    summary: str
    requirements: list[RequirementRef]
    plan_phases: list[PlanPhase]
    tasks: list[TaskNode]
    verification_obligations: list[VerificationObligation]
    trace_links: list[TraceLink]
    spec_framework: str = "speckit"
    schema_version: str = "1.0"
    execution_context_pack: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.execution_context_pack:
            unresolved = [task.to_dict() for task in self.tasks if task.status != "completed"]
            self.execution_context_pack = {
                "unresolved_tasks": unresolved,
                "verification_obligation_ids": [item.id for item in self.verification_obligations],
            }

    def to_dict(self) -> dict:
        completed = sum(1 for task in self.tasks if task.status == "completed")
        pending = len(self.tasks) - completed
        return {
            "schema_version": self.schema_version,
            "spec_framework": self.spec_framework,
            "feature": {
                "id": self.feature_id,
                "title": self.feature_title,
                "root": self.feature_root,
            },
            "artifact_refs": [item.to_dict() for item in self.artifact_refs],
            "capability_spec": {
                "summary": self.summary,
                "requirements": [item.to_dict() for item in self.requirements],
            },
            "implementation_plan": {
                "phases": [item.to_dict() for item in self.plan_phases],
            },
            "task_graph": {
                "tasks": [item.to_dict() for item in self.tasks],
                "summary": {"total": len(self.tasks), "completed": completed, "pending": pending},
            },
            "execution_context_pack": self.execution_context_pack,
            "verification_obligations": [item.to_dict() for item in self.verification_obligations],
            "trace_links": [item.to_dict() for item in self.trace_links],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False)

    def write_json(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json())

    @classmethod
    def from_dict(cls, data: dict) -> "PlanningSnapshot":
        return cls(
            schema_version=data.get("schema_version", "1.0"),
            spec_framework=data.get("spec_framework", "speckit"),
            feature_id=data["feature"]["id"],
            feature_title=data["feature"]["title"],
            feature_root=data["feature"]["root"],
            artifact_refs=[ArtifactRef.from_dict(item) for item in data.get("artifact_refs", [])],
            summary=data.get("capability_spec", {}).get("summary", ""),
            requirements=[
                RequirementRef.from_dict(item)
                for item in data.get("capability_spec", {}).get("requirements", [])
            ],
            plan_phases=[
                PlanPhase.from_dict(item)
                for item in data.get("implementation_plan", {}).get("phases", [])
            ],
            tasks=[
                TaskNode.from_dict(item) for item in data.get("task_graph", {}).get("tasks", [])
            ],
            verification_obligations=[
                VerificationObligation.from_dict(item)
                for item in data.get("verification_obligations", [])
            ],
            trace_links=[TraceLink.from_dict(item) for item in data.get("trace_links", [])],
            execution_context_pack=data.get("execution_context_pack", {}),
        )

    @classmethod
    def read_json(cls, path: str | Path) -> "PlanningSnapshot":
        return cls.from_dict(json.loads(Path(path).read_text()))
