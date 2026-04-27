---
title: jarasport-tp-mcp — Commercial-Grade Rebuild
date: 2026-04-25
author: Jara
status: approved
type: design-spec
supersedes: upstream fork jara-r-k/trainingpeaks-mcp
---

# jarasport-tp-mcp — Commercial-Grade Rebuild

## Context

`jara-r-k/trainingpeaks-mcp` is a fork of `JamsusMaximus/trainingpeaks-mcp`. As of 2026-04-25 the fork is 13 commits ahead and 39 commits behind upstream, carries Jarasport-specific customisations (pretext cache, prepare/compute splits, fitness None handling, benchmarks), and is not the user's project to govern.

The root cause is governance: there is no maintenance strategy, no upstream-sync cadence, and no path to commercial deployment. The fork also inherits upstream's architectural choices that do not meet commercial-grade requirements — local cookie-based auth only, stdio-only transport, no multi-tenancy, no observability spine, no release automation.

This spec replaces the fork with a clean, owned, commercial-grade rebuild named `jarasport-tp-mcp`. Auth identity is handled by Clerk; detailed Clerk wiring is being addressed in a separate session. This spec defines the contract that session must fulfil.

## Non-Goals

- Contributing back to `JamsusMaximus/trainingpeaks-mcp` (that fork remains its own project).
- Lobbying TrainingPeaks for an official partner API (open question, not in scope).
- Supporting every TP endpoint — scope is feature-parity with the 52 tools currently exposed.
- Building a UI. This is a backend service + MCP surface.

## Product Definition

- **Name**: `jarasport-tp-mcp`
- **PyPI**: `jarasport-tp-mcp`
- **Container**: `ghcr.io/jara-r-k/jarasport-tp-mcp:vX.Y.Z`
- **Licence**: MIT
- **Primary consumer**: Race Day Hub (RDH) cloud sync
- **Secondary**: Claude Code direct (via HTTP/SSE or stdio for local dev)
- **Future**: SaaS surface for external athletes/coaches under Jarasport
- **Support matrix**: Python 3.10 → 3.14

## Architecture

Two separable layers. `tp_core` is a pure TP client library with no MCP coupling. `tp_mcp` is a thin adapter that exposes `tp_core` over the MCP protocol.

```
tp_core/                    # Pure TP client — user-agnostic, independently usable
  auth/
    provider.py             # AuthProvider abstract base
    cookie_jwt.py           # Cookie → JWT exchange (TP's internal flow)
    token_cache.py          # Async-lock-safe token cache, 60s refresh buffer
  http/
    client.py               # httpx wrapper
    rate_limiter.py         # Token bucket, per-endpoint override
    retry.py                # Exponential backoff + jitter, bounded
    circuit_breaker.py      # Open/half-open/closed state machine
  cache/
    tiered.py               # Memory (LRU) + optional disk tier
    keys.py                 # Deterministic key generation
    ttl.py                  # Per-endpoint TTL policy
  models/
    base.py                 # Pydantic v2 base, extra='ignore'
    workout.py              # WorkoutSummary, WorkoutDetail, Structure
    fitness.py
    event.py
    equipment.py
    ...
  endpoints/
    workouts.py             # One module per TP API domain
    fitness.py
    events.py
    ...

tp_mcp/                     # MCP adapter — thin, swappable
  transport/
    http_sse.py             # Primary: HTTP/SSE per MCP spec
    stdio.py                # Local-dev fallback
  auth/
    clerk.py                # Clerk JWT verification (JWKS cache)
    middleware.py           # Per-request auth → user context
    context.py              # UserContext propagation
  credentials/
    store.py                # CredentialStore abstract base
    sqlite.py               # Dev backend
    postgres.py             # Prod backend
    encryption.py           # libsodium/age wrapper
  tools/
    __init__.py             # Tool registry
    _base.py                # Base handler, pulls TPClient from UserContext
    workouts.py             # One file per tool, 52 total
    ...
  schemas/
    workouts.py             # Input+output JSON Schema per tool
    ...
  observability/
    logging.py              # structlog JSON, PII scrub middleware
    tracing.py              # OpenTelemetry
    metrics.py              # Prometheus exporter
  server.py                 # Composition root
  cli.py                    # tp-mcp serve|migrate|healthcheck|auth-import
```

**Key invariants:**
1. `tp_core` never imports from `tp_mcp`. Dependency flows one way.
2. One tool = one file in `tp_mcp/tools/`. New tools add files, never modify existing ones.
3. Every tool handler receives a user-scoped `TPClient` from `UserContext`. No global TP client.
4. Cookies and JWTs never appear in logs or tool output. Enforced by middleware and CI scan.

