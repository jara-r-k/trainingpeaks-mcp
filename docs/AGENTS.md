<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# docs

## Purpose
Project documentation: architecture decision records (ADRs), product requirements document (PRD), progress tracking, and superpowers planning artefacts. Nothing here is imported by the runtime — this is human- and agent-readable reference material only.

## Key Files

| File | Description |
|------|-------------|
| `tpmcp-prd.md` | Product requirements document — feature scope and user stories |
| `PROGRESS.md` | Running changelog of completed milestones and pending work |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `adr/` | Architecture Decision Records (see `adr/AGENTS.md`) |
| `images/` | Screenshots and diagrams referenced in docs |
| `superpowers/` | OMC/superpowers planning artefacts (plans, specs, handoffs) |

## For AI Agents

### Working In This Directory
- Never modify files in `docs/` as part of a tool implementation — docs are updated separately.
- ADRs are append-only: create new ones rather than editing existing decisions.
- `PROGRESS.md` can be updated to reflect completed milestones.

### Common Patterns
- ADR naming: `ADR-NNNN-short-title.md`
- Superpowers plans live under `superpowers/plans/`

<!-- MANUAL: -->
