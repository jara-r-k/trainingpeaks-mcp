<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# tp_mcp

## Purpose
The core MCP server package. Implements all 52 TrainingPeaks tools, authentication, HTTP client, response caching, input validation, credential sanitisation, and the stdio MCP transport. This is the only installable package in the project.

## Key Files

| File | Description |
|------|-------------|
| `server.py` | MCP server entry point — defines all 52 `Tool` objects, registers `_handler` decorators, dispatches `call_tool()` calls, runs `stdio_server()` |
| `cli.py` | CLI commands: `auth`, `auth-status`, `auth-clear`, `config`, `serve`, `help` |
| `sanitiser.py` | `sanitise_result()` — recursively strips auth artefacts (JWT tokens, cookies, sensitive keys) from all tool results before they reach the MCP client |
| `__main__.py` | Enables `python -m tp_mcp` invocation |
| `__init__.py` | Package version (`__version__ = "0.1.0"`) |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `auth/` | Cookie storage, browser extraction, token exchange, validation (see `auth/AGENTS.md`) |
| `client/` | Async HTTP client, response caching, Pydantic models, athlete context var (see `client/AGENTS.md`) |
| `tools/` | One file per tool handler — 52 total (see `tools/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- `server.py` is the single source of truth for tool registration. Every tool must appear in three places: `TOOLS` list, `_TOOL_HANDLERS` dict (via `@_handler`), and imported from `tools/__init__.py`.
- The `_ATHLETE_EXEMPT_TOOLS` set in `server.py` controls which tools do NOT get an injected `athlete` parameter — update it for any tool that operates at account level rather than athlete level.
- `sanitise_result()` is called at the dispatch layer in `server.py` — individual tool handlers must never log or return raw cookie/token values.
- Logging goes to `sys.stderr`; `sys.stdout` is reserved for the MCP stdio protocol.

### Testing Requirements
```bash
python3 -m pytest tests/ -v              # Full suite
python3 -m pytest tests/test_server_functional.py -v  # Server dispatch tests
```

### Common Patterns
- Tool handlers are async functions accepting a single `args: dict` parameter.
- Errors are returned as dicts with `isError: True`, `error_code`, and `message` keys.
- The `athlete_override` context variable in `client/context.py` carries the coach's target athlete ID through async call chains without thread-local state.

## Dependencies

### Internal
- `auth/` — credential retrieval
- `client/` — HTTP requests and caching
- `tools/` — all tool implementations
- `sanitiser.py` — credential scrubbing

### External
- `mcp` — `Server`, `stdio_server`, `Tool`, `TextContent`
- `httpx` (via `client/`)
- `pydantic` (via `client/models.py`)

<!-- MANUAL: -->
