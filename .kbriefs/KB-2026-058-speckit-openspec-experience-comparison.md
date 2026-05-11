---
id: KB-2026-058
type: tradeoff
status: validated
created: 2026-05-11
updated: 2026-05-11
tags: [speckit, openspec, user-experience, workflow, planning, integration, kbpd]
related: [KB-2026-048, KB-2026-056, KB-2026-057]
---

# Spec Kit vs OpenSpec Workflow Experience Comparison

## Context & Problem Statement

This repo now integrates both upstream Spec Kit and OpenSpec as thin planning producers. The
question is not which framework is "better" in the abstract. The useful question is what each
framework feels like to use from `aider-relay`, and what that implies for architecture.

## Trade-Off Description

### Variable Definitions

- **Bootstrap determinism**: How much usable planning state exists immediately after CLI setup.
- **Artifact immediacy**: How quickly real, inspectable planning files appear.
- **Workflow rigidity**: How strongly the framework enforces a staged lifecycle.
- **Brownfield fit**: How naturally the framework centers changes to an existing system.
- **CLI-only operability**: How far a non-interactive shell flow gets without invoking the agent
  workflow itself.

### Relationships

- As **bootstrap determinism** increases, CLI-only automation gets easier, but the workflow tends
  to become more opinionated.
- As **workflow rigidity** decreases, early experimentation gets easier, but adapters must tolerate
  sparser partial states.
- A stronger **brownfield fit** usually means the planning unit shifts from "feature shell" to
  "change proposal."

## Empirical Findings

### Spec Kit Experience

Observed with `specify-cli` `v0.8.7`:

```bash
uvx --from git+https://github.com/github/spec-kit.git@v0.8.7 specify init . --integration codex --script sh
./.specify/scripts/bash/create-new-feature.sh --json "Bridge local relay consumption"
```

Experience:

- `init` creates a rich project structure immediately.
- Templates, scripts, integration metadata, and `.specify/memory/constitution.md` appear at setup.
- The helper scaffolding flow provides a deterministic `SPEC_FILE` and a clear staged artifact
  model.
- This made Spec Kit easy to wrap with pinned CLI tasks and smoke automation.

Practical implication:

- Spec Kit is stronger for deterministic bootstrap and greenfield or staged planning flows.

### OpenSpec Experience

Observed with OpenSpec `1.3.1`:

```bash
npx -y @fission-ai/openspec@1.3.1 init --tools codex
npx -y @fission-ai/openspec@1.3.1 new change add-openspec-adapter
npx -y @fission-ai/openspec@1.3.1 instructions proposal --change add-openspec-adapter --json
```

Experience:

- `init` installs Codex skills and command surfaces but does not create planning artifacts.
- `new change` creates a change shell with `.openspec.yaml`, but not proposal/design/tasks/spec
  files.
- The meaningful planning content is expected to be materialized by the OpenSpec workflow itself.
- This feels lighter and more fluid, but it is less deterministic for pure CLI-only automation.

Practical implication:

- OpenSpec is stronger for brownfield, change-centered flows, but the adapter must tolerate
  partial or agent-materialized states.

## Design Implications for aider-relay

- Use **Spec Kit** when you want strong staged scaffolding and a direct feature pointer.
- Use **OpenSpec** when you want a lighter change proposal layer over an existing codebase.
- Keep the planning kernel neutral so each framework can remain itself.
- Do not force OpenSpec to behave like Spec Kit, or Spec Kit to behave like OpenSpec.

## Quantitative/Qualitative Summary

| Variable | Spec Kit | OpenSpec | Implication |
|----------|----------|----------|-------------|
| Bootstrap determinism | High | Medium | Spec Kit is easier to automate immediately |
| Artifact immediacy | High | Low-Medium | OpenSpec needs workflow materialization |
| Workflow rigidity | Higher | Lower | OpenSpec is more fluid |
| Brownfield fit | Medium | High | OpenSpec maps better to change-driven work |
| CLI-only operability | High | Medium | Spec Kit is easier for shell-first smoke paths |

## Rationale & Recommendations

- Recommendation 1: Keep thin wrappers for both CLIs rather than reimplementing either workflow.
- Recommendation 2: Prefer Spec Kit when the repository needs strong scaffolding and staged
  feature planning.
- Recommendation 3: Prefer OpenSpec when the repository needs a lighter brownfield planning layer.
- Recommendation 4: Capture partial-state handling as first-class adapter behavior.

## Verification & Compliance

- `task dc:smoke:specify`
- `task dc:smoke:openspec`
- manual CLI help checks through `task dc:specify -- --help` and `task dc:openspec -- --help`

## Applicability Matrix

| Context | Spec Kit | OpenSpec | Notes |
|---------|----------|----------|-------|
| Greenfield feature planning | Strong | Moderate | Spec Kit scaffolding is richer |
| Brownfield change planning | Moderate | Strong | OpenSpec is change-centered |
| Deterministic shell automation | Strong | Moderate | OpenSpec relies more on workflow materialization |
| Planning kernel integration | Strong | Strong | Both work when consumed neutrally |

## Related Knowledge

- [KB-2026-048](C:/Users/chris/Dev/aider-relay/.kbriefs/KB-2026-048-spec-framework-optionality-and-agentic-se-architecture.md)
- [KB-2026-056](C:/Users/chris/Dev/aider-relay/.kbriefs/KB-2026-056-upstream-specify-cli-consumption-bridge.md)
- [KB-2026-057](C:/Users/chris/Dev/aider-relay/.kbriefs/KB-2026-057-openspec-change-adapter-standard.md)
