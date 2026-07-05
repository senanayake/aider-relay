import json

from aider.relay.campaign import (
    CAMPAIGN_SCHEMA_VERSION,
    CampaignEvent,
    CampaignState,
    DryRunWorkerResult,
    QueueRecord,
    QueueState,
    UsageSnapshot,
    run_dry_worker_turn,
    schedule_next_queue,
)


def _queue(queue_id, **kwargs):
    return QueueRecord(id=queue_id, title=queue_id, **kwargs)


def test_completed_queue_promotes_next_candidate():
    state = CampaignState(queues=[_queue("A"), _queue("B")])

    schedule_next_queue(state)
    assert state.active_queue_id == "A"

    run_dry_worker_turn(state, DryRunWorkerResult.COMPLETED, "done")

    assert state.queues[0].state == QueueState.COMPLETED
    assert state.active_queue_id == "B"
    assert state.queues[1].state == QueueState.ACTIVE
    assert state.validation_receipts[-1].passed is True


def test_blocked_decision_queue_is_deferred_and_another_candidate_promoted():
    state = CampaignState(queues=[_queue("needs-decision"), _queue("independent")])

    schedule_next_queue(state)
    run_dry_worker_turn(state, DryRunWorkerResult.BLOCKED_DECISION, "needs product call")

    assert state.queues[0].state == QueueState.DEFERRED_DECISION
    assert state.active_queue_id == "independent"
    assert state.queues[1].state == QueueState.ACTIVE


def test_blocked_external_queue_does_not_stop_campaign_if_candidate_exists():
    state = CampaignState(queues=[_queue("blocked"), _queue("still-useful")])

    schedule_next_queue(state)
    run_dry_worker_turn(state, DryRunWorkerResult.BLOCKED_EXTERNAL, "service unavailable")

    assert state.queues[0].state == QueueState.BLOCKED_EXTERNAL
    assert state.active_queue_id == "still-useful"
    assert state.stop_audit is None
    assert not state.stopped


def test_scheduler_stops_only_when_no_decision_independent_useful_queue_remains():
    state = CampaignState(
        queues=[
            _queue("active"),
            _queue("needs-decision", decision_dependent=True),
            _queue("not-worth-it", useful=False),
            _queue("explicit-stop", explicit_stop=True),
        ]
    )

    schedule_next_queue(state)
    run_dry_worker_turn(state, DryRunWorkerResult.BLOCKED_EXTERNAL, "waiting on vendor")

    assert state.stopped
    assert state.active_queue_id is None
    assert state.queues[0].state == QueueState.BLOCKED_EXTERNAL
    assert state.queues[1].state == QueueState.DEFERRED_DECISION
    assert state.queues[2].state == QueueState.ABANDONED_LOW_VALUE
    assert state.queues[3].state == QueueState.CANDIDATE


def test_stop_audit_records_why_campaign_stopped():
    state = CampaignState(
        queues=[
            _queue("finished", state=QueueState.COMPLETED),
            _queue("decision", state=QueueState.DEFERRED_DECISION),
            _queue("external", state=QueueState.BLOCKED_EXTERNAL),
            _queue("validation", state=QueueState.FAILED_VALIDATION),
            _queue("low-value", state=QueueState.ABANDONED_LOW_VALUE),
            _queue("stopped", explicit_stop=True),
        ]
    )

    schedule_next_queue(state)

    audit = state.stop_audit
    assert audit is not None
    assert audit.stopped is True
    assert "no decision-independent useful candidate" in audit.reason
    assert audit.completed_queue_ids == ["finished"]
    assert audit.deferred_queue_ids == ["decision"]
    assert audit.blocked_queue_ids == ["external"]
    assert audit.failed_queue_ids == ["validation"]
    assert audit.low_value_queue_ids == ["low-value"]
    assert audit.explicit_stop_queue_ids == ["stopped"]


def test_usage_unknown_triggers_conservative_mode_without_blocking_scheduling():
    state = CampaignState(
        queues=[_queue("first"), _queue("second")],
        usage_snapshot=UsageSnapshot.unknown(provider="codex"),
    )

    schedule_next_queue(state)

    assert state.usage_snapshot.known is False
    assert state.usage_snapshot.conservative_mode is True
    assert state.active_queue_id == "first"
    assert not state.stopped

    run_dry_worker_turn(state, DryRunWorkerResult.LOW_VALUE, "scope is no longer valuable")
    run_dry_worker_turn(state, DryRunWorkerResult.COMPLETED, "done")

    assert state.stopped
    assert state.stop_audit.conservative_mode is True