## Auth

### Identity Layer — Clerk

Every MCP request over HTTP/SSE carries a Clerk JWT in `Authorization: Bearer <token>`. A middleware verifies the JWT against Clerk's JWKS (cached with TTL), extracts `user_id`, `session_id`, and claims, and attaches them to the request's `UserContext`.

Full Clerk SDK integration, webhook handling, sign-in/sign-up flows, and RDH↔MCP session linkage are owned by the separate Clerk session. This spec treats Clerk as an opaque JWT issuer and defines the boundary in ADR-0001 (see Docs).

### TP Credential Layer

Per-user TrainingPeaks cookies are encrypted at rest in a `CredentialStore`, keyed by Clerk `user_id`. The cookie-to-JWT exchange described in upstream's `RESEARCH.md` still happens — but per-user, triggered on demand by the `AuthProvider` when a tool handler needs an authenticated TP client.

**Storage backends:**
- **Dev**: SQLite with libsodium-encrypted blobs. Key from env var.
- **Prod**: Postgres with encryption key wrapped by AWS KMS (or 1Password Connect / GCP KMS depending on deploy target). Decision captured in ADR-0002.

**Onboarding flow:**
1. User authenticates to Jarasport via Clerk (out of scope for this spec).
2. User visits a "Connect TrainingPeaks" view (owned by RDH / Clerk session).
3. Either (a) uploads their TP cookie manually, or (b) runs a helper `tp-mcp auth-import --from-browser chrome` locally and POSTs the resulting cookie to the MCP's `/credentials` endpoint.
4. MCP encrypts and stores the cookie, keyed by `user_id`. Plaintext is discarded immediately.
5. Subsequent tool calls decrypt the cookie per-request, exchange for JWT, cache the JWT in-memory (per-user, with async lock), invalidate on 401.

### AuthProvider Implementations

- `ClerkUserAuth(credential_store, token_cache)` — production path. Given a `user_id` from the Clerk JWT, fetches that user's TP cookie from the store, exchanges for JWT, caches.
- `EnvDevAuth(cookie_env_var)` — local-dev-only bypass. Reads cookie from env. Disabled in production by a build-time flag.

### Hard Rules

- **No secret in logs.** A structured-logging PII-scrub middleware drops keys named `cookie`, `token`, `authorization`, `jwt`, `access_token` from every log record. A CI job greps the codebase for literal `print(` / `logger.*(.*cookie` patterns and fails.
- **No secret in tool output.** A tool-result sanitiser runs before returning to the client. Any matching key pattern is redacted.
- **Token cache is per-user.** No cross-user leakage. Verified by integration test.
- **Credential store never returns plaintext outside the process.** No API returns a cookie; only opaque handles or "exists/doesn't exist" booleans.

## Transport

- **HTTP/SSE** — primary, per MCP spec. Authenticated via Clerk JWT. Supports streaming for long operations (e.g., bulk workout export).
- **stdio** — local-dev only. Uses `EnvDevAuth` or a single-user `CredentialStore`. Not exposed in prod container.
- **Future**: WebSocket if MCP spec adds it.

Transport is abstracted behind a `Transport` interface in `tp_mcp/transport/`. Adding a new transport should not touch tool code.

## Reliability & Observability

### Reliability

- **Rate limit**: Token bucket, 100/min default (empirically calibrated, see upstream RESEARCH.md). Per-endpoint overrides via config. Enforced client-side in `tp_core/http/rate_limiter.py`.
- **Retry**: Exponential backoff with jitter. Bounded to 3 attempts. Only retries on 5xx responses, connection errors, and timeouts. Never retries on 4xx (auth errors surface immediately).
- **Circuit breaker**: Opens after 5 consecutive 5xx responses from TP. Half-open probe after 30s. Closed again on successful response. Prevents hammering TP during outages.
- **Timeouts**: Connect 5s, read 30s, total 60s. Configurable per endpoint.
- **Graceful degradation**: If circuit is open, return a structured `TPUnavailable` error to the MCP client rather than hanging.

### Observability

- **Logging**: `structlog` with JSON output. Every log line carries `user_id` (hashed), `request_id`, `tool_name`. PII-scrub middleware strips auth secrets.
- **Tracing**: OpenTelemetry. Spans: MCP request → auth → credential fetch → TP HTTP call → response parse. Traces propagate to the MCP client via context.
- **Metrics**: Prometheus-compatible. Exported at `/metrics`:
  - `tp_mcp_requests_total{tool, user_bucket, status}`
  - `tp_mcp_request_duration_seconds{tool, quantile}` (p50/p95/p99)
  - `tp_cache_hits_total{tier, endpoint}` / `tp_cache_misses_total{tier, endpoint}`
  - `tp_http_errors_total{status_code, endpoint}`
  - `tp_auth_refreshes_total{user_bucket}`
  - `tp_circuit_breaker_state{endpoint}`
