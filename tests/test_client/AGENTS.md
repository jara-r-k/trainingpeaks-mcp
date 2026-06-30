<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# test_client

## Purpose
Tests for the HTTP client layer, response cache, and Pydantic models. Covers token exchange, rate limiting, cache TTL tiers, cache key determinism, and field shape variance across sport types and account tiers.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | Package marker |
| `test_http.py` | Tests for `TPClient` — token exchange, request dispatch, error mapping, rate limiting. Uses `mock_httpx_client` fixture |
| `test_cache.py` | Unit tests for `ResponseCache` TTL logic and `build_cache_key()` determinism |
| `test_cache_integration.py` | Integration-level cache tests — verifies cached responses are returned on repeat calls |
| `test_models.py` | Pydantic model tests — field aliasing, `DateOnly` validator, `extra='ignore'` behaviour, sport-type shape variance |

## For AI Agents

### Working In This Directory
- Mock `httpx.AsyncClient` via the `mock_httpx_client` fixture in root `conftest.py`.
- `test_models.py` should cover at minimum: bike workout, run workout, swim workout, and a response with extra unknown fields (to verify `extra='ignore'`).
- Cache tests must verify both hit and miss paths, and TTL expiry.

### Testing Requirements
```bash
python3 -m pytest tests/test_client/ -v
```

## Dependencies

### Internal
- `src/tp_mcp/client/` — modules under test

<!-- MANUAL: -->
