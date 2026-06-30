<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# src

## Purpose
Container for the installable Python package. The single package `tp_mcp` lives here under the `src/` layout, which keeps it isolated from the project root during development and avoids accidental import of uninstalled code.

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `tp_mcp/` | The entire MCP server implementation (see `tp_mcp/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- Do not add anything alongside `tp_mcp/` — the `src/` layout has one package only.
- `hatchling` is configured to package only `src/tp_mcp` (see `pyproject.toml`).

<!-- MANUAL: -->
