# SpecKit MTARP Bootstrap Integration

## Overview

Integrate a minimal, read-only SpecKit-compatible workflow into aider-relay that can discover
SpecKit-style artifacts and report their status without generating or modifying specs.

## Implemented Scope

### As a developer using aider-relay
- I want to discover SpecKit artifacts in my repository so I can see what specifications exist
- I want to check the status of SpecKit artifacts so I can understand project readiness
- I want the tool to work offline without requiring LLM calls for basic discovery

### As a project maintainer
- I want SpecKit artifact discovery to be separate from MTARP execution state
- I want the implementation to follow aider's existing patterns and conventions
- I want this bootstrap to be a foundation for later deterministic snapshot export

## Functional Requirements

### Artifact Discovery
- **FR-001**: Discover `.specify/memory/constitution.md`
- **FR-002**: Discover `specs/<feature>/spec.md`
- **FR-003**: Discover `specs/<feature>/plan.md`
- **FR-004**: Discover `specs/<feature>/tasks.md`
- **FR-005**: Distinguish complete spec directories from incomplete ones

### Status Reporting
- **FR-006**: Report found and missing artifacts in human-readable format
- **FR-007**: Report whether the repository is ready for MTARP snapshot generation
- **FR-008**: Provide summary statistics for discovered artifacts
- **FR-009**: Handle empty repositories gracefully

### Command Integration
- **FR-010**: Implement `/speckit status` following aider's command patterns
- **FR-011**: Integrate with aider's existing IO and error handling
- **FR-012**: Use aider's repository root discovery mechanism

## Non-Functional Requirements

### Compatibility
- **NFR-001**: Must work offline without LLM calls
- **NFR-002**: Must not modify SpecKit artifacts
- **NFR-003**: Must be compatible with upstream aider changes
- **NFR-004**: Must follow aider's existing code patterns and conventions

### Performance
- **NFR-005**: Artifact discovery must complete in under 1 second for typical repositories

### Maintainability
- **NFR-006**: Implementation must be in small, testable modules
- **NFR-007**: Must have comprehensive test coverage

## Acceptance Criteria

### Discovery Functionality
- [x] Can discover `constitution.md` in `.specify/memory/`
- [x] Can discover `spec.md` files in `specs/<feature>/`
- [x] Can discover `plan.md` files in `specs/<feature>/`
- [x] Can discover `tasks.md` files in `specs/<feature>/`
- [x] Distinguishes complete and incomplete spec directories
- [x] Handles missing files gracefully

### Status Reporting
- [x] Generates human-readable status report
- [x] Shows found vs missing artifacts
- [x] Provides summary statistics
- [x] Indicates MTARP readiness
- [x] Handles empty repositories without errors

### Command Integration
- [x] `/speckit status` command works in aider
- [x] Uses aider's error handling patterns
- [x] Respects aider's repository root detection
- [x] Works with aider's existing IO system

### Quality Assurance
- [x] All functionality has unit tests
- [x] Integration tests cover command execution
- [x] Code follows aider's style and patterns
- [x] No regressions in existing aider functionality

## Out of Scope (Moved to Later Specs)

- Selecting one feature when multiple specs exist
- Deterministic MTARP snapshot generation and execution
- `/speckit snapshot`, `/speckit.specify`, `/speckit.plan`, `/speckit.tasks`,
  `/speckit.implement`
- LLM integration for artifact generation
- Multi-feature orchestration
- Artifact validation beyond existence and completeness checks

## References

- GitHub Spec Kit: https://github.com/github/spec-kit
- Aider command system: `aider/commands.py`
- Aider IO patterns: `aider/io.py`
- Existing aider tests: `tests/` directory
- Follow-on work: `specs/002-planning-kernel-snapshot/`
