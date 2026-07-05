---
id: KB-2026-059
type: standard
status: draft
created: 2026-07-05
updated: 2026-07-05
tags: [relay, campaign, scheduler, deterministic-control-plane, persistence, mtarp]
related: [KB-2026-021, KB-2026-026, KB-2026-050, KB-2026-052]
---

# Deterministic Campaign Scheduler Standard

## Context & Problem Statement

Long-running relay campaigns need an owned control plane. Codex, Claude, and other agentic
providers are bounded workers: they can produce useful output, but they must not decide whether the
overall campaign is blocked, should continue, or should stop.

The immediate implementation queue proved the first scheduler dry run without invoking real
providers or scraping usage analytics.

## Standard/Pattern Description

### Core Principles

- Campaign progress is determined from orchestrator-owned queue state.
- A blocked queue is not a blocked campaign while decision-independent useful queues remain.
- Worker results are inputs to the state machine, not authority over the campaign loop.
- Unknown usage enters conservative mode, but does not block deterministic scheduling by itself.

### Implementation

Use `aider.relay.campaign` records for campaign dry runs:

- `CampaignState`
- `QueueRecord`
- `WorkerTurn`
- `ValidationReceipt`
- `StopAudit`
- `UsageSnapshot`

The scheduler promotes candidates in list order only when they are useful, decision-independent, and
not explicitly stopped. It records a stop audit when no promotable queue remains.

Campaign state is persisted as deterministic JSON. The artifact uses string enum values, a schema
version, campaign ID, timestamps, queue records, worker turns, validation receipts, usage snapshot,
and optional stop audit. Readers ignore unknown future fields so later queue metadata can be added
without breaking existing state files.

Campaign manifests describe queue intent only. They can supply queue prompts, dependencies,
decision-dependency flags, usefulness flags, explicit stops, and validation commands. The manifest
loader validates duplicate queue IDs and unknown dependencies before creating `CampaignState`.

The top-level campaign function is `run_autonomous_campaign()` in
`aider.relay.campaign_runner`. It owns scheduling, worker invocation, validation, persistence, and
stop auditing. Workers implement a small `CampaignWorker` protocol and return normalized
`WorkerResult` outcomes. The shipped `ScriptedCampaignWorker` proves the loop without invoking real
provider CLIs.

Codex CLI is the first real worker adapter. `CodexCliCampaignWorker` wraps the existing
`CodexProvider` and maps provider events into campaign outcomes. It uses `codex exec --json` through
the provider, supports read-only sandbox and ephemeral mode for smoke tests, and does not read,
write, log, or persist credentials.

The operator CLI starts at:

```bash
aider-relay campaign run --manifest campaign.yaml --worker codex
aider-relay campaign resume --state .aider-relay/campaign.json --worker codex
aider-relay campaign status --state .aider-relay/campaign.json
aider-relay campaign status --state .aider-relay/campaign.json --watch
```

For trusted, externally isolated workspaces where approval prompts would prevent useful throughput,
the Codex worker can be launched with:

```bash
aider-relay campaign run \
  --manifest campaign.yaml \
  --worker codex \
  --codex-dangerously-bypass-approvals-and-sandbox
```

This passes Codex's `--dangerously-bypass-approvals-and-sandbox` flag and intentionally omits
`--sandbox`. It should only be used in an externally isolated environment.

Campaign runs emit live telemetry events for queue starts/outcomes, provider start/text/completion,
validation command starts/outcomes, and campaign stops. The same events are persisted in
`.aider-relay/campaign.json`, so `campaign status --watch` can tail state from another terminal.
They can also be appended to `.aider-relay/campaign.events.jsonl` so all-day campaigns do not rely
only on the mutable state file for history.

Operational controls now include:

- interrupt sentinel: `.aider-relay/interrupt`
- pause sentinel: `.aider-relay/pause`
- heartbeat events
- max runtime
- optional clean-worktree guard
- optional checkpoint command after each queue
- Codex exhaustion metadata in `UsageSnapshot`

### Key Rules

- Rule 1: Do not stop the campaign solely because the active queue becomes externally blocked.
- Rule 2: Defer decision-dependent queues and continue with independent candidates when available.
- Rule 3: Record a stop audit whenever the scheduler stops.
- Rule 4: Keep this dry-run layer provider-free; real CLI invocation belongs in a later queue.
- Rule 5: Persist campaign state after control-plane decisions so resume behavior can be
  deterministic.
- Rule 6: Validation commands are orchestrator-owned receipts, not worker self-attestation.
- Rule 7: Dependencies are scheduler inputs; a candidate with unmet dependencies is not promoted.
- Rule 8: Real providers must be adapted behind `CampaignWorker`; they must not own campaign
  continuation.
- Rule 9: Provider adapters must not scrape browser state, ChatGPT analytics, or credentials.
- Rule 10: Dangerous Codex permission bypass must be explicit at the CLI and documented as requiring
  an externally isolated workspace.
- Rule 11: Long-running campaigns must emit persisted telemetry events; final summaries alone are
  insufficient for operator control.
- Rule 12: Long-running campaigns need out-of-band operator controls (`interrupt` and `pause`) that
  do not depend on worker cooperation.
- Rule 13: Checkpoint commits must be explicit operator configuration, not an implicit side effect.

## Rationale & Benefits

- Prevents worker prompt discipline from becoming a control-plane dependency.
- Makes campaign stop decisions reproducible and testable.
- Creates a small state model that later provider integrations can feed without owning the loop.

## Alternatives & Evidence

### Alternative 1

Let the worker decide whether to continue.

- Why not chosen: provider prompts are not a reliable enforcement boundary.
- When it might be appropriate: manual one-shot relay runs where no campaign orchestration exists.

