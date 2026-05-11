---
id: KB-2026-051
type: standard
status: validated
created: 2026-05-09
updated: 2026-05-09
tags: [spec-driven, planning-kernel, snapshot, determinism, speckit, testing]
related: [KB-2026-050, KB-2026-048]
---

# Deterministic Spec Snapshot Validation

## Context & Problem Statement

After adopting the planning-kernel and snapshot-first standard, the next question was whether a
small neutral schema was enough to make checked-in SpecKit artifacts operational for relay use.

The concrete risks were:

- the snapshot might still be too SpecKit-specific
- output might not be deterministic across repeated runs
- unresolved tasks and verification context might be lost during export

## Standard/Pattern Description

### Core Principles

- Use a minimal kernel, not a full framework clone.
- Export JSON deterministically from checked-in artifacts.
- Preserve unresolved work and verification obligations explicitly.
- Fail fast when feature selection is ambiguous.

### Implementation

The validated minimal snapshot shape includes:

- `feature`
- `artifact_refs`
- `capability_spec`
- `implementation_plan`
- `task_graph`
- `execution_context_pack`
- `verification_obligations`
- `trace_links`

### Key Rules

- Rule 1: Repeated snapshot generation over unchanged files must produce identical JSON.
- Rule 2: Multiple feature directories must require explicit selection.
- Rule 3: The execution context must carry unresolved tasks by value, not only by reference.

## Rationale & Benefits

- The schema is small enough to adapt later to OpenSpec and BMad.
- Artifact hashes provide stable references without embedding framework semantics in MTARP.
- Relay can consume structured intent instead of reconstructing it from raw markdown later.

## Alternatives & Evidence

### Alternative 1

Export raw markdown files only.

- Why not chosen:
  - pushes parsing ambiguity downstream into relay
  - does not create a stable execution boundary

### Alternative 2

Export a much richer schema immediately.

- Why not chosen:
  - increases design burden before the adapter seam is proven
  - risks overfitting the first framework

### Supporting Evidence

Validated on 2026-05-09:

```text
task dc:exec -- bash -lc '.venv/bin/python -m pytest tests/test_planning.py tests/test_speckit.py -q'
27 passed in 2.63s

task dc:exec -- task lint
isort Passed
black Passed
flake8 Passed
codespell Passed
```

The tests prove:

- single-feature default selection works
- multi-feature ambiguity produces a hard error
- snapshot output is deterministic across repeated builds
- unresolved tasks and acceptance criteria survive export
- `/speckit snapshot` is available through aider command handling

## Anti-Patterns & Examples

### Correct Implementation

- Parse checked-in planning artifacts once into a normalized snapshot.
- Feed unresolved tasks and verification obligations forward explicitly.

### Incorrect Implementation (Anti-pattern)

- Defer all interpretation to relay from raw markdown.
- Infer a feature silently when multiple spec directories exist.

Why the anti-pattern fails:

- creates non-deterministic downstream behavior
- makes the operator guess which feature was actually executed

## Verification & Compliance

- Automated tests for determinism and ambiguity handling
- Automated tests for command integration
- Repo lint gate via pre-commit

## Migration & Exceptions

### Migrating to This Standard

1. Parse framework-native artifacts into the kernel.
2. Export deterministic snapshots.
3. Extend relay and MTARP to consume the snapshot.

### Exceptions

- None in the current architecture phase. Ambiguous feature selection must remain an error.

## Applicability Matrix

| Context | Applies | Rationale |
|---------|---------|-----------|
| SpecKit adapter | Yes | This is the validated first adapter |
| Relay integration | Yes | Snapshot is now safe to consume |
| Future OpenSpec/BMad adapters | Yes | The kernel shape is intentionally neutral |
| Direct protocol serialization from raw markdown | No | Not deterministic enough |

## Related Knowledge

- KB-2026-050
- `aider/planning.py`
- `aider/speckit.py`
- `tests/test_planning.py`
