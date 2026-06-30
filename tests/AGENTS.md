<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# tests

## Purpose
Full pytest test suite mirroring the `src/tp_mcp/` structure. All tests mock the TP API — no real network calls are made in CI. The suite covers auth backends, HTTP client, Pydantic models, and every tool handler. `asyncio_mode = "auto"` is set in `pyproject.toml`, so `async def` tests run without explicit markers.

## Key Files

| File | Description |
|------|-------------|
| `conftest.py` | Shared fixtures: `mock_keyring`, `mock_httpx_client`, `mock_credential`, fake cookie/athlete constants |
| `test_server_functional.py` | Integration-level tests that exercise the server dispatch layer |
| `test_benchmarks.py` | Performance checks (response time, throughput) |
| `test_sanitiser.py` | Tests for the `sanitise_result()` credential scrubber |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `test_auth/` | Tests for all three auth backends (see `test_auth/AGENTS.md`) |
| `test_client/` | Tests for HTTP client, cache, and Pydantic models (see `test_client/AGENTS.md`) |
| `test_tools/` | One test file per tool handler (see `test_tools/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- New tool → new test file at `test_tools/test_<tool_name>.py`.
- Import fixtures from `conftest.py` rather than re-defining mocks inline.
- Never make real HTTP calls; patch `tp_mcp.client.http.httpx.AsyncClient`.
- `TEST_COOKIE`, `TEST_ATHLETE_ID`, `TEST_EMAIL` constants are defined in `conftest.py`.

### Testing Requirements
```bash
python3 -m pytest tests/ -v                   # Full suite
python3 -m pytest tests/test_tools/ -v        # Tools only
python3 -m pytest tests/test_auth/ -v         # Auth only
python3 -m pytest tests/test_client/ -v       # Client only
```

### Common Patterns
- Use `pytest.fixture` with `patch()` context managers for mocking.
- `AsyncMock` for async httpx client methods.
- Auth mocked at `tp_mcp.auth.storage` level, not at keyring level, for most tool tests.

## Dependencies

### Internal
- `src/tp_mcp/` — package under test

### External
- `pytest>=8.0.0`
- `pytest-asyncio>=0.24.0`

<!-- MANUAL: -->
