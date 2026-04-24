---
title: jarasport-clerk-integration-CLK-1-backend-jwt-middleware
plan: CLK Phase 1 — Backend JWT Middleware
status: not-started
owner: jara-r-k
date: 2026-04-25
project: trainingpeaks-mcp
parent: jarasport-clerk-integration-master
phase: CLK-1
actionable: blocked
blocked_on: CLK-0
next_action: (Blocked) Await CLK-0 DoD sign-off
depends_on: CLK-0
---

# CLK-1 — Backend JWT Middleware Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL — use `superpowers:test-driven-development` plus `superpowers:executing-plans`. Each task uses `- [ ]` tracking. Every task that adds production code adds a test in the same commit.

**Before you start:** read the [CLK master plan](./2026-04-25-jarasport-clerk-integration-master.md) §12 and `HANDOFFS/CLK-0-to-CLK-1.md`. Claim this phase in master §3.

**Goal:** Ship `tp_mcp/auth/clerk.py` with verified-against-JWKS JWT verification, an async-safe JWKS cache, `UserContext` propagation through an ASGI middleware, and an `EnvDevAuth` dev-mode bypass. Deliver a fake-JWT minting script for local development. Unblock TP MCP P2's stub swap (rebuild risk register R-002).

**Architecture:** `pyjwt[crypto]` for signature verification; `httpx` for JWKS fetch; in-process TTL cache with async lock; ASGI middleware attaches `UserContext` to `scope["user_context"]`; `EnvDevAuth` mode swaps JWKS for a checked-in fixture.

**Tech Stack:** Python 3.10–3.14, `pyjwt[crypto]` ≥2.8, `httpx` ≥0.27, `cryptography` ≥42 (bundled with pyjwt[crypto]), `pytest-asyncio`, `respx`, `freezegun`.

**Estimated effort:** 3 working days.

---

## Prerequisites