- **Health**: `tp_health` MCP tool + `/health` HTTP endpoint + `tp-mcp healthcheck` CLI. Checks: DB reachable, Clerk JWKS reachable, TP DNS resolves, token cache responsive.

## Testing Strategy

A commercial-grade pyramid. Every layer has a coverage gate enforced in CI.

### Unit Tests

- **Target**: ≥90% line coverage, ≥85% branch coverage.
- **Scope**: Every tool handler, every parser, every validator, every pure function in `tp_core`.
- **Framework**: `pytest` + `pytest-asyncio` (`asyncio_mode=auto`).
- **Auth**: All TP calls mocked. No real TP API in CI.

### Contract Tests

- **Target**: 100% of tools have a contract test.
- **Scope**: Every tool's input JSON Schema validates correctly; every output matches its declared schema via Pydantic roundtrip.
- **Purpose**: Breaks if a tool's output drifts from its declared schema. Prevents silent contract changes.

### Integration Tests

- **Framework**: `respx` for mocking `httpx` + recorded VCR cassettes (`pytest-vcr`) for real TP response shapes captured once against a synthetic test account.
- **Scope**: End-to-end MCP request → tool → TP client → response parse → tool output. Uses in-memory SQLite `CredentialStore` + fake Clerk JWT fixtures.
- **Cassettes**: Recorded once, scrubbed of all secrets before commit. CI replays; never hits real TP.

### Property-Based Tests

- **Framework**: `hypothesis`.
- **Scope**: Parsers in `tp_core/models/`. Generates random field shapes (missing fields, wrong types, null values, extra fields) to catch `Optional` gaps. Directly addresses the "field shape varies by sport/tier" gotcha from upstream's RESEARCH.md.

### Smoke Tests

- **Tag**: `@smoke`. Not run in CI.
- **Trigger**: Manual via `make smoke` or a dedicated GitHub Actions workflow with manual dispatch + secret gating.
- **Scope**: A handful of critical paths against a real synthetic TP test account. Confirms real-world behaviour before release.

### Benchmarks

- **Framework**: `pytest-benchmark`.
- **Scope**: Each tool has a budget (wall-clock, memory). Regressions >20% fail CI.
- **Baseline**: Captured once from the current fork, tracked in `tests/benchmarks/baseline.json`.

### Security Tests

- **`bandit`**: Static analysis, fails on medium+ findings.
- **`pip-audit`**: Dependency vulnerability scan.
- **`trivy`**: Container image scan.
- **`gitleaks`**: Pre-commit hook + CI scan for committed secrets.
- **Custom log-safety test**: Automated test that runs every tool with a known secret in the credential store, captures all log output and tool output, asserts the secret does not appear.

### Mutation Tests (stretch)

- **Framework**: `mutmut` on `tp_core` hot paths (parsers, auth, rate limiter).
- **Target**: ≥75% mutation score on `tp_core/auth/` and `tp_core/models/`.

## CI/CD & Supply Chain

### Continuous Integration

GitHub Actions matrix across Python 3.10, 3.11, 3.12, 3.13, 3.14. Gates run in sequence; a failure at any gate fails the build:

1. `ruff check` + `ruff format --check`
2. `mypy --strict`
3. `pytest` with coverage gate (≥90% line, ≥85% branch)
4. `pytest` contract tests
5. `pytest -k property`
6. `bandit -ll` (medium+)
7. `pip-audit --strict`
8. `gitleaks detect`
9. Build wheel + sdist
10. Build container, `trivy image --severity HIGH,CRITICAL`

### Release

- **Trigger**: Git tag matching `v*.*.*`.
- **Tool**: `semantic-release` (or `release-please`) — generates changelog from conventional commits, bumps version, creates GitHub Release.
- **Artefacts**:
  - Wheel + sdist to PyPI.
  - OCI image to `ghcr.io/jara-r-k/jarasport-tp-mcp`.
  - SBOM (CycloneDX) attached to the release.
  - Sigstore/cosign signatures on wheel and image.

### Versioning

- **SemVer** strictly. Breaking changes → major bump. New tools or opt-in fields → minor. Bug fixes → patch.
- **Tool schema versioning**: Each tool declares a `schema_version`. Clients can inspect. Removal/rename requires a deprecation window of one minor release.
- **CHANGELOG**: `keep-a-changelog` format, auto-generated from commits.

