---
id: KB-2026-057
type: standard
status: validated
created: 2026-05-11
updated: 2026-05-11
tags: [openspec, planning-kernel, adapter, brownfield, spec-driven, relay]
related: [KB-2026-048, KB-2026-050, KB-2026-051, KB-2026-052, KB-2026-056]
---

# OpenSpec Change Adapter Standard

## Context & Problem Statement

The planning kernel already supports Spec Kit snapshots. The next architectural step is to prove
framework optionality with a second adapter. OpenSpec is the strongest comparison point because
it is brownfield-first and organized around change proposals rather than a single staged feature
directory.

The critical question is what planning unit `aider-relay` should consume from OpenSpec.

## Standard/Pattern Description

### Core Principles

- Treat `openspec/changes/<change>/` as the planning unit.
- Treat the change shell as real state even when only some artifacts exist.
- Read requirements from change-local spec deltas under `openspec/changes/<change>/specs/**/spec.md`.
- Include baseline capability specs from `openspec/specs/<capability>/spec.md` when a delta touches
  an existing capability.
- Preserve the planning kernel shape rather than exposing OpenSpec-native structures directly in
  MTARP or relay prompts.

### Implementation

The adapter should read these artifacts when they exist:

```text
openspec/changes/<change>/.openspec.yaml
openspec/changes/<change>/proposal.md
openspec/changes/<change>/design.md
openspec/changes/<change>/tasks.md
openspec/changes/<change>/specs/<capability>/spec.md
openspec/specs/<capability>/spec.md
```

Mapping rules:

- `feature_id` = OpenSpec change id (for example `add-openspec-adapter`)
- `feature_root` = `openspec/changes/<change>`
- `summary` = `proposal.md` `## Why` section when present
- `requirements` = `### Requirement:` blocks from delta specs
- `verification_obligations` = `#### Scenario:` blocks from delta specs
- `tasks` = checkbox tasks from `tasks.md`
- `plan_phases` = `##` sections from `tasks.md`, or `design.md` if tasks do not exist
- `artifact_refs` = change shell metadata, proposal/design/tasks, delta specs, and matching
  baseline specs

### Key Rules

- Rule 1: Require an explicit change when multiple active change directories exist.
- Rule 2: Allow proposal-only changes to snapshot successfully, even with empty requirements/tasks.
- Rule 3: Do not assume an OpenSpec active-change pointer file exists.
- Rule 4: Keep OpenSpec-specific paths inside artifact references, not inside MTARP protocol keys.
- Rule 5: Scenarios are the primary verification surface for OpenSpec consumption.

## Rationale & Benefits

- Matches OpenSpec's change-centered workflow instead of forcing it into a feature-centered shape.
- Preserves optionality: relay and MTARP continue to operate on framework-neutral planning context.
- Supports brownfield work where the proposed change matters more than a greenfield feature shell.

## Alternatives & Evidence

### Alternative 1

- Description: Treat `openspec/specs/<capability>/spec.md` as the primary planning unit.
- Why not chosen: That loses the active change proposal, design, and tasks that make OpenSpec
  useful for execution.

### Alternative 2

- Description: Require proposal, design, tasks, and delta specs before allowing a snapshot.
- Why not chosen: OpenSpec is intentionally fluid; a hard gate would fight the framework.

### Supporting Evidence

Empirical probes in the devcontainer against OpenSpec `1.3.1`:

```bash
npx -y @fission-ai/openspec@1.3.1 init --tools codex
npx -y @fission-ai/openspec@1.3.1 new change add-openspec-adapter
npx -y @fission-ai/openspec@1.3.1 instructions proposal --change add-openspec-adapter --json
npx -y @fission-ai/openspec@1.3.1 instructions specs --change add-openspec-adapter --json
npx -y @fission-ai/openspec@1.3.1 instructions tasks --change add-openspec-adapter --json
```

Observed behavior:

- `init` installs Codex skills and commands but does not create planning artifacts.
- `new change` creates the change shell and `.openspec.yaml`.
- Proposal/spec/design/tasks content is produced by the workflow instructions, not by the shell
  creation command itself.

## Anti-Patterns & Examples

### Correct Implementation

```text
OpenSpec change directory
       ↓
OpenSpecAdapter
       ↓
PlanningSnapshot
       ↓
relay prompt / MTARP spec_context
```

### Incorrect Implementation (Anti-pattern)

```text
Parse only openspec/specs/ and ignore changes/
```

Why the anti-pattern fails:

- drops proposal intent
- drops design and task context
- loses the brownfield change lens that makes OpenSpec useful

## Verification & Compliance

- build snapshots from a populated OpenSpec change fixture
- confirm proposal-only changes still snapshot
- confirm scenario obligations appear in planning context
- run `task dc:smoke:openspec`

## Migration & Exceptions

### Migrating to This Standard

1. Initialize OpenSpec in a project.
2. Create a change shell.
3. Materialize proposal/spec/design/tasks through the OpenSpec workflow.
4. Consume the change with `OpenSpecAdapter` or `--openspec-change`.

### Exceptions

- Exception 1: Proposal-only snapshots are allowed for early planning.
- Exception 2: Baseline spec refs may be absent for truly new capabilities.

## Applicability Matrix

| Context | Applies | Rationale |
|---------|---------|-----------|
| Brownfield change planning | Yes | OpenSpec is change-centered |
| Greenfield staged feature flow | Sometimes | Spec Kit remains stronger there |
| Relay prompt injection | Yes | The kernel output remains neutral |
| MTARP schema design | Yes | Context keys stay framework-agnostic |

## Related Knowledge

- [KB-2026-048](C:/Users/chris/Dev/aider-relay/.kbriefs/KB-2026-048-spec-framework-optionality-and-agentic-se-architecture.md)
- [KB-2026-050](C:/Users/chris/Dev/aider-relay/.kbriefs/KB-2026-050-planning-kernel-snapshot-first-standard.md)
- [KB-2026-051](C:/Users/chris/Dev/aider-relay/.kbriefs/KB-2026-051-deterministic-spec-snapshot-validation.md)
- [KB-2026-052](C:/Users/chris/Dev/aider-relay/.kbriefs/KB-2026-052-neutral-spec-context-carry-forward.md)
- [KB-2026-056](C:/Users/chris/Dev/aider-relay/.kbriefs/KB-2026-056-upstream-specify-cli-consumption-bridge.md)
