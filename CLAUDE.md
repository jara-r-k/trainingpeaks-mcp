# TrainingPeaks MCP Server

Local MCP server providing 51 TrainingPeaks tools to Claude Code.

## Architecture

- Python 3.11 + FastMCP framework
- Cookie-based auth (browser session, refreshed via `tp_refresh_auth`)
- Stdio transport: `.venv/bin/tp-mcp serve`

## Build & Test

- Install: `pip install -e ".[dev]"`
- Run tests: `python3 -m pytest tests/ -v`
- Start server: `.venv/bin/tp-mcp serve`

## Key Patterns

- All tools prefixed with `tp_` (e.g. `tp_get_fitness`, `tp_get_workouts`)
- Auth requires an active TrainingPeaks browser session — call `tp_refresh_auth` if 401
- Athlete ID resolved automatically from profile unless overridden

## Compact Instructions

When compacting, always preserve:
- Modified files and their paths
- Auth status (authenticated vs expired)
- Any tool additions or changes to the MCP server
