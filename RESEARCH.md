# RESEARCH.md — TrainingPeaks MCP Server

## Overview

trainingpeaks-mcp is a Python MCP (Model Context Protocol) server exposing 51 tools for TrainingPeaks integration. It enables Claude Code (and other MCP clients) to read and write TrainingPeaks data — workouts, fitness metrics, events, equipment, nutrition, and athlete profiles. The engineering constraints include: cookie-based authentication (no official OAuth API), rate limiting from the TP API, 51 tools that must remain backward-compatible, and Pydantic-based response parsing that must handle inconsistent API field shapes across sport types and subscription tiers.

---

## Decision Log

### Cookie-Based Authentication

**Date:** 2025-12 (retrospective)
**Status:** Kept (with reservations)

**Problem Statement:**
TrainingPeaks does not provide a public OAuth API for third-party applications. The system needs to authenticate with the TP API to access athlete data. How do we authenticate without official API credentials?

**Approaches Tried:**

1. **Official API application** — Applied for TP API partnership.
   - Result: TP's API programme is restricted to certified coaching platforms and hardware vendors. Individual developer applications are not accepted. No timeline for public API access.
   - Verdict: Rejected (not available).

2. **Cookie extraction from browser** — Use `browser-cookie3` to extract the `Production_tpAuth` session cookie from Chrome/Safari/Firefox, then exchange it for a JWT access token via the internal `/users/v3/token` endpoint.
   - Result: Works reliably. The cookie persists across browser sessions. Token exchange returns a JWT with configurable expiry. The approach is fragile (depends on TP's internal API stability) but is the only viable option.
   - Verdict: Kept.

3. **Headless browser automation** — Use Playwright to log in programmatically and capture the session.
   - Result: Works but is heavyweight (requires browser binary), slow (login flow takes 5-10 seconds), and breaks when TP changes their login page. Not suitable for an MCP server that starts on every Claude Code session.
   - Verdict: Rejected.

**Current Approach:**
Three-tier credential storage with fallback chain:
1. Environment variable (for CI/server deployments)
2. System keyring (macOS Keychain, preferred)
3. Encrypted file fallback (for environments without keyring access)

Token exchange: `POST /users/v3/token` with cookie → JWT access token. In-memory `TokenCache` with 60-second refresh buffer before expiry. Shared across all `TPClient` instances as a class variable.

The invariant: the auth cookie is the single source of truth. All three storage backends produce the same cookie format. Token refresh is transparent to tools — `_ensure_access_token()` handles it automatically.

**What Did NOT Survive:**
- Official OAuth (not available to individual developers)
- Headless browser automation (too slow, too fragile)
- Storing raw JWT tokens (they expire; the cookie is longer-lived)

---

### Pydantic Models for API Response Parsing

**Date:** 2025-12 (retrospective)
**Status:** Kept

**Problem Statement:**
TP API responses are large JSON objects with many fields. MCP tool responses consume Claude's context window. How do we extract only the relevant fields while maintaining type safety?

**Approaches Tried:**

1. **Raw dict access** — Parse JSON, access fields by string key.
   - Result: No type safety, no validation, no IDE completion. Typos in field names silently return `None`. Different tools implemented different parsing logic for the same response shape.
   - Verdict: Rejected.

2. **Full Pydantic models matching API schema** — Model every field in the API response.
   - Result: Token-heavy. The full workout detail response has 100+ fields; most are irrelevant to Claude's analysis. Sending all fields wastes context window and confuses the model.
   - Verdict: Rejected.

3. **Selective Pydantic models** — Model only the fields that tools actually use. Use `model_config = ConfigDict(extra='ignore')` to silently drop unknown fields.
   - Result: Clean, type-safe, and token-efficient. Models like `WorkoutSummary` extract 10-15 essential fields from 100+ available. Parse functions (`parse_workout_detail()`, `parse_user_profile()`) handle the conversion.
   - Verdict: Kept.

**Current Approach:**
- `client/models.py` defines selective Pydantic models for each response type
- `extra='ignore'` drops fields not in the model
- Parse functions handle field name inconsistencies (e.g. `title` vs `workoutTitle`)
- Tool handlers format Pydantic model output for human/Claude readability

The invariant: Pydantic models are the single source of truth for response shapes. Tools never access raw dict keys — always go through the model.

**What Did NOT Survive:**
- Raw dict access (no type safety, duplicate parsing logic)
- Full API schema models (too token-heavy for MCP context window)

---

### One Tool Per File Architecture

**Date:** 2025-12 (retrospective)
**Status:** Kept

**Problem Statement:**
With 51 tools, code organisation is critical. How do we structure tools for maintainability?

**Approaches Tried:**

1. **All tools in one file** — Single `tools.py` with 51 handler functions.
   - Result: File exceeded 3,000 lines. Merge conflicts on every change. Impossible to understand tool dependencies at a glance.
   - Verdict: Rejected.

2. **Tools grouped by domain** — `workout_tools.py`, `fitness_tools.py`, `event_tools.py`, etc.
   - Result: Better, but grouping was subjective. Some tools span domains (e.g. `tp_analyze_workout` touches fitness, peaks, and heart rate zones). Group files still grew large.
   - Verdict: Rejected.

3. **One tool per file** — `tools/fitness.py`, `tools/workout.py`, `tools/analyze_workout.py`, etc.
   - Result: Each file is self-contained with its own imports, handler, and helper functions. Easy to find, easy to test (one test file per tool), easy to add new tools without touching existing code. `server.py` registers all tools from the directory.
   - Verdict: Kept.

**Current Approach:**
- `src/tp_mcp/tools/` contains one Python file per tool (51 files)
- `server.py` imports and registers all tools
- Each tool file exports a single handler function
- Tests mirror the structure: `tests/test_tools/test_[tool_name].py`

The invariant: one tool = one file. New tools are added by creating a new file, not modifying existing ones.

**What Did NOT Survive:**
- Monolithic tools file (unmaintainable at 51 tools)
- Domain-grouped files (subjective grouping, still grew large)

---

## Discoveries

### TP API Field Shape Inconsistencies

**Date:** 2026-02

The TP API returns different field shapes depending on:
- **Sport type**: `normalizedPower` is null for swimming; `pace` fields absent for cycling
- **Subscription tier**: `heartRateZones` absent for non-premium athletes
- **Endpoint version**: `title` (list endpoint) vs `workoutTitle` (detail endpoint)
- **Workout source**: Garmin-synced workouts have different field names than manually entered ones

The Pydantic models handle this with `Optional` fields and `field_validator` fallbacks. Every field that varies by context must be Optional with a sensible default.

### Rate Limiting Behaviour

**Date:** 2026-01

The TP API rate limits are undocumented. Empirical observation:
- ~100 requests/minute before 429 responses appear
- Rate limit resets after 60 seconds
- Bulk operations (fetching workout history) should batch with small delays
- Auth token exchange is not rate-limited (tested up to 10/minute)

No official documentation exists for these limits. The values were determined by experimentation.

### Token Refresh Race Condition

**Date:** 2026-01

When multiple tools execute concurrently (e.g. Claude calls `tp_get_workouts` and `tp_get_fitness` simultaneously), both may detect an expired token and attempt refresh simultaneously. The `TokenCache` class variable ensures only one refresh occurs (second caller sees the updated cache), but there was initially a race window where both refreshes could fire. Fixed by adding a check after acquiring the lock: if the token was refreshed while waiting, skip the refresh.

---

## Open Questions

- [ ] Should the server implement request queuing/throttling to stay under the undocumented rate limit, or leave that to the caller?
- [ ] Is cookie-based auth sustainable long-term? If TP changes their internal API, the entire auth flow breaks. Should we lobby for official API access?
- [ ] Should we cache API responses at the MCP server level to reduce TP API load? (Being implemented as part of pretext pattern adoption — Phase 3)
- [ ] Some tools (e.g. `tp_analyze_workout`) make multiple sequential API calls internally. Should these be refactored to use a batch fetch pattern?

---

## References

- [CLAUDE.md](CLAUDE.md) — Tool list, auth setup, development workflow
- [Pretext pattern catalogue](~/Obsidian/ClaudeHub/references/pretext-pattern-catalogue.md)
