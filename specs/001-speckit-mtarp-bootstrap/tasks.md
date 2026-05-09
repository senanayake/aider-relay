# Implementation Tasks: SpecKit MTARP Bootstrap Integration

## Completed Work

### Discovery and Reporting
- [x] Add constitution discovery (`.specify/memory/constitution.md`)
- [x] Detect complete spec directories (`spec.md` + `plan.md` + `tasks.md`)
- [x] Calculate MTARP readiness from constitution + completeness
- [x] Report complete vs incomplete spec directories
- [x] Generate human-readable status output

### Command Integration
- [x] Implement `/speckit status`
- [x] Use aider's repository root detection
- [x] Use aider's IO and error reporting patterns

### Testing and Validation
- [x] Add discovery tests for constitution, complete specs, and incomplete specs
- [x] Add MTARP readiness tests
- [x] Add `/speckit status` command integration tests
- [x] Validate current implementation with `tests/test_speckit.py`

## Follow-on Work

The next implementation stage is tracked in:

- `specs/002-planning-kernel-snapshot/`

That stage owns:

- feature selection when multiple specs exist
- deterministic snapshot export
- framework-neutral planning kernel structures
- relay and MTARP integration with spec references
