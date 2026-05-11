# Planning Kernel and Spec Snapshot Integration

## Overview

Add a framework-neutral planning kernel and a deterministic SpecKit snapshot path so
spec-driven artifacts can become operational input to relay execution without coupling
MTARP to one framework's file layout.

## User Stories

### As a developer using SpecKit-style artifacts
- I want to export one feature into a deterministic execution snapshot
- I want the snapshot to include unresolved tasks and verification obligations
- I want clear feature-selection behavior when multiple specs exist

### As a relay user
- I want to start a relay run from a feature spec or snapshot file
- I want MTARP handoff state to reference the spec context in a framework-neutral way
- I want the relay prompt to carry structured intent, not just raw free text

### As a project maintainer
- I want the internal schema to preserve optionality for OpenSpec and BMad later
- I want spec snapshots to remain deterministic and offline
- I want empirical tests that prove schema stability and relay integration

## Functional Requirements

### Planning Kernel
- **FR-001**: Define a framework-neutral internal representation for planning artifacts
- **FR-002**: Represent a feature's capability spec, implementation plan, task graph,
  verification obligations, and trace references
- **FR-003**: Keep the initial kernel small enough to map cleanly from current SpecKit artifacts

### SpecKit Adapter
- **FR-004**: Select one feature from `specs/<feature>/...`
- **FR-005**: If multiple features exist and none is specified, return a clear error
- **FR-006**: Export a deterministic JSON snapshot for the selected feature
- **FR-007**: Include constitution/spec/plan/tasks artifact references in the snapshot
- **FR-008**: Include unresolved tasks and acceptance/verification obligations in the snapshot

### Command Integration
- **FR-009**: Implement `/speckit snapshot` in aider
- **FR-010**: Allow writing the snapshot to a file or displaying it through aider IO

### Relay and MTARP Integration
- **FR-011**: Allow relay to start from `--spec <feature>` or `--spec-snapshot <path>`
- **FR-012**: Extend MTARP session state with framework-neutral spec references
- **FR-013**: Ensure the relay handoff prompt carries spec context derived from the snapshot

## Non-Functional Requirements

- **NFR-001**: Snapshot generation must be deterministic and offline
- **NFR-002**: MTARP must remain methodology-neutral
- **NFR-003**: The initial implementation must preserve backward compatibility for relay users
- **NFR-004**: All new behavior must be covered by automated tests

## Acceptance Criteria

- [ ] A selected SpecKit feature can be exported to a deterministic JSON snapshot
- [ ] Multiple-feature ambiguity produces a clear error
- [ ] Snapshot output includes unresolved tasks and verification obligations
- [ ] `/speckit snapshot` works inside aider
- [ ] Relay can consume `--spec` and `--spec-snapshot`
- [ ] MTARP session output records framework-neutral spec references
- [ ] Automated tests prove determinism and relay integration
