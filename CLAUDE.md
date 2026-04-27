# CLAUDE.md — trainingpeaks-mcp

> **Root principles**: See ~/projects/CLAUDE.md §1–4 (Think Before Coding, Simplicity First,
> Surgical Changes, Goal-Driven Execution). Apply them here — especially §3: with 52 tools
> across 34 source files, touch only the file you need.

> **Wiki**: ~/projects/wiki/ — entity page at [[entities/trainingpeaks-mcp]].

## Project Overview

Python MCP server (v2.0.0) exposing 52 TrainingPeaks tools to Claude Code/Desktop via stdio.
Cookie-based auth (browser session → JWT token exchange). Published open-source under MIT.

## Tech Stack

- **Python** ≥3.10 (tested 3.10–3.14)
- **MCP SDK** (`mcp>=1.0.0`) — low-level Server + stdio_server
- **httpx** — async HTTP client for TP API
- **Pydantic** v2 — selective response models (`extra='ignore'`)
- **keyring** + **cryptography** — credential storage (Keychain → encrypted file fallback)
- **browser-cookie3** (optional) — cookie extraction from browsers
- **Build**: hatchling
- **Linting**: ruff (line-length 120), mypy (py310)
- **Testing**: pytest + pytest-asyncio (asyncio_mode = "auto")

## Architecture

```
src/tp_mcp/
├── server.py          # MCP server — imports & registers all 52 tools
├── cli.py             # CLI entrypoint (tp-mcp serve|auth|auth-status|config)
├── auth/              # Cookie storage, token exchange, validation
│   ├── browser.py     # browser-cookie3 extraction (hardcoded .trainingpeaks.com)
│   ├── keyring.py     # System keyring storage
│   ├── encrypted.py   # AES-256-GCM fallback storage
│   ├── storage.py     # Credential retrieval chain (env → keyring → file)
│   └── validator.py   # Token validation
├── client/
│   ├── http.py        # TPClient — async httpx wrapper, token cache, rate limiting
│   ├── models.py      # Selective Pydantic models (WorkoutSummary, etc.)
│   ├── cache.py       # Response caching tiers
│   └── context.py     # Athlete ID override context manager
└── tools/             # One file per tool (52 files)
    ├── __init__.py    # Re-exports all tool handlers
    ├── _validation.py # Shared Pydantic input validation
    ├── workouts.py    # tp_get_workouts, tp_create_workout, etc.
    ├── fitness.py     # tp_get_fitness
    ├── analyze.py     # tp_analyze_workout
    └── ...            # One handler per file
```

**Key invariant**: one tool = one file. New tools → new file, don't modify existing.

## Dev Commands

```bash
pip install -e ".[dev]"           # Install with dev deps
python3 -m pytest tests/ -v      # Run tests
mypy src/                         # Type checking
ruff check src/                   # Linting
.venv/bin/tp-mcp serve            # Start MCP server (stdio)
tp-mcp auth --from-browser chrome # Auth setup
tp-mcp auth-status                # Check auth
```

## Testing

- Tests mirror source: `tests/test_tools/test_[tool].py`
- `conftest.py` provides `mock_keyring`, fake cookie/athlete fixtures
- Auth mocked in all tests — no real TP calls in CI
- `test_server_functional.py` for integration-level server tests
- `test_benchmarks.py` for performance checks

## Success Criteria Patterns

**New tool**: Create `tools/new_tool.py` with handler → add import to `tools/__init__.py` →
register in `server.py` → create `tests/test_tools/test_new_tool.py` → all tests pass.

**Bug fix**: Reproduce with a failing test → fix → test passes → no other tests break.

**Auth change**: Verify all three storage backends still work (env, keyring, encrypted).
Verify token refresh race condition handling. Run `test_auth/` suite.

**Model change**: Update `client/models.py` → verify `extra='ignore'` still handles missing
fields → test with multiple sport types (bike, run, swim have different field shapes).

## Gotchas & Failure Modes

1. **Cookie expiry**: Browser sessions expire after ~2–4 weeks. If 401 errors appear, call
   `tp_refresh_auth` or re-run `tp-mcp auth`. The cookie is the root of all auth.
2. **Field shape varies by sport/tier**: TP API returns different fields for cycling vs running
   vs swimming, and for premium vs free accounts. Every varying field must be `Optional`.
3. **Undocumented rate limits**: ~100 req/min, 60s reset. `MIN_REQUEST_INTERVAL = 0.15s` in
   `http.py` provides basic throttling. Bulk fetches need small delays.
4. **Token refresh race**: Concurrent tool calls can both detect expired token. `TokenCache`
   class variable + lock handles this — don't bypass it.
5. **`title` vs `workoutTitle`**: List endpoint returns `title`, detail endpoint returns
   `workoutTitle`. Pydantic `field_validator` fallbacks handle the inconsistency.
6. **ruff line-length 120**: Not the root convention (88 for Black). This project uses ruff
   at 120 — match it, don't "fix" to 88.
7. **No official API**: This uses TP's internal API via cookie auth. If TP changes their
   internal endpoints, the entire server breaks. Monitor for 404s on known endpoints.
8. **Result sanitisation**: Tool results are scrubbed for auth-related keys before returning
   to Claude. Never log or return cookie/token values.
9. **Wiki raw/ safety**: This project is part of the ~/projects/ LLM Wiki. Never write to ~/projects/raw/ — that layer is human-curated and immutable. See ~/projects/CLAUDE.md for the full wiki schema.

## Compact Instructions

When compacting, always preserve:
- Modified files and their paths
- Auth status (authenticated vs expired)
- Any tool additions or changes to the MCP server
- Which sport types were tested (field shape variance)
