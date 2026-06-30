<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# client

## Purpose
Async HTTP client layer for the TrainingPeaks API. Handles token caching, rate-limiting, TTL-based response caching, Pydantic response models, and the athlete-targeting context variable used by coach accounts. All tool handlers call through this layer — no tool should use `httpx` directly.

## Key Files

| File | Description |
|------|-------------|
| `http.py` | `TPClient` — async httpx wrapper. Manages token exchange from cookie, `TokenCache` (class-level lock prevents refresh race), `MIN_REQUEST_INTERVAL = 0.15s` rate limiter, error mapping to `APIError` subclasses, `APIResponse` and `RawResponse` dataclasses |
| `cache.py` | `ResponseCache` with `CacheTier` enum (PROFILE=1h, WORKOUT_LIST=5m, WORKOUT_DETAIL=2m, REALTIME=30s). `build_cache_key()` is deterministic and order-independent |
| `models.py` | Selective Pydantic v2 models with `extra='ignore'`. `UserProfile`, `WorkoutSummary`. `DateOnly` validator strips time/timezone from datetime strings. All optional fields are `Optional` to handle sport/tier variance |
| `context.py` | `athlete_override: ContextVar[str | None]` — carries target athlete ID through async call chains for coach accounts. Set/reset in `server.py` dispatch layer |

## For AI Agents

### Working In This Directory
- Never bypass `TPClient` to make raw `httpx` calls in tool handlers.
- `TokenCache` is a class variable with an asyncio lock — do not replace or shadow it; concurrent token refreshes would cause auth races.
- `MIN_REQUEST_INTERVAL = 0.15s` in `http.py` provides basic rate limiting. Bulk operations (e.g. fetching 90 days of workouts) should add small delays between requests.
- When adding new Pydantic models: always set `extra='ignore'` and make all non-essential fields `Optional` — TP API returns different fields for cycling vs running vs swimming, and premium vs free accounts.
- `DateOnly` validator in `models.py` strips `T...` suffixes from datetime strings — use it for any date field to avoid timezone conversion bugs.

### Testing Requirements
```bash
python3 -m pytest tests/test_client/ -v
```
- `test_http.py` — mock `httpx.AsyncClient` via `conftest.py` fixture
- `test_cache.py` and `test_cache_integration.py` — TTL and key collision tests
- `test_models.py` — field validation and sport-type shape variance

### Common Patterns
- Error codes: `AUTH_EXPIRED`, `AUTH_INVALID`, `NOT_FOUND`, `RATE_LIMITED`, `PREMIUM_REQUIRED`, `VALIDATION_ERROR`, `API_ERROR`, `NETWORK_ERROR` (see `ErrorCode` enum in `http.py`).
- `APIResponse(success, data, error_code, message)` is the standard return type from `TPClient` methods.
- `athlete_override` is read inside `TPClient` to substitute the target athlete ID in API URLs.

## Dependencies

### Internal
- `auth/storage.py` — `get_credential()` for cookie retrieval
- `sanitiser.py` — result scrubbing (called at server layer, not here)

### External
- `httpx>=0.27.0` — async HTTP
- `pydantic>=2.0.0` — response models

<!-- MANUAL: -->
