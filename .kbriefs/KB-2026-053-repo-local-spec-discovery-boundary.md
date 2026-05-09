---
id: KB-2026-053
type: failure-mode
status: validated
created: 2026-05-09
updated: 2026-05-09
tags: [speckit, discovery, repo-boundary, venv, failure-mode, testing]
related: [KB-2026-051, KB-2026-052]
---

# Repo-Local Spec Discovery Boundary

## Context & Problem Statement

The implemented `/speckit status` command worked, but a live run on this repository exposed a bad
discovery boundary. Test-file discovery used a blind recursive search from repo root, so the
status report walked `.venv` and surfaced thousands of third-party package tests as if they were
project-local evidence.

This produced misleading output:

- test counts were inflated from repo-local tests to dependency-tree tests
- the status report became noisy and hard to read
- a “read-only discovery” command looked operationally correct while reporting the wrong scope

## Failure Mode Description

### Trigger

- A repository contains a local virtualenv or dependency tree under the workspace root.
- Discovery uses broad recursive file search without pruning environment/dependency directories.

### Observed Failure

- `/speckit status` reported `3282` test files instead of the repo-local set.
- Most returned paths were from `.venv/lib/python3.12/site-packages/...`.

### Root Cause

- Test discovery treated “under repo root” as equivalent to “belongs to the repo.”
- Dependency and cache directories were not excluded during traversal.

## Prevention / Standard

### Rule

Repo-local spec discovery must prune environment, cache, VCS, and dependency trees during
traversal instead of filtering only after recursion has already entered them.

### Validated Exclusion Set

- `.git`
- `.mypy_cache`
- `.pytest_cache`
- `.ruff_cache`
- `.venv`
- `__pycache__`
- `build`
- `dist`
- `node_modules`
- `site-packages`

### Implementation Pattern

- Walk the tree top-down.
- Mutate the directory list in place so excluded trees are never descended into.
- Report only repo-local Python test files after pruning.

## Evidence

Before the fix, a live `/speckit status` run reported:

```text
Test Files (3282):
- .venv/lib/python3.12/site-packages/_pytest/doctest.py
- .venv/lib/python3.12/site-packages/...
```

After the fix, the same command reported:

```text
Test Files (49):
- benchmark/test_benchmark.py
- scripts/test_claude.py
- tests/test_speckit.py
...
```

Validation:

```text
task dc:exec -- bash -lc '.venv/bin/python -m pytest tests/test_speckit.py -q'
22 passed in 2.07s

task dc:exec -- bash -lc \".venv/bin/python -m aider.main --model gpt-4o-mini --yes-always --message '/speckit status'\"
```

An end-to-end relay CLI demo with mocked providers also still confirmed `--spec` injects planning
context after the discovery fix.

## Anti-Pattern

### Incorrect

- `root.rglob("*test*.py")` across the whole workspace without boundary pruning

### Why It Fails

- traverses generated/local dependency trees
- produces misleading governance signals
- scales poorly on large workspaces

## Applicability

- Applies to SpecKit discovery
- Applies to future OpenSpec/BMad discovery layers
- Applies to any repo-scoped evidence inventory in this codebase

## Related Knowledge

- `aider/speckit.py`
- `tests/test_speckit.py`
- KB-2026-051
- KB-2026-052
