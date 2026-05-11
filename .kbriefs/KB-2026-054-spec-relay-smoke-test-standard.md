---
id: KB-2026-054
type: standard
status: draft
created: 2026-05-10
updated: 2026-05-10
tags: [testing, speckit, relay, devcontainer, kbpd]
related: [KB-2026-008, KB-2026-051, KB-2026-052, KB-2026-053]
---

# SpecKit and Relay Smoke Test Standard

## Context & Problem Statement

The planning-kernel and SpecKit work added new user-facing entrypoints in two places:
real `/speckit` commands inside aider, and relay startup via spec-derived planning
context. Unit tests prove the pieces independently, but maintainers also need one
small deterministic command that demonstrates the integrated path from repository
artifacts to relay prompt construction.

A live provider session is the wrong standard for this check. It adds account state,
authentication, and usage-window variability to a test whose purpose is local proof of
integration.

## Standard/Pattern Description

### Core Principles

- Exercise the real CLI surface for `/speckit` commands.
- Keep the smoke test offline and deterministic.
- Prove relay planning-context injection without requiring provider credentials.
- Run the canonical version inside the devcontainer, not against the host `.venv`.
- Use checked-in repo artifacts for status and snapshot checks, but allow a temporary
  sample feature for unresolved-task proof when the checked-in specs are already complete.

### Implementation

Implement two Task targets:

```yaml
smoke:speckit:
  # run inside devcontainer

dc:smoke:speckit:
  # host wrapper that executes the smoke task in-container
```

The smoke task should perform three checks in order:

1. Run `/speckit status` through `aider.main`.
2. Run `/speckit snapshot <feature> <tmpfile>` and parse the JSON summary.
3. Run one mocked relay turn with a `PlanningSnapshot` and assert the prompt contains
   planning context, an unresolved task, and a verification obligation.

Implementation detail discovered during execution:

- Multiline shell steps that embed heredocs must use YAML literal blocks (`|`), not folded
  scalars (`>-`), or the Python script will collapse into invalid one-line input.

### Key Rules

- Rule 1: Use `aider.main` for SpecKit command smoke checks so command parsing and repo
  discovery are exercised together.
- Rule 2: Use a temporary snapshot file and print a compact summary line that humans can
  inspect quickly.
- Rule 3: Use mocked providers for the relay segment so the smoke test validates local
  architecture rather than external provider availability.
- Rule 4: Provide a `dc:` wrapper so the supported invocation path is obvious to users.
- Rule 5: Parse the published snapshot schema (`feature`, `task_graph`, `spec_framework`),
  not internal adapter attribute names.

## Rationale & Benefits

Why should this standard be followed?

- It gives a fast integration proof without spending provider quota.
- It isolates failures to repo logic instead of auth or service state.
- It makes the current SpecKit-compatible slice demonstrable to contributors.

## Alternatives & Evidence

What other approaches were evaluated?

### Alternative 1

- Description: Only rely on pytest coverage.
- Why not chosen: It does not give contributors a single human-runnable integrated check.
- When it might be appropriate: For low-level refactors that do not change entrypoints.

### Alternative 2

- Description: Use real Claude/Codex CLI sessions in the smoke test.
- Why not chosen: Results would depend on credentials, quota state, and provider latency.
- When it might be appropriate: Manual acceptance testing before a release.

### Supporting Evidence

- Existing unit coverage already proves snapshot determinism and relay integration.
- The smoke task reuses those validated seams while keeping runtime dependencies local.
- Initial attempts using folded YAML scalars broke the heredoc-based Python snippets with a
  `SyntaxError`; switching to literal blocks fixed the issue.
- Initial attempts using `002-planning-kernel-snapshot` for unresolved-task assertions failed
  because all checked-in specs were complete; a temporary sample feature restored a stable
  proof for planning-context injection.

## Anti-Patterns & Examples

### Correct Implementation

```text
task dc:smoke:speckit
```

This runs the real SpecKit command surface and a mocked relay proof entirely inside the
container-managed environment.

### Incorrect Implementation (Anti-pattern)

```text
Taskfile command written with a folded YAML scalar around a heredoc shell script
```

Why the anti-pattern fails:
- It collapses multiline Python into invalid one-line input.
- It hides the actual shell boundary bugs until runtime.

### Incorrect Implementation (Anti-pattern)

```text
python -m aider.relay.loop --spec ...
```

when executed directly on the Windows host against the container-created `.venv`.

Why the anti-pattern fails:
- It bypasses the supported environment boundary.
- It can reintroduce host/container drift that earlier work explicitly removed.

## Verification & Compliance

How to verify adherence to this standard:

- Run `task dc:smoke:speckit`.
- Confirm the output includes a SpecKit status report, a `SMOKE SNAPSHOT:` line, and a
  `SMOKE RELAY:` line with all checks set to `yes`.
- Keep `task dc:exec -- task lint` and `task dc:exec -- task test` green.

## Migration & Exceptions

### Migrating to This Standard

1. Add or update the smoke task in `Taskfile.yml`.
2. Keep the smoke path devcontainer-first.
3. Extend the mocked relay assertions when new planning-context fields become required.

### Exceptions

When is it OK to deviate from this standard?

- Exception 1: A release rehearsal may add a separate manual run against real providers.
- Exception 2: If relay semantics change to require provider-specific behavior, add a new
  higher-cost acceptance test instead of weakening the smoke test.

## Applicability Matrix

| Context | Applies | Rationale |
|---------|---------|-----------|
| Local contributor verification | Yes | Fast deterministic proof of current integrated behavior |
| CI smoke validation | Yes | No external credentials required |
| Provider quota or auth validation | No | Needs a separate live-provider test path |
| Deep relay behavior debugging | Sometimes | Use this first, then escalate to targeted tests |

## Related Knowledge

- [KB-2026-008](.kbriefs/KB-2026-008-devcontainer-environment.md)
- [KB-2026-051](.kbriefs/KB-2026-051-deterministic-spec-snapshot-validation.md)
- [KB-2026-052](.kbriefs/KB-2026-052-neutral-spec-context-carry-forward.md)
- [KB-2026-053](.kbriefs/KB-2026-053-repo-local-spec-discovery-boundary.md)
