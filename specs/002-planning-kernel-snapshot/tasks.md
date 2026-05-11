# Implementation Tasks: Planning Kernel and Spec Snapshot Integration

## Stage 1: Rebaseline and Design Freeze
- [x] Update `001` spec artifacts to match shipped Phase 1 behavior
- [x] Add a K-Brief for planning-kernel and snapshot-first integration
- [x] Prove current bootstrap with targeted SpecKit tests

## Stage 2: Planning Kernel + SpecKit Snapshot
- [x] Add planning-kernel data structures
- [x] Add SpecKit feature selection and ambiguity handling
- [x] Add deterministic JSON snapshot export
- [x] Add `/speckit snapshot`
- [x] Add snapshot tests for determinism and content mapping

## Stage 3: Relay and MTARP Integration
- [x] Extend `MTARPSession` with framework-neutral spec references
- [x] Add relay CLI support for `--spec`
- [x] Add relay CLI support for `--spec-snapshot`
- [x] Build initial relay prompt from snapshot context
- [x] Add MTARP and relay integration tests

## Stage 4: Verification Hooking
- [x] Carry verification obligations into snapshot output
- [x] Carry unresolved tasks and verification context into relay prompts
- [x] Prove the handoff envelope includes spec context with tests
