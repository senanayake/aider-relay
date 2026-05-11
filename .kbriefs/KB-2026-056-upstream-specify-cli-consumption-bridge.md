---
id: KB-2026-056
type: standard
status: validated
created: 2026-05-10
updated: 2026-05-10
tags: [speckit, specify-cli, integration, devcontainer, planning-kernel, minimal-wrap]
related: [KB-2026-048, KB-2026-050, KB-2026-051, KB-2026-052]
---

# Upstream Specify CLI Consumption Bridge

## Context & Problem Statement

This repo already implements a framework-neutral planning kernel plus a thin SpecKit-compatible
surface. The open decision was whether to continue toward full native Spec Kit command parity or
to integrate the real upstream `specify-cli` and consume its artifacts inside `aider-relay`.

The correct direction is the second one. The goal is not to recreate Spec Kit inside this fork.
The goal is to let upstream Spec Kit remain the producer of spec-driven artifacts while
`aider-relay` consumes those artifacts for relay execution and MTARP carry-forward.

## Standard/Pattern Description

### Core Principles

- Use upstream `specify-cli` for project initialization and Spec Kit command installation.
- Keep `aider-relay` focused on consuming `.specify/...` and feature artifacts, not generating
  them.
- Expose upstream `specify-cli` through thin pinned wrappers in the devcontainer rather than
  vendoring or forking its command surface.
- Follow the staged lifecycle of upstream Spec Kit: `spec.md` first, `plan.md` next, `tasks.md`
  later.
- Treat `.specify/feature.json` as the canonical pointer to the current feature when present.

### Implementation

The compatibility layer in [aider/speckit.py](C:/Users/chris/Dev/aider-relay/aider/speckit.py)
should support these upstream conventions:

```text
.specify/feature.json              # current feature pointer
.specify/memory/constitution.md    # governance
specs/<feature>/spec.md            # required
specs/<feature>/plan.md            # optional early, expected after planning
specs/<feature>/tasks.md           # optional until task generation
specs/<feature>/research.md        # optional supporting artifact
specs/<feature>/data-model.md      # optional supporting artifact
specs/<feature>/quickstart.md      # optional supporting artifact
specs/<feature>/contracts/*        # optional supporting artifacts
```

When consuming upstream default templates:

- derive summary from `## Overview` when present
- otherwise derive it from the first user story description
- parse `FR-*` requirements from the default requirements section
- treat `SC-*` success criteria as verification obligations
- treat `**Independent Test**:` lines as verification obligations
- allow `tasks.md` to be absent without failing snapshot generation

### Key Rules

- Rule 1: Do not reimplement `/speckit.specify`, `/speckit.plan`, or `/speckit.tasks`.
- Rule 2: Use upstream `specify init` to install Codex skills and shared Spec Kit structure.
- Rule 2a: Invoke upstream `specify-cli` via pinned `uvx` wrappers such as `task specify -- ...`
  and `task dc:specify -- ...`.
- Rule 3: Prefer consuming `feature.json` over guessing the active feature from branch naming.
- Rule 4: Support partial feature states so relay consumption works before every artifact exists.
- Rule 5: Include optional design artifacts as traceable references when they exist.

## Rationale & Benefits

Why should this standard be followed?

- It avoids building and maintaining a second Spec Kit implementation.
- It preserves compatibility with upstream templates, integrations, and future extensions.
- It keeps `aider-relay` aligned with KBPD and Gall's Law: consume proven upstream outputs,
  add only the minimal bridge required for relay usage.

## Alternatives & Evidence

What other approaches were evaluated?

### Alternative 1

- Description: Continue implementing local `/speckit.*` command parity.
- Why not chosen: High maintenance cost and inevitable drift from upstream Spec Kit.
- When it might be appropriate: Only if upstream Spec Kit becomes unavailable or structurally
  incompatible with relay consumption.

### Alternative 2

- Description: Consume only the current repo's custom spec shape.
- Why not chosen: Locks the repo to a non-upstream artifact contract and weakens interoperability.
- When it might be appropriate: As a temporary bootstrap layer during early experimentation.

### Supporting Evidence

Empirical upstream validation was run inside the devcontainer using:

```bash
uvx --from git+https://github.com/github/spec-kit.git@v0.8.7 specify init . --integration codex --script sh
```

Observed output:

- installs Codex skills under `.agents/skills/speckit-*`
- installs shared templates and scripts under `.specify/`
- creates `.specify/feature.json` as the active-feature pointer
- installs a bundled `speckit` workflow

Observed artifact lifecycle:

- `create-new-feature.sh` creates `specs/<feature>/spec.md` and returns `SPEC_FILE`
- the higher-level Spec Kit command/skill flow is responsible for persisting
  `.specify/feature.json`
- `setup-plan.sh` creates `plan.md`
- `setup-tasks.sh` requires `spec.md` and `plan.md`, and prepares `tasks.md`

This proves the bridge can be thin: consume upstream state rather than replacing it. It also
clarifies that the bridge should key off the persisted artifact contract (`feature.json` plus
feature docs), not assume every helper shell script writes the active-feature pointer by itself.

## Anti-Patterns & Examples

### Correct Implementation

```text
upstream specify-cli produces artifacts
          ↓
aider-relay reads .specify/feature.json + feature docs
          ↓
planning snapshot / relay prompt / MTARP state
```

### Incorrect Implementation (Anti-pattern)

```text
Rebuild full Spec Kit command lifecycle inside aider-relay
```

Why the anti-pattern fails:

- duplicates upstream functionality
- creates command and template drift
- increases maintenance cost without improving relay execution

## Verification & Compliance

How to verify adherence to this standard:

- run upstream `specify init` in a temp project and inspect installed files
- run adapter tests against upstream-style fixtures
- confirm snapshots build when `tasks.md` is absent
- confirm `.specify/feature.json` selects the active feature when multiple features exist
- run `task dc:smoke:specify` to prove real upstream init/scaffold and local consumption interlock

## Migration & Exceptions

### Migrating to This Standard

1. Use upstream `specify-cli` in the devcontainer.
2. Expose it through thin wrapper tasks instead of adding new local command logic.
3. Keep local code limited to artifact consumption and relay integration.
4. Expand adapter compatibility only when upstream artifacts require it.

### Exceptions

When is it OK to deviate from this standard?

- Exception 1: temporary local fixtures may be used in tests to model upstream templates.
- Exception 2: a minimal wrapper task or smoke command is acceptable if it only invokes upstream
  Spec Kit and does not replace it.

## Applicability Matrix

| Context | Applies | Rationale |
|---------|---------|-----------|
| Spec artifact production | Yes | Upstream Spec Kit should remain authoritative |
| Relay planning-context consumption | Yes | This repo's planning kernel is the consumer side |
| Full local command parity | No | Explicitly outside the chosen integration strategy |
| Temporary compatibility shims | Sometimes | Allowed only when they reduce friction without replacing upstream |

## Related Knowledge

- [KB-2026-048](C:/Users/chris/Dev/aider-relay/.kbriefs/KB-2026-048-spec-framework-optionality-and-agentic-se-architecture.md)
- [KB-2026-050](C:/Users/chris/Dev/aider-relay/.kbriefs/KB-2026-050-planning-kernel-snapshot-first-standard.md)
- [KB-2026-051](C:/Users/chris/Dev/aider-relay/.kbriefs/KB-2026-051-deterministic-spec-snapshot-validation.md)
- [KB-2026-052](C:/Users/chris/Dev/aider-relay/.kbriefs/KB-2026-052-neutral-spec-context-carry-forward.md)