def test_campaign_state_serializes_enums_as_strings():
    state = CampaignState(
        campaign_id="campaign-1",
        created_at="2026-07-05T00:00:00+00:00",
        updated_at="2026-07-05T00:00:00+00:00",
        queues=[
            _queue(
                "A",
                state=QueueState.BLOCKED_EXTERNAL,
                last_result=DryRunWorkerResult.BLOCKED_EXTERNAL,
                reason="waiting on dependency",
            )
        ],
    )

    data = state.to_dict()

    assert data["schema_version"] == CAMPAIGN_SCHEMA_VERSION
    assert data["queues"][0]["state"] == "blocked_external"
    assert data["queues"][0]["last_result"] == "blocked_external"


def test_campaign_state_round_trip_preserves_active_queue():
    state = CampaignState(
        campaign_id="campaign-1",
        created_at="2026-07-05T00:00:00+00:00",
        updated_at="2026-07-05T00:00:00+00:00",
        queues=[_queue("A"), _queue("B")],
    )

    schedule_next_queue(state)
    loaded = CampaignState.from_dict(state.to_dict())

    assert loaded.campaign_id == "campaign-1"
    assert loaded.active_queue_id == "A"
    assert loaded.active_queue().id == "A"
    assert loaded.queues[0].state == QueueState.ACTIVE


def test_campaign_state_round_trip_preserves_worker_turns_and_receipts():
    state = CampaignState(
        campaign_id="campaign-1",
        created_at="2026-07-05T00:00:00+00:00",
        updated_at="2026-07-05T00:00:00+00:00",
        queues=[_queue("A")],
    )

    schedule_next_queue(state)
    run_dry_worker_turn(state, DryRunWorkerResult.COMPLETED, "done")
    loaded = CampaignState.from_dict(state.to_dict())

    assert loaded.worker_turns[0].queue_id == "A"
    assert loaded.worker_turns[0].result == DryRunWorkerResult.COMPLETED
    assert loaded.validation_receipts[0].queue_id == "A"
    assert loaded.validation_receipts[0].passed is True


def test_campaign_state_round_trip_preserves_stop_audit_and_unknown_usage():
    state = CampaignState(
        campaign_id="campaign-1",
        created_at="2026-07-05T00:00:00+00:00",
        updated_at="2026-07-05T00:00:00+00:00",
        queues=[_queue("A", decision_dependent=True)],
        usage_snapshot=UsageSnapshot.unknown(provider="codex"),
    )

    schedule_next_queue(state)
    loaded = CampaignState.from_dict(state.to_dict())

    assert loaded.usage_snapshot.known is False
    assert loaded.usage_snapshot.provider == "codex"
    assert loaded.stop_audit is not None
    assert loaded.stop_audit.deferred_queue_ids == ["A"]
    assert loaded.stop_audit.conservative_mode is True


def test_campaign_state_write_and_read(tmp_path):
    state = CampaignState(
        campaign_id="campaign-1",
        created_at="2026-07-05T00:00:00+00:00",
        updated_at="2026-07-05T00:00:00+00:00",
        queues=[_queue("A"), _queue("B")],
    )
    schedule_next_queue(state)

    path = tmp_path / ".aider-relay" / "campaign.json"
    state.write(path)
    loaded = CampaignState.read(path)

    assert path.exists()
    assert json.loads(path.read_text()) == state.to_dict()
    assert loaded.to_dict() == state.to_dict()


def test_campaign_state_ignores_unknown_future_fields():
    data = {
        "schema_version": "1.0",
        "campaign_id": "campaign-1",
        "created_at": "2026-07-05T00:00:00+00:00",
        "updated_at": "2026-07-05T00:00:00+00:00",
        "active_queue_id": None,
        "queues": [{"id": "A", "future_queue_field": "ignored"}],
        "worker_turns": [],
        "validation_receipts": [],
        "usage_snapshot": {"known": True, "future_usage_field": "ignored"},
        "stop_audit": None,
        "future_campaign_field": "ignored",
    }

    loaded = CampaignState.from_dict(data)

    assert loaded.campaign_id == "campaign-1"
    assert loaded.queues[0].id == "A"
    assert loaded.queues[0].state == QueueState.CANDIDATE


def test_campaign_state_round_trip_preserves_events():
    state = CampaignState(queues=[_queue("A")])
    state.events.append(
        CampaignEvent(
            type="queue.started",
            message="started",
            queue_id="A",
            provider="codex",
            data={"n": 1},
        )
    )

    loaded = CampaignState.from_dict(state.to_dict())

    assert loaded.events[0].type == "queue.started"
    assert loaded.events[0].queue_id == "A"
    assert loaded.events[0].provider == "codex"
    assert loaded.events[0].data == {"n": 1}