### Alternative 2

Treat any blocked queue as a blocked campaign.

- Why not chosen: it wastes independent queued work and recreates the single-turn failure mode that
  campaign orchestration is meant to avoid.
- When it might be appropriate: a campaign containing exactly one useful queue.

### Supporting Evidence

- `tests/test_campaign.py` proves promotion, decision deferral, external blocking, stop auditing,
  failed validation recording, low-value abandonment, and unknown usage conservative mode.
- Queue B added schema-versioned JSON round trips for active queues, worker turns, validation
  receipts, stop audits, unknown usage, file read/write, and future-field tolerance.
- Queues C-E added manifest ingestion, command validation receipts, and
  `run_autonomous_campaign()` with a scripted worker. Tests prove all-queue completion, dependency
  order, blocked-queue continuation, decision deferral, failed-validation continuation, max-queue
  resumability, and state persistence.
- Queue F added `CodexCliCampaignWorker` and extended `CodexProvider` with explicit cwd, sandbox,
  approval-policy, and ephemeral options. Unit tests prove Codex provider events map into campaign
  outcomes. The opt-in real smoke test proves a campaign can run through the installed Codex CLI.
- Queue G added the `aider-relay campaign` CLI surface with `run`, `resume`, and `status`, plus
  explicit Codex dangerous-bypass plumbing for high-throughput trusted environments.
- Queue H added live campaign telemetry events and `campaign status --watch`.
- Queue I added JSONL event logs, interrupt/pause sentinels, heartbeat/runtime controls,
  clean-worktree guard, checkpoint command hooks, and persisted Codex exhaustion metadata.
- Focused regression validation on 2026-07-05:

```text
python3 -m pytest tests/test_campaign.py tests/test_relay.py tests/test_relay_infrastructure.py -q
68 passed

python3 -m pytest tests/test_campaign.py -q
12 passed

python3 -m pytest tests/test_campaign*.py tests/test_relay.py tests/test_relay_infrastructure.py -q
87 passed

python3 -m pytest tests/test_campaign*.py tests/test_relay.py tests/test_relay_infrastructure.py -q
91 passed, 1 skipped

python3 -m pytest tests/test_campaign*.py tests/test_relay.py tests/test_relay_infrastructure.py -q
100 passed, 1 skipped

python3 -m pytest tests/test_campaign*.py tests/test_relay.py tests/test_relay_infrastructure.py -q
105 passed, 1 skipped

AIDER_RELAY_RUN_CODEX_CLI=1 python3 -m pytest \
  tests/test_campaign_codex_worker.py::test_real_codex_cli_campaign_dry_run -q
1 passed
```

## Known Gaps

- Provider switching is not implemented yet. Codex exhaustion currently maps to an externally blocked
  queue outcome; a future provider pool should retry the same queue with another provider before
  blocking it.
- There is no curses/full-screen UI. The current operator surface is live line-oriented telemetry,
  `campaign status --watch`, and persisted `.aider-relay/campaign.json`.
- Heartbeats and max-runtime controls exist, but provider turns are still single blocking calls; there
  is no concurrent provider-side heartbeat while Codex is inside a long `codex exec` turn.
- Objective monitoring is still validation-command based. There is no independent semantic evaluator
  beyond queue validation receipts.
- Codex exhaustion metadata is persisted in `UsageSnapshot` when available, but there is no wait until
  reset/retry-after-reset policy yet.
- Claude is not integrated into the campaign worker pool yet.

## Anti-Patterns & Examples

### Correct Implementation

The active queue reports `blocked_external`; the scheduler records that queue as blocked and
promotes the next candidate.

### Incorrect Implementation

The active queue reports `blocked_external`; the scheduler stops the whole campaign despite another
decision-independent useful candidate.

Why the anti-pattern fails:

- It confuses local queue state with campaign state.
- It leaves deterministic work undone.

## Verification & Compliance

- Automated tests must prove stop behavior and stop audit content.
- Automated tests must prove campaign JSON read/write round trips before a real campaign runner is
  introduced.
- Automated tests must prove the top-level campaign function with scripted workers before real
  provider adapters are added.
- Real provider smoke tests must be opt-in and must not require committed credentials.
- Code review must check that no provider subprocess, browser scraping, or credential handling is
  introduced outside explicit provider adapters.

## Migration & Exceptions

### Migrating to This Standard

1. Represent planned work as `QueueRecord` objects.
2. Feed worker outcomes into `run_dry_worker_turn`.
3. Inspect `CampaignState.stop_audit` for terminal campaign decisions.
4. Persist state with `CampaignState.write()` and resume with `CampaignState.read()`.
5. Use `run_autonomous_campaign()` for deterministic dry-run campaign execution.

### Exceptions

- None for campaign scheduling. Provider adapters may be added later, but they must feed this state
  machine rather than replace it.

## Applicability Matrix

| Context | Applies | Rationale |
|---------|---------|-----------|
| Campaign dry runs | Yes | This is the initial implementation target |
| Real provider invocation | Later | Providers should feed the scheduler after the dry run is proven |
| ChatGPT analytics scraping | No | Usage analytics discovery is explicitly out of scope for this queue |

## Related Knowledge

- `.kbriefs/KB-2026-021-multi-turn-agentic-routing-protocol.md`
- `.kbriefs/KB-2026-026-mtarp-as-a2a-extension.md`
- `.kbriefs/KB-2026-050-planning-kernel-snapshot-first-standard.md`
- `.kbriefs/KB-2026-052-neutral-spec-context-carry-forward.md`
- `docs/campaigns/run-codex-campaign.md`