### Supply Chain

- **Dependencies**: Pinned via `uv` lock. Renovate PRs grouped weekly; security fixes auto-merged after CI green.
- **No post-install scripts.** `pip install` must not execute arbitrary code.
- **Minimal attack surface**: Container uses `python:3.12-slim` base, runs as non-root UID, read-only root filesystem, drops all capabilities.
- **Repro builds**: `SOURCE_DATE_EPOCH` respected, deterministic wheel builds.

## Deployment

**Target**: Fly.io or Google Cloud Run for the stateless MCP service; managed Postgres for the credential store.

**Shape**:
- Stateless containers, horizontal scale behind a load balancer.
- Postgres with encryption at rest + KMS-wrapped column encryption for credential blobs.
- Secrets (KMS key, Clerk signing keys, DB password) via the platform's secret store — never in env vars baked into the image.
- HTTP only; TLS terminated by the platform.

**Resilience**:
- Readiness probe on `/health`. Liveness probe on `/health/live` (cheaper check).
- Graceful shutdown: drain in-flight requests, flush traces, close DB pool.
- DB connection pool sized to container concurrency.

**Observability plumbing**:
- Logs shipped to the platform log aggregator (JSON format).
- Metrics scraped by Prometheus or platform-native (Cloud Monitoring / Fly metrics).
- Traces exported to an OTLP collector (Honeycomb / Grafana Tempo / platform default).

## Documentation

- `README.md` — quickstart, for both RDH integrators and Claude Code users.
- `ARCHITECTURE.md` — this spec, distilled.
- `THREAT_MODEL.md` — STRIDE analysis. Focus on credential theft, JWT replay, cross-user data leaks, TP cookie harvesting.
- `SECURITY.md` — vulnerability disclosure, CVE process.
- `CONTRIBUTING.md` — commit conventions, test requirements, PR checklist.
- `RUNBOOK.md` — operator procedures: credential rotation, Clerk JWKS rotation, DB backup/restore, incident response, scaling.
- `docs/adr/` — Architecture Decision Records:
  - ADR-0001: Clerk as identity provider; boundary with MCP (contract with other session)
  - ADR-0002: Prod credential-store backend (Postgres + KMS vs secrets manager)
  - ADR-0003: Transport choice (HTTP/SSE primary, stdio dev)
  - ADR-0004: Rate-limit calibration and circuit-breaker thresholds
- `docs/api/` — auto-generated from Pydantic input/output schemas.

## Phase Breakdown

Each phase gets its own implementation plan file when executed. Dependencies are sequential unless noted.

| Phase | Scope | Est. | Depends on |
|-------|-------|-----:|------------|
| **P0** | Scaffold: repo, package layout, lint/type/test skeleton, pre-commit hooks, CI skeleton, licensing, CONTRIBUTING, Dockerfile, dev SQLite store scaffolding | 4 d | — |
| **P1** | `tp_core`: AuthProvider abstract, cookie→JWT exchange, token cache (race-safe), HTTP client, rate limiter, retry, circuit breaker, tiered cache, Pydantic models, endpoint modules | 5 d | P0 |
| **P2** | `tp_mcp` shell: HTTP/SSE transport, stdio transport, Clerk JWT middleware (stub — wires to other session), UserContext propagation, CredentialStore abstract + SQLite impl + encryption, tool registry, JSON Schema plumbing, error taxonomy, observability spine | 5 d | P1 |
| **P3** | Tool migration: port all 52 tools to new surface with typed I/O, unit tests, contract tests, property tests on parsers, integration VCR cassettes. Tools pull `TPClient` from `UserContext` | 10 d | P2 |
| **P4** | Reliability & observability: OpenTelemetry wiring, Prometheus exporter, PII-scrub middleware, health tool + endpoint, rate-limit tuning, circuit-breaker tuning | 4 d | P3 |
| **P5** | Release & supply chain: semantic-release, PyPI publish, ghcr.io publish, cosign signing, SBOM, deploy pipeline (Fly.io or Cloud Run), Postgres migration, KMS wiring | 4 d | P4 |
| **P6** | Docs: ARCHITECTURE, THREAT_MODEL, SECURITY, CONTRIBUTING, RUNBOOK, ADRs 1–4, auto-generated API reference | 3 d | P5 (partial parallel) |
| **P7** | RDH cutover: bridge config flag in RDH, feature-parity test suite runs against both old fork and new service, cutover default after 14 days clean, archive old fork with README pointing to new package | 3 d | P5 + other session complete |

**Total**: ~38 working days (~7–8 weeks solo). P4–P6 can run partly in parallel.

## Interface Contracts

