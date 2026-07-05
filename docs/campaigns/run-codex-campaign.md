# Tutorial: Run a Codex Campaign

This tutorial walks through running a campaign with `aider-relay` as the
orchestrator and Codex CLI as the worker.

By the end, you will have:

- a campaign manifest
- a persisted campaign state file
- a live event log
- a second terminal watching campaign progress
- a safe way to pause or stop before the next queue

This is a tutorial, not a reference. It follows one working path.

## Prerequisites

Run this from a git repository with `aider-relay` installed from this checkout.

Codex CLI must already be authenticated:

```bash
codex login
```

`aider-relay` does not read, copy, store, or commit Codex credentials. Codex
uses its own local authentication.

For high-throughput local campaigns, use an isolated workspace such as a
devcontainer, disposable VM, or dedicated worktree. The dangerous bypass mode
gives Codex broad local authority.

## 1. Create a campaign manifest

Create `campaign.yaml`:

```yaml
campaign:
  title: First Codex campaign

queues:
  - id: inspect
    title: Inspect the repository
    prompt: |
      Inspect the repository and identify the smallest implementation path.
      Do not edit files in this queue. End with a concise summary.
    validation:
      - python3 -m pytest tests/test_campaign*.py -q

  - id: implement
    title: Implement the change
    depends_on: [inspect]
    prompt: |
      Implement the requested change. Keep the diff focused.
      Run the validation command before stopping.
    validation:
      - python3 -m pytest tests/test_campaign*.py tests/test_relay.py tests/test_relay_infrastructure.py -q

  - id: review
    title: Review and cleanup
    depends_on: [implement]
    prompt: |
      Review the implementation for unrelated edits, missing tests, and obvious regressions.
      Fix only issues directly related to this campaign.
    validation:
      - python3 -m pytest tests/test_campaign*.py tests/test_relay.py tests/test_relay_infrastructure.py -q
```

Queues run in manifest order, except a queue with `depends_on` will not be
promoted until its dependencies are completed.

## 2. Start a watcher terminal

In a second terminal, run:

```bash
aider-relay campaign status \
  --state .aider-relay/campaign.json \
  --watch \
  --interval 5
```

At first it may print that it is waiting for the state file. Leave it running.

## 3. Run the campaign with Codex

For a lower-risk first run, use workspace-write mode:

```bash
aider-relay campaign run \
  --manifest campaign.yaml \
  --worker codex \
  --cwd . \
  --state .aider-relay/campaign.json \
  --event-log .aider-relay/campaign.events.jsonl \
  --max-runtime 8h \
  --heartbeat 5m \
  --interrupt-file .aider-relay/interrupt \
  --pause-file .aider-relay/pause \
  --codex-sandbox workspace-write \
  --codex-approval-policy never
```

For a trusted isolated environment where approval prompts would block useful
throughput, use Codex dangerous bypass mode:

```bash
aider-relay campaign run \
  --manifest campaign.yaml \
  --worker codex \
  --cwd . \
  --state .aider-relay/campaign.json \
  --event-log .aider-relay/campaign.events.jsonl \
  --max-runtime 1d \
  --heartbeat 5m \
  --interrupt-file .aider-relay/interrupt \
  --pause-file .aider-relay/pause \
  --codex-dangerously-bypass-approvals-and-sandbox
```

Only use dangerous bypass inside an externally isolated environment.

## 4. Watch progress

The run terminal and watch terminal show events such as:

```text
[CAMPAIGN] ... queue.started queue=implement | started queue implement
[CAMPAIGN] ... provider.started provider=codex | codex cli started
[CAMPAIGN] ... provider.text provider=codex | ...
[CAMPAIGN] ... validation.command.started queue=implement | started validation command: ...
[CAMPAIGN] ... validation.passed queue=implement | validation passed for queue implement
[CAMPAIGN] ... queue.completed queue=implement provider=codex | queue implement -> completed
```

The mutable state lives in:

```text
.aider-relay/campaign.json
```

The append-only event log lives in:

```text
.aider-relay/campaign.events.jsonl
```

Both are ignored by git.

## 5. Pause or stop safely

Pause before the next queue:

```bash
touch .aider-relay/pause
```

Resume:

```bash
rm .aider-relay/pause
```

Stop gracefully before the next queue:

```bash
touch .aider-relay/interrupt
```

The active Codex turn is not killed mid-turn by these files. The orchestrator
checks them between queues and while paused.

## 6. Resume a campaign

If the process exits or you stop after a queue, resume from state:

```bash
aider-relay campaign resume \
  --state .aider-relay/campaign.json \
  --worker codex \
  --cwd . \
  --event-log .aider-relay/campaign.events.jsonl \
  --max-runtime 8h \
  --heartbeat 5m \
  --codex-dangerously-bypass-approvals-and-sandbox
```

## 7. Add checkpoint commits

For long-running work, checkpoint after each queue:

```bash
aider-relay campaign run \
  --manifest campaign.yaml \
  --worker codex \
  --cwd . \
  --checkpoint-command 'git add -A && git commit -m "campaign checkpoint: {queue_id}"' \
  --codex-dangerously-bypass-approvals-and-sandbox
```

Use checkpoint commits only when your manifest validation is strong enough that
each completed queue is worth preserving.

## 8. Inspect final state

Print a summary:

```bash
aider-relay campaign status --state .aider-relay/campaign.json
```

Look for:

- completed queues
- failed validation queues
- deferred decision queues
- blocked external queues
- final stop reason

## Known limits

- Provider switching is not implemented yet.
- Codex reset timing may be persisted when reported, but there is no
  wait-until-reset policy yet.
- The UI is line-oriented telemetry, not a full-screen dashboard.
- Pause and interrupt are checked between queues, not inside a running Codex
  turn.
- Objective monitoring depends on validation commands in the manifest.
