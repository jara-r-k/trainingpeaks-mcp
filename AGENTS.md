<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# trainingpeaks-mcp

## Purpose
Python MCP server (v2.0.0) exposing 52 TrainingPeaks tools to AI assistants (Claude Code/Desktop) via stdio transport. Operates entirely through TrainingPeaks' internal cookie-based API — no official API key. Cookie extracted from user's browser session is exchanged for a JWT token, which is used for all subsequent requests. Published open-source under MIT by JamsusMaximus.

## Key Files

| File | Description |
|------|-------------|
| `pyproject.toml` | Project metadata, dependencies, build config (hatchling), entry point `tp-mcp` → `tp_mcp.cli:main` |
| `README.md` | User-facing install and setup guide |
| `RESEARCH.md` | Notes on TP API reverse-engineering |
| `CLAUDE.md` | AI agent instructions and architecture overview for this project |
| `uv.lock` | Locked dependency manifest (uv package manager) |
| `LICENSE` | MIT licence |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `src/` | All application source code (see `src/AGENTS.md`) |
| `tests/` | Test suite mirroring `src/tp_mcp/` structure (see `tests/AGENTS.md`) |
| `docs/` | ADRs, PRD, progress tracking, plans (see `docs/AGENTS.md`) |
| `scripts/` | Utility shell scripts |

## For AI Agents

### Working In This Directory
- UPSTREAM-OWNED repo (JamsusMaximus/trainingpeaks-mcp). Never `git add`, `git commit`, or `git push` here.
- Read CLAUDE.md at this root before any changes — it contains critical gotchas.
- The `tp-mcp` CLI entrypoint is defined in `pyproject.toml` → `tp_mcp.cli:main`.
- Python ≥3.10 required; use `uv` or `pip install -e ".[dev]"` for dev setup.
- ruff line-length is 120 (NOT 88) — never "fix" to 88.

### Testing Requirements
```bash
python3 -m pytest tests/ -v          # Full suite
mypy src/                             # Type checking
ruff check src/                       # Linting
```

### Common Patterns
- One tool = one file in `src/tp_mcp/tools/`.
- All tool results pass through `sanitise_result()` before reaching the MCP client.
- Coach-account multi-athlete support is injected at dispatch time via `athlete_override` context var.

## Dependencies

### External
- `mcp>=1.0.0` — MCP SDK (stdio_server, Server, Tool)
- `httpx>=0.27.0` — async HTTP client for TP API
- `keyring>=25.0.0` — system credential storage
- `cryptography>=42.0.0` — AES-256-GCM fallback storage
- `pydantic>=2.0.0` — response model validation
- `idna>=3.15` — DNS/URL utilities
- `browser-cookie3>=0.19.0` (optional extra `[browser]`) — cookie extraction

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