### Contract with Clerk Session (other session)

The other session owns:
- Clerk SDK integration in Jarasport frontend.
- Sign-in / sign-up flows.
- Session linkage between Jarasport web app and the MCP service.
- The "Connect TrainingPeaks" UI.
- Clerk webhook handling for user lifecycle events.

This spec owns:
- Clerk JWT verification middleware inside `tp_mcp/auth/clerk.py`.
- `UserContext` extraction and propagation.
- `CredentialStore` API (`get`, `put`, `delete`, `exists`).
- `/credentials` POST endpoint for TP cookie upload.

**Boundary API** (what the other session can rely on):

```
POST /credentials
  Headers: Authorization: Bearer <clerk-jwt>
  Body: { "tp_cookie": "<cookie-value>" }
  Returns: 204 No Content on success, 401 on bad JWT, 400 on bad cookie

DELETE /credentials
  Headers: Authorization: Bearer <clerk-jwt>
  Returns: 204 No Content

GET /credentials/status
  Headers: Authorization: Bearer <clerk-jwt>
  Returns: { "connected": bool, "cookie_age_days": int | null, "last_refresh_at": iso8601 | null }

(All MCP tool endpoints)
  Headers: Authorization: Bearer <clerk-jwt>
  The JWT's user_id selects which user's TP credentials are used.
```

ADR-0001 captures this contract so both sessions stay aligned.

### Contract with RDH (consumer)

RDH currently consumes the old fork via stdio + local keyring. Migration:

1. RDH adds env flag `TP_MCP_IMPL=legacy|jarasport`.
2. While `legacy`: unchanged (current behaviour).
3. While `jarasport`: RDH calls the new HTTP/SSE endpoint with the Clerk JWT it already has (since RDH uses Clerk).
4. Feature-parity suite runs against both in CI until cutover.
5. Flip default after 14 days clean running in production.
6. Remove `legacy` codepath one minor release later.

## Success Criteria

Program-level gates that must all pass before declaring this complete:

1. **Feature parity**: All 52 tools reproduced with identical observable behaviour. Parity matrix in `docs/parity.md` green across the full row.
2. **Coverage**: Unit ≥90% line / ≥85% branch; contract coverage = 100% of tools; integration covers every tool's happy path.
3. **CI matrix green** on Python 3.10, 3.11, 3.12, 3.13, 3.14.
4. **Performance**: Benchmarks within 20% of current fork baseline (`tests/benchmarks/baseline.json`).
5. **Security**: Automated scan confirms zero cookie/JWT in any log line or tool output (tested via the custom log-safety test with a plant secret).
6. **Isolation**: Integration test proves user A cannot access user B's TP data via any known path (JWT swap, user_id injection, cache bleed).
7. **Release**: Signed release on PyPI + ghcr.io, SBOM attached, CHANGELOG complete.
8. **Deployed**: Running on target platform with health green for 14 days.
9. **Migrated**: RDH cutover complete, `TP_MCP_IMPL=jarasport` default, old fork archived with deprecation README pointing to new package.
10. **Clerk JWT verification p95 <5ms** (JWKS cached).

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| TP changes internal API, breaks cookie→JWT exchange | All tools fail | Circuit breaker + alert; monitor 404s on known endpoints; weekly synthetic probe |
| Clerk integration session slips | P2 blocked on the middleware stub | P2 ships stub `ClerkUserAuth` returning a fake user_id; real wiring becomes a one-day swap once other session lands |
| Postgres KMS integration is platform-specific | P5 effort higher than estimated | ADR-0002 picks the backend early; SQLite covers dev until then |
| Migration period produces divergent behaviour | RDH bugs | Parity suite runs against both impls in CI; flag-gated rollout; rollback via env flag flip |
| Credential-store encryption key lost | All users must re-authenticate | Key escrow via KMS; documented recovery runbook; encryption key rotation procedure in RUNBOOK |
| Rate limits tighter than 100/min in practice | Throttling | Empirical calibration in P4; per-endpoint overrides; bulk endpoints use explicit batching |
| Supply-chain compromise (dep takeover) | Malicious code in prod | Pinned deps, Renovate with CI gates, cosign verification, no post-install scripts |

## Open Questions (deferred, not blocking)

- Should `tp_core` ship as a separately published package for reuse? Defer until post-P5; add as a minor release if demand appears.
- Should we pursue official TP partner API? Long-term strategic question — revisit at one-year review.
- Rate-limit tuning — adaptive (observes 429s and backs off) vs fixed? Start fixed in P4, add adaptive in a later minor release if needed.
- Mutation testing coverage target — chosen 75% as stretch; revisit after P3 data.