- CLK-0 DONE; handoff `CLK-0-to-CLK-1.md` readable.
- TP MCP P0 scaffolding must exist OR this phase bootstraps a minimal `tp_mcp/auth/` package and tests into the existing repo. (If TP MCP P0 hasn't landed, CLK-1 files go into the existing `trainingpeaks-mcp/src/tp_mcp/` layout; they will migrate during TP MCP P1/P2.)
- Python ≥3.10 installed locally with `uv` or `pip` for dependency management.

---

## Tasks

### Task 1 — Dependencies

- [ ] 1.1 Add to `pyproject.toml` (or `jarasport-tp-mcp` equivalent when scaffolded):
  ```toml
  [project]
  dependencies = [
    "pyjwt[crypto]>=2.8,<3",
    "httpx>=0.27,<1",
  ]
  [project.optional-dependencies]
  dev = [..., "respx>=0.21", "freezegun>=1.5"]
  ```
- [ ] 1.2 Regenerate lockfile (`uv lock` or `pip-compile`).
- [ ] 1.3 Commit with message `chore(deps): add pyjwt + respx + freezegun for CLK-1`.

### Task 2 — `UserContext` dataclass (TDD)

- [ ] 2.1 Write `tests/tp_mcp/test_auth_context.py` — failing test: construct `UserContext(user_id="u_1", email="a@b", org_id=None, org_role=None, plan="annual", tp_connected=False, request_id="r_1")`, assert immutability (try setattr, expect `FrozenInstanceError`).
- [ ] 2.2 Create `src/tp_mcp/auth/__init__.py` (empty).
- [ ] 2.3 Create `src/tp_mcp/auth/context.py` with `UserContext` frozen dataclass per CLK spec §Backend. Include docstring referencing ADR-0001 §Wire format.
- [ ] 2.4 Run test; green.
- [ ] 2.5 Commit: `feat(auth): add UserContext dataclass`.

### Task 3 — JWKS cache (TDD)

- [ ] 3.1 Write `tests/tp_mcp/test_auth_jwks_cache.py`:
  - Fetch on miss, serve from cache on hit.
  - TTL expiry triggers refetch.
  - Concurrent requests during miss hit httpx once (async lock).
  - On refresh failure, serves stale for up to 24h with a WARN log.
  - On refresh failure beyond 24h stale window, raises `JWKSUnavailableError`.
  - Use `respx` to stub `https://…/.well-known/jwks.json`; `freezegun` for TTL.
- [ ] 3.2 Create `src/tp_mcp/auth/jwks_cache.py`:
  - `class JWKSCache` with `async get_key(kid: str) -> PublicKey`.
  - In-process dict keyed by JWKS URL → `{keys, fetched_at, etag}`.
  - `asyncio.Lock` per URL.
  - Default TTL 600s; stale-serve 86400s.
  - Emits `structlog` events (fetch_start, fetch_ok, fetch_error, serving_stale).
- [ ] 3.3 Run tests; green. Coverage ≥90%.
- [ ] 3.4 Commit: `feat(auth): add JWKS cache with stale-serve fallback`.

### Task 4 — JWT verification function (TDD)

- [ ] 4.1 Write `tests/tp_mcp/test_auth_clerk.py` with fixtures:
  - `tests/fixtures/jwks-dev.json` — checked-in JWKS with kid `dev-key-001`.
  - `tests/fixtures/dev-private-key.pem` — matching private key (DO NOT use this key in prod).
  - `make_fake_jwt(**claims)` helper that signs with the dev private key.
- [ ] 4.2 Test cases, each producing the correct rejection code per ADR-0001:
  - Happy path: valid JWT → returns `UserContext`.
  - Missing token → `unauthorized.missing_token`.
  - Bad signature → `unauthorized.bad_signature`.
  - Expired → `unauthorized.expired` (use `freezegun`).
  - Not-yet-valid → `unauthorized.not_yet_valid`.
  - Wrong `iss` → `unauthorized.wrong_issuer`.
  - Wrong `azp` → `unauthorized.wrong_azp`.
  - Unknown `kid` → `unauthorized.unknown_kid`.
  - Missing required claim → `unauthorized.malformed_claims`.
  - RS256-only: HS256-signed token → `unauthorized.bad_signature`.
- [ ] 4.3 Create `src/tp_mcp/auth/clerk.py`:
  - `class ClerkJWTVerifier(jwks_url: str, expected_iss: str, expected_azp: set[str])`.
  - `async verify(token: str) -> UserContext`.
  - Uses `pyjwt.decode` with `algorithms=["RS256"]`, `audience=None` (we verify `azp` manually for flexibility), `options={"require": ["iss", "sub", "exp", "nbf", "iat", "azp"]}`.
  - 30s clock skew via `leeway`.
  - Raises `UnauthorizedError(reason: str)` with machine-readable reason codes.
- [ ] 4.4 Run tests; all 10 cases green. Coverage ≥90%.
- [ ] 4.5 Commit: `feat(auth): add Clerk JWT verifier with structured rejection codes`.

### Task 5 — ASGI middleware (TDD)

- [ ] 5.1 Write `tests/tp_mcp/test_auth_middleware.py`:
  - Valid JWT → middleware sets `scope["user_context"]`, passes to next.
  - No Authorization header → 401 with JSON error body `{"error": "unauthorized", "reason": "missing_token"}`.
  - Malformed Authorization header → 401.
  - Verifier raises `UnauthorizedError` → 401 with matching reason.
- [ ] 5.2 Create `src/tp_mcp/auth/middleware.py`:
  - `class ClerkAuthMiddleware(app, verifier)`.
  - Reads `Authorization: Bearer <token>` from ASGI scope headers.
  - On success: attach `UserContext` at `scope["user_context"]`, `request_id = uuid4().hex`, call `await self.app(scope, receive, send)`.
  - On failure: send 401 JSON response, close early.
  - Never logs the raw token.
- [ ] 5.3 Run tests; green.
- [ ] 5.4 Commit: `feat(auth): add ClerkAuthMiddleware with structured 401 errors`.

### Task 6 — `EnvDevAuth` bypass (TDD)

- [ ] 6.1 Write `tests/tp_mcp/test_auth_env_dev.py`:
  - `TP_MCP_AUTH_IMPL=env` + `CLERK_ENV=dev` → uses fixture JWKS, accepts fake JWT.
  - `TP_MCP_AUTH_IMPL=env` + `CLERK_ENV=prod` → raises `DevAuthDisallowedError` at startup.
  - Absent env var → uses prod JWKS URL.
- [ ] 6.2 Create `src/tp_mcp/auth/env_dev.py`:
  - Factory function `build_verifier(settings) -> ClerkJWTVerifier`.
  - In dev mode: JWKS URL is `file://…tests/fixtures/jwks-dev.json`; `expected_iss` is a dev-only value `https://dev.clerk.local`.
  - In prod mode: JWKS URL and iss come from env.
  - Raises `DevAuthDisallowedError` if `env=prod` and `TP_MCP_AUTH_IMPL=env`.
- [ ] 6.3 Run tests; green.
- [ ] 6.4 Commit: `feat(auth): add EnvDevAuth for local development`.

### Task 7 — `scripts/fake-jwt.py` helper

- [ ] 7.1 Create `scripts/fake-jwt.py`:
  - Argparse: `--sub`, `--email`, `--plan`, `--tp-connected`, `--ttl`, `--org-id`, `--org-role`.
  - Signs with `tests/fixtures/dev-private-key.pem`.
  - Prints the JWT to stdout.
  - Includes a `--help` example showing curl usage.
- [ ] 7.2 Write `tests/test_scripts_fake_jwt.py`:
  - Generated token verifies against the dev JWKS.
  - Default TTL is 3600s (longer than prod 60s because dev).
- [ ] 7.3 Add entry to `pyproject.toml` scripts section: `tp-mcp-fake-jwt = "scripts.fake_jwt:main"`.
- [ ] 7.4 Run test; green.
- [ ] 7.5 Commit: `feat(scripts): add fake-jwt minting helper for dev mode`.

### Task 8 — Performance benchmark

- [ ] 8.1 Write `tests/test_auth_benchmark.py` using `pytest-benchmark`:
  - Benchmark `ClerkJWTVerifier.verify()` with JWKS cache hit; assert p95 < 5ms.
  - Benchmark with cache miss (one httpx call); assert p95 < 150ms.
- [ ] 8.2 Capture baseline in `tests/benchmarks/clk1-baseline.json`.
- [ ] 8.3 CI: mark benchmark tests with `@pytest.mark.benchmark`; fail if p95 cache-hit exceeds 5ms by >20%.
- [ ] 8.4 Commit: `test(auth): benchmark JWT verification latency`.

### Task 9 — Integration: mount middleware on a canary FastAPI route

- [ ] 9.1 Create a temp harness `examples/auth_demo.py`:
  - Tiny FastAPI app.
  - `ClerkAuthMiddleware` mounted.
  - One route `/hello` that reads `scope["user_context"]` and returns `{"user_id": ctx.user_id}`.
- [ ] 9.2 Write `tests/test_auth_integration.py`:
  - Mint fake JWT via helper.
  - `httpx.AsyncClient` hits `/hello`.
  - Assert 200 and correct `user_id`.
  - Assert 401 without header.
- [ ] 9.3 Commit: `feat(examples): add auth demo integration test`.

### Task 10 — Documentation

- [ ] 10.1 Create `docs/auth.md` covering:
  - JWT verification flow diagram (ASCII).
  - Dev mode quickstart (`export TP_MCP_AUTH_IMPL=env`, mint a fake JWT, curl).
  - Prod config env vars: `CLERK_FRONTEND_API`, `CLERK_JWKS_URL`, `CLERK_EXPECTED_AZP_PROD`, `CLERK_EXPECTED_AZP_STAGING`.
  - Link to ADR-0001.
- [ ] 10.2 Update `README.md` with a three-line pointer to `docs/auth.md`.
- [ ] 10.3 Commit: `docs(auth): CLK-1 quickstart and config reference`.

### Task 11 — Handoff: CLK-1 → CLK-2

- [ ] 11.1 Create `HANDOFFS/CLK-1-to-CLK-2.md`:
  - `UserContext` fields (copy dataclass signature).
  - Middleware mount point (`scope["user_context"]`).
  - Error body format.
  - How CLK-2 routes access the context (receive `Request` from FastAPI → read from `request.scope`).

### Task 12 — Handoff: CLK-1 → TP MCP P2

- [ ] 12.1 Create `HANDOFFS/CLK-1-to-P2.md`:
  - `ClerkJWTVerifier` public API.
  - Dev-mode contract (`EnvDevAuth` activation conditions).
  - Fake-JWT helper CLI usage.
  - How P2 replaces its `StubClerkAuth`: drop-in replacement of a single factory function.
  - R-002 can be marked CLOSED in the TP MCP master risk register once P2 lands CLK-1.

### Task 13 — Master plan + TP MCP master plan updates

- [ ] 13.1 CLK master §1: CLK-1 `IN PROGRESS` → `DONE — UNVERIFIED` → `DONE` (with DoD sign-off).
- [ ] 13.2 CLK master §3: release claim.
- [ ] 13.3 CLK master §11: ledger row.
- [ ] 13.4 CLK master §6 Interface Inventory: check off `auth/clerk.py`, `auth/context.py`, `auth/middleware.py`, `auth/env_dev.py`, `scripts/fake-jwt.py`.
- [ ] 13.5 TP MCP master §1: CLK row status if changed; §4 CLK-to-P2 handoff status `not written` → `written`; §7 R-002 status update.

---

## DoD (extends master §5)

- [ ] Universal DoD green.
- [ ] `verify_jwt()` p95 < 5ms JWKS-hit.
- [ ] All ADR-0001 rejection codes exercised in tests.
- [ ] Integration test green against fake JWT via helper.
- [ ] `EnvDevAuth` refuses to load in `CLERK_ENV=prod`.
- [ ] TP MCP master §1 CLK-to-P2 unblocker ready (P2 can swap stub in a 1-day session).

---

## Handoff Outputs

1. `HANDOFFS/CLK-1-to-CLK-2.md`
2. `HANDOFFS/CLK-1-to-P2.md`
3. `docs/auth.md`
4. Benchmark baseline `tests/benchmarks/clk1-baseline.json`

---

## Exit Criteria

- All 13 tasks checked off.
- DoD green.
- Master plan §9 sign-off appended.
- Both handoff files committed.

Next phase: **CLK-2** unblocks.
