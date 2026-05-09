# Implementation Plan: SpecKit MTARP Bootstrap Integration

## Outcome

Phase 1 shipped a read-only SpecKit bootstrap:

- `aider/speckit.py` discovers constitution, spec, plan, and task artifacts
- `/speckit status` reports artifact completeness and MTARP readiness
- `tests/test_speckit.py` covers discovery, reporting, and command integration

## Architecture Delivered

### Component Structure
```text
aider/
|-- speckit.py              # SpecKit discovery and status reporting
|-- commands.py             # /speckit status command
`-- relay/
    `-- session.py          # MTARP execution state, still separate from SpecKit
```

### Design Principles Preserved
- **Read-only first**: No generation or mutation of SpecKit artifacts
- **Separation of concerns**: Spec artifacts are treated as intent, not execution state
- **Aider integration**: Uses existing command, IO, and repository infrastructure
- **Testability**: Discovery and formatting are isolated in small functions

## Empirical Validation

The bootstrap is proven by the repository test suite:

- `tests/test_speckit.py` verifies discovery of constitution/spec/plan/tasks artifacts
- Status formatting is validated for empty, complete, incomplete, and MTARP-ready repositories
- `/speckit status` command integration is covered with repository-root and no-root scenarios

Validated on 2026-05-09:

```text
task dc:exec -- bash -lc '.venv/bin/python -m pytest tests/test_speckit.py -q'
19 passed in 4.24s
```

## What This Phase Does Not Attempt

This phase intentionally does not:

- select one feature from multiple specs
- export deterministic execution snapshots
- embed framework-native artifact paths into MTARP semantics
- generate or mutate SpecKit artifacts

Those concerns move to `specs/002-planning-kernel-snapshot/`.
