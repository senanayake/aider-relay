---
id: KB-2026-050
type: standard
status: validated
created: 2026-05-09
updated: 2026-05-09
tags: [spec-driven, architecture, planning-kernel, speckit, mtarp, relay, optionality]
related: [KB-2026-048, KB-2026-049]
---

# Planning Kernel and Snapshot-First Spec Integration Standard

## Context & Problem Statement

aider-relay already has a shipped read-only SpecKit bootstrap and an existing MTARP handoff
envelope. The next design choice is whether to:

- add more framework-native commands directly
- couple MTARP to SpecKit artifact paths
- or insert a minimal neutral layer between planning artifacts and relay execution

The project also wants to preserve optionality for OpenSpec and BMad later.

## Standard/Pattern Description

### Core Principles

- Treat spec artifacts as intent, not execution state.
- Keep MTARP framework-neutral.
- Add a small internal planning kernel before adding more framework-native commands.
- Export deterministic snapshots before attempting spec generation or mutation.

### Implementation

The recommended sequence is:

1. Keep the shipped Phase 1 discovery/status bootstrap as read-only.
2. Add a minimal planning kernel.
3. Implement `SpecKitAdapter` as the first adapter.
4. Export deterministic snapshots from adapter output.
5. Feed those snapshots into relay and MTARP using neutral references.

### Key Rules

- Rule 1: Do not encode SpecKit file layout as MTARP protocol semantics.
- Rule 2: Do not add `/speckit.plan` or `/speckit.implement` before deterministic snapshot export.
- Rule 3: Prove each stage with automated tests before moving to the next stage.

## Rationale & Benefits

- Preserves future compatibility with OpenSpec and BMad.
- Keeps execution and protocol layers stable while planning frameworks evolve.
- Creates a testable seam between raw files and relay prompts.
- Reduces risk of prematurely locking the repo into one tool's lifecycle.

## Alternatives & Evidence

### Alternative 1

Add more SpecKit-native commands immediately.

- Why not chosen:
  - increases coupling to one framework
  - violates the repo constitution's read-only-first rule
  - skips the neutral layer recommended by KB-2026-048

### Alternative 2

Embed SpecKit paths and semantics directly into MTARP.

- Why not chosen:
  - makes the protocol harder to evolve
  - collapses intent representation and execution state

### Supporting Evidence

- `tests/test_speckit.py` proves the Phase 1 read-only bootstrap is already operational.
- KB-2026-048 identifies canonical-core-plus-adapters as the preferred architecture.
- The constitution explicitly requires read-only discovery before generation or implementation.

## Anti-Patterns & Examples

### Correct Implementation

- `SpecKit -> PlanningKernel -> Snapshot -> Relay/MTARP`

### Incorrect Implementation (Anti-pattern)

- `SpecKit paths -> MTARP schema`
- `/speckit.plan` added before snapshot export exists`

Why the anti-pattern fails:
- hard-codes one framework into the execution protocol
- reduces flexibility for brownfield and multi-framework evolution

## Verification & Compliance

- Code review check: new protocol fields must remain framework-neutral
- Automated tests: snapshot determinism, ambiguity handling, relay integration
- Manual check: no LLM is required for snapshot export

## Migration & Exceptions

### Migrating to This Standard

1. Rebaseline shipped bootstrap specs
2. Introduce the kernel and snapshot export
3. Extend relay and MTARP to consume the snapshot

### Exceptions

- A framework-native command is acceptable only if it delegates through the planning kernel
  instead of bypassing it.

## Applicability Matrix

| Context | Applies | Rationale |
|---------|---------|-----------|
| Current SpecKit bootstrap | Yes | This is the immediate next layer |
| MTARP schema evolution | Yes | Neutral references are required |
| OpenSpec/BMad future support | Yes | The kernel preserves optionality |
| Direct spec generation | No | Too early before snapshot export |

## Related Knowledge

- KB-2026-048
- `.specify/memory/constitution.md`
- `specs/002-planning-kernel-snapshot/`
