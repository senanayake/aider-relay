# Implementation Plan: Planning Kernel and Spec Snapshot Integration

## Design Standard

This phase follows the architecture direction captured in:

- `.specify/memory/constitution.md`
- `.kbriefs/KB-2026-048-spec-framework-optionality-and-agentic-se-architecture.md`

The core rule is:

1. keep MTARP methodology-neutral
2. add a minimal planning kernel
3. implement SpecKit as an adapter, not as the protocol

## Incremental Stages

### Stage 1: Rebaseline and Design Freeze
- update stale `001` artifacts to match shipped Phase 1 behavior
- define the minimal planning-kernel schema
- capture the design standard in a K-Brief
- prove the current bootstrap with targeted tests

### Stage 2: Planning Kernel + SpecKit Snapshot
- implement the canonical planning-kernel data structures
- implement a `SpecKitAdapter` that maps current repo artifacts into the kernel
- add deterministic JSON snapshot export
- add `/speckit snapshot`
- prove determinism and ambiguity handling with tests

### Stage 3: Relay and MTARP Integration
- extend `MTARPSession` with framework-neutral spec references
- add `--spec` and `--spec-snapshot` to relay
- build the initial relay prompt from snapshot content
- prove session serialization and relay behavior with tests

### Stage 4: Verification Hooking
- make verification obligations visible in snapshot and relay context
- ensure unresolved work is carried into handoff prompts and session envelopes
- validate the resulting context with integration tests

## Success Criteria

- planning artifacts are operational input to relay runs
- MTARP remains neutral to external framework layout
- the design is proven incrementally with automated tests before each next stage
