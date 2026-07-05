"""
Campaign manifest loading for deterministic relay campaigns.

The manifest describes queue intent. It does not execute providers or decide
campaign continuation; that remains in the scheduler.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from aider.relay.campaign import CampaignState, QueueRecord, UsageSnapshot


@dataclass
class CampaignManifest:
    title: str = ""
    queues: list[QueueRecord] = field(default_factory=list)
    usage_snapshot: UsageSnapshot = field(default_factory=UsageSnapshot)

    def to_state(self) -> CampaignState:
        return CampaignState(queues=list(self.queues), usage_snapshot=self.usage_snapshot)


def load_campaign_manifest(path: str | Path) -> CampaignManifest:
    path = Path(path)
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text())
    else:
        data = yaml.safe_load(path.read_text())
    return campaign_manifest_from_dict(data or {})


def campaign_manifest_from_dict(data: dict) -> CampaignManifest:
    campaign_data = data.get("campaign", {})
    queue_items = data.get("queues", [])
    if not isinstance(queue_items, list):
        raise ValueError("campaign manifest queues must be a list")

    queues = [_queue_from_manifest_item(item) for item in queue_items]
    _validate_queue_ids(queues)
    _validate_dependencies(queues)

    usage_data = data.get("usage_snapshot", {})
    usage_snapshot = UsageSnapshot.from_dict(usage_data)
    return CampaignManifest(
        title=campaign_data.get("title", ""),
        queues=queues,
        usage_snapshot=usage_snapshot,
    )


def _queue_from_manifest_item(data: dict) -> QueueRecord:
    if not isinstance(data, dict):
        raise ValueError("campaign manifest queue entries must be objects")
    if not data.get("id"):
        raise ValueError("campaign manifest queue entries require id")

    validation = data.get("validation", data.get("validation_commands", []))
    if isinstance(validation, str):
        validation = [validation]

    depends_on = data.get("depends_on", [])
    if isinstance(depends_on, str):
        depends_on = [depends_on]

    return QueueRecord(
        id=data["id"],
        title=data.get("title", data["id"]),
        prompt=data.get("prompt", data.get("task", "")),
        depends_on=list(depends_on),
        validation_commands=list(validation),
        decision_dependent=data.get("decision_dependent", False),
        useful=data.get("useful", True),
        explicit_stop=data.get("explicit_stop", False),
    )


def _validate_queue_ids(queues: list[QueueRecord]) -> None:
    seen = set()
    for queue in queues:
        if queue.id in seen:
            raise ValueError(f"duplicate campaign queue id: {queue.id}")
        seen.add(queue.id)


def _validate_dependencies(queues: list[QueueRecord]) -> None:
    known_ids = {queue.id for queue in queues}
    for queue in queues:
        for dependency_id in queue.depends_on:
            if dependency_id not in known_ids:
                raise ValueError(f"queue {queue.id} depends on unknown queue id: {dependency_id}")
