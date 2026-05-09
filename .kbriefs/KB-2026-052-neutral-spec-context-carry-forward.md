---
id: KB-2026-052
type: standard
status: validated
created: 2026-05-09
updated: 2026-05-09
tags: [mtarp, relay, spec-driven, handoff, planning-kernel, verification, testing]
related: [KB-2026-048, KB-2026-050, KB-2026-051]
---

# Neutral Spec Context Carry-Forward

## Context & Problem Statement

The planning-kernel and SpecKit snapshot work proved that checked-in planning artifacts can be
normalized into deterministic JSON. The next question was how much of that structure should travel
through MTARP and relay prompts during provider handoff.

The main risks were:

- embedding SpecKit file semantics directly into MTARP
- forcing downstream providers to re-parse raw markdown after every handoff
- dropping unresolved tasks and verification obligations at the exact point where context fidelity
  matters most

## Standard/Pattern Description

### Core Principles

- Carry forward a compact neutral `spec_context`, not a full framework-native snapshot.
- Preserve execution-driving context explicitly: change identity, artifact refs, unresolved tasks,
  and verification obligations.
- Enrich relay prompts only when planning context is supplied, so legacy relay behavior stays
  unchanged.

### Implementation

The validated MTARP carry-forward shape is:

- `spec_framework`
- `change_id`
- `feature`
- `capability_summary`
- `artifact_refs`
- `execution_context_pack`
- `verification_refs`
- `trace_refs`

This compact structure is derived from `PlanningSnapshot.to_spec_context()` and stored in
`MTARPSession.spec_context`.

### Key Rules

- Rule 1: MTARP stores neutral planning references and execution context, not raw SpecKit sections.
- Rule 2: Relay initial prompts include planning context only when a snapshot is supplied.
- Rule 3: Handoff prompts must preserve unresolved tasks and pending verification obligations.
- Rule 4: CLI loading must support both `--spec <feature>` and `--spec-snapshot <file>`.

## Rationale & Benefits

- The protocol stays open for future OpenSpec and BMad adapters.
- Providers receive structured intent without repeating markdown parsing at each switch.
- Existing relay flows remain backward compatible because the no-snapshot path is unchanged.

## Alternatives & Evidence

### Alternative 1

Store the full planning snapshot inside `session.json`.

- Why not chosen:
  - duplicates large amounts of data already available in the repo or snapshot file
  - couples MTARP more tightly to the first adapter schema than needed

### Alternative 2

Store only artifact paths and require prompt-time re-parsing.

- Why not chosen:
  - reintroduces parsing ambiguity at every handoff
  - loses the proof that unresolved tasks and verification context were actually preserved

### Supporting Evidence

Validated on 2026-05-09:

```text
task dc:exec -- bash -lc '.venv/bin/python -m pytest tests/test_relay_spec_context.py -q'
7 passed in 20.03s

task dc:exec -- bash -lc '.venv/bin/python -m pytest tests/test_mtarp_session.py tests/test_relay.py tests/test_phase2_session_fields.py tests/test_repomap_handoff.py tests/test_relay_infrastructure.py -q'
130 passed in 229.47s

task dc:exec -- task lint
isort Passed
black Passed
flake8 Passed
codespell Passed

task dc:exec -- task test
670 passed, 1 skipped, 67 subtests passed in 408.02s
```

The tests prove:

- planning snapshots export a compact neutral carry-forward structure
- MTARP round-trips that structure through `session.json`
- relay initial prompts include unresolved tasks and verification obligations when snapshot context
  is supplied
- fallback handoff prompts preserve the same planning context
- relay CLI accepts both checked-in feature specs and prebuilt snapshot files

## Anti-Patterns & Examples

### Correct Implementation

- Convert planning artifacts once into a neutral context object before relay execution starts.
- Preserve the same context in both the session envelope and the fallback prompt.

### Incorrect Implementation (Anti-pattern)

- Serialize raw framework markdown into MTARP and expect each provider to interpret it.
- Build initial prompts from planning context but drop it from the handoff envelope.

Why the anti-pattern fails:

- breaks protocol neutrality
- creates context drift between the initial session and the resumed session

## Verification & Compliance

- Targeted spec-context relay tests
- Existing relay/session regression suite
- Full repo lint and test gates after integration

## Migration & Exceptions

### Migrating to This Standard

1. Normalize framework artifacts into `PlanningSnapshot`.
2. Derive `spec_context` from the snapshot.
3. Pass that context into MTARP and relay prompt construction.

### Exceptions

- None for snapshot-backed relay flows. If planning context is supplied, it must survive both
  `session.json` and fallback prompting.

## Applicability Matrix

| Context | Applies | Rationale |
|---------|---------|-----------|
| SpecKit-backed relay runs | Yes | Current validated path |
| Future OpenSpec adapter | Yes | Neutral context keys are framework-independent |
| Future BMad adapter | Yes | Relay consumes normalized context, not workflow-specific commands |
| Legacy relay runs without planning artifacts | Yes | Behavior remains unchanged because enrichment is opt-in |

## Related Knowledge

- KB-2026-048
- KB-2026-050
- KB-2026-051
- `aider/planning.py`
- `aider/relay/session.py`
- `aider/relay/loop.py`
