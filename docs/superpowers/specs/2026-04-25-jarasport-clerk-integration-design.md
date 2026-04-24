---
title: jarasport-clerk-integration — Identity Layer Design
date: 2026-04-25
author: Jara
status: approved
type: design-spec
supersedes: Jarasport Wix-Members-only auth bridge
companion: 2026-04-25-jarasport-tp-mcp-design.md
---

# jarasport-clerk-integration — Identity Layer Design

## Context

The Jarasport product surface (Race Day Hub frontend + `jarasport-tp-mcp` backend) currently has two structurally incompatible auth models:

- **RDH today** authenticates via Wix Members → access-code → app token, bridged in `src/services/wixBridge.ts`. Wix Pricing Plans handles billing. This is tightly coupled to Wix as an IdP.
- **`jarasport-tp-mcp`** (in-progress clean rebuild, [spec](2026-04-25-jarasport-tp-mcp-design.md)) requires a Clerk JWT on every MCP request, with per-user TrainingPeaks credentials stored server-side keyed by Clerk `user_id`.

The rebuild spec (§"Interface Contracts > Contract with Clerk Session") defers the full Clerk integration to "a separate session" — this spec is that session. It was previously scoped server-side only; this revision (user-approved Option 3) expands it to cover **both sides of the identity boundary end-to-end**: frontend Clerk SDK, backend JWT verification, credential store, webhooks, Wix coexistence, and migration of existing access-code users.

Without this work:
- `jarasport-tp-mcp` P2 cannot ship a real middleware (blocked on a Clerk JWKS URL and expected-claims contract).
- RDH has no end-user surface to exercise the `/credentials` endpoint.
- Access-code users cannot migrate to the new MCP without an identity migration path.

## Non-Goals

- Replacing Wix as the **billing** system. Wix Pricing Plans continues to handle subscriptions; Clerk picks up identity only. Plan entitlement flows from Wix → Clerk metadata via a thin sync route.
- Replacing Wix as the **CMS**. AccessCodes and AthleteProfiles collections remain authoritative for the data they currently own; migration is additive, not destructive.
- Building a full B2B org/team UX. The JWT claim `org_id` is provisioned but the coach-to-athletes org model UI ships in a later RDH workstream, not here.
- Federated SSO with KPMG or external IdPs. Clerk's built-in providers (email, Google, Apple) cover the current user base.
- Running our own OAuth server. Clerk is the issuer; we verify JWTs, we do not mint them.

## Product Statement

- **Name**: CLK (Clerk identity track) — parallel to the `jarasport-tp-mcp` rebuild.
- **Scope**: End-to-end Clerk integration for the Jarasport product, covering both `Race Day Hub` frontend and `jarasport-tp-mcp` backend, with a migration path for existing Wix-Members access-code users.
- **Primary consumers**: Race Day Hub users (athletes + coaches), and `jarasport-tp-mcp` as the authenticated service.
- **Success criteria**: The rebuild's P2 unblocks on a real JWT (stub removed), RDH sign-in runs via Clerk, and a user can complete "sign up → connect TrainingPeaks → call an MCP tool" end-to-end, with Wix billing intact.

## Architecture

### Topology

```
┌──────────────── Jarasport Race Day Hub (Vercel) ───────────────────┐
│  <ClerkProvider publishableKey env>                                │
│    ├── Public routes (marketing handoff, sign-in, sign-up)         │
│    ├── <SignedIn> routes: dashboard, connect-tp, profile           │
│    ├── <SignedOut> → redirect to /sign-in                          │
│    └── useAuth().getToken() ─► Authorization: Bearer <Clerk JWT>   │
└────────────────────────────────────────────────────────────────────┘
                │                                     │
                │ Clerk Frontend API                  │
                ▼                                     ▼
        ┌───────────────┐                   ┌──────────────────────┐
        │ Clerk tenant  │──webhooks (Svix)─►│ jarasport-tp-mcp     │
        │ JWKS endpoint │                   │  /webhooks/clerk     │
        └───────┬───────┘                   │                      │
                │ JWKS (JWT verify keys)    │  /auth/clerk.py      │
                └───────────────────────────┤  /credentials/*      │
                                            │  CredentialStore     │
                                            └──────────────────────┘
```

### Package layout changes

**Race Day Hub (`Jarasport/Race Day Hub/src/`)** — additive, not rewrite:

```
src/
├── auth/                          # NEW: Clerk wrapper + API helpers
│   ├── ClerkProviderWrapper.tsx   # ClerkProvider + router bridge
│   ├── ProtectedRoute.tsx         # <SignedIn> guard with redirect
│   ├── useApi.ts                  # fetch with Clerk bearer token
│   └── sessionLink.ts             # Wix ⇆ Clerk linkage helpers (CLK-6 only)
├── screens/
│   ├── SignIn.tsx                 # NEW: Clerk-hosted sign-in
│   ├── SignUp.tsx                 # NEW
│   ├── ConnectTrainingPeaks.tsx   # NEW: cookie upload / helper handshake
│   └── [existing screens]         # migrated off wixBridge auth token in CLK-6
├── services/
│   ├── wixBridge.ts               # auth paths deprecated in CLK-6, kept for billing
│   ├── wixBilling.ts              # NEW: split out billing-only Wix calls
│   └── tpMcpClient.ts             # NEW: typed MCP client, injects Authorization
└── main.tsx                       # ClerkProvider mounts at root
```

**`jarasport-tp-mcp/src/tp_mcp/`** — matches rebuild spec §Architecture:

```
src/tp_mcp/
├── auth/
│   ├── clerk.py          # JWT verify via JWKS cache (CLK-1 produces this)
│   ├── middleware.py     # Per-request auth → UserContext
│   └── context.py        # UserContext dataclass
├── credentials/
│   ├── store.py          # CredentialStore abstract base (CLK-2)
│   ├── sqlite.py         # Dev backend
│   ├── postgres.py       # Prod backend (CLK-7)
│   └── encryption.py     # libsodium wrapper
├── routes/
│   └── credentials.py    # POST/DELETE/GET /credentials/*
├── webhooks/
│   └── clerk.py          # Svix-verified user.deleted / user.updated
└── [rest per rebuild spec]
```

### Invariants

1. Clerk is the **sole issuer** of user identity. No other path creates a user record.
2. The JWT `sub` claim is the canonical `user_id` everywhere in the system. No shadow ID mapping.
3. `tp_core` never imports Clerk. Identity lives entirely in `tp_mcp/auth/` and `tp_mcp/routes/`.
4. The frontend never persists a Clerk JWT to localStorage. Tokens are requested per-call via `useAuth().getToken()`.
5. Clerk webhooks are Svix-verified before any state change. An unverified webhook is dropped with a 401.

## Identity & Claims Model

### Clerk tenant configuration

- **Environments**: two tenants — `jarasport-dev` (dev + preview) and `jarasport-prod` (staging + production). Staging shares the prod tenant but uses a dev instance ring-fenced at the gateway.
- **Sign-in methods** (Phase CLK-0): email + password, Google OAuth, Apple (for iOS-first athletes). Facebook deferred — existing `@greatsumini/react-facebook-login` in RDH removed.
- **User metadata**:
  - `public_metadata.plan` — `trial | monthly | annual | comp | none`, synced from Wix Pricing Plan events.
  - `public_metadata.tp_connected` — boolean, mirrored from `GET /credentials/status`, for UI gating without a backend roundtrip.
  - `private_metadata.wix_member_id` — legacy Wix Member ID during coexistence, null post-migration.
  - `private_metadata.athlete_profile_id` — Wix CMS AthleteProfiles row ID, authoritative for profile data until CLK-6.

### JWT custom template

Named **`jarasport-mcp`** in the Clerk dashboard. Claims:

```json
{
  "iss": "https://clerk.jarasport.{env}",
  "sub": "<clerk_user_id>",
  "email": "<primary_verified_email_or_null>",
  "email_verified": true,
  "org_id": "<clerk_org_id_or_null>",
  "org_role": "admin | basic_member | null",
  "plan": "trial | monthly | annual | comp | none",
  "tp_connected": true,
  "iat": 1735000000,
  "exp": 1735003600,
  "nbf": 1735000000,
  "azp": "https://raceday.jarasport.com.au"
}
```

Session token lifetime: 60s (short — we rely on `getToken()` per-call, not long-lived tokens). Refresh handled by Clerk SDK transparently.

### User ID model

- `user_id` (everywhere in `jarasport-tp-mcp` DB + logs + traces) **=** Clerk JWT `sub`.
- Logs emit `user_id_hash = sha256(user_id)[:16]` for privacy; raw `user_id` only in traces behind opt-in.

## Frontend (Race Day Hub)

### Integration points

- **Provider mount**: `ClerkProvider` wraps the React-Router tree in `src/main.tsx`. Publishable key via `VITE_CLERK_PUBLISHABLE_KEY`.
- **Routing**: React Router v7 already in place. Add `/sign-in/*`, `/sign-up/*` as Clerk-hosted routes via `<SignIn routing="path" path="/sign-in"/>`.
- **Protected routes**: `<ProtectedRoute>` component wraps every route under `/app/*`. Uses Clerk's `<SignedIn>` / `<SignedOut>` + `useAuth()`. On `SignedOut`, redirects with `redirect_url` set to current location.
- **API client**: `tpMcpClient.ts` wraps `fetch`, calling `await auth.getToken({ template: "jarasport-mcp" })` and setting `Authorization: Bearer <jwt>` on every request.
- **UI kit**: Clerk's prebuilt components styled with the Jarasport design tokens (Spinnaker headings, Anton labels, `#027DC6` primary, `#1a1a1a` background). Theme configured via `<ClerkProvider appearance={...}>`.

### Connect-TrainingPeaks flow

A new `ConnectTrainingPeaks.tsx` screen. Two paths:

- **Path A — Manual cookie upload** (fallback, always available): textarea + help text pointing to a browser-extension handoff. User pastes their TP session cookie string, RDH POSTs `/credentials` with it.
- **Path B — Helper CLI** (recommended, shipped in CLK-4): user runs `tp-mcp auth-import --from-browser chrome`; the CLI extracts the cookie locally and uploads it with the Clerk session cookie attached. No plaintext traverses the UI.

On success: green "Connected" pill, "Last refreshed" timestamp, and a "Disconnect" button that calls `DELETE /credentials`.

### Wix coexistence during rollout

- `wixBridge.ts` is split: **auth** path marked `@deprecated` but still present, **billing** path moves to `wixBilling.ts` unchanged.
- Feature flag `VITE_AUTH_IMPL = wix | clerk` drives which code path RDH uses.
- While `wix`: existing access-code flow works; Clerk SDK is loaded but idle.
- While `clerk`: Clerk is primary; `wixBridge.auth.*` returns 410-equivalents in the client.
- Cutover: default flips to `clerk` after 14 days clean in production (CLK-6).

## Backend (`jarasport-tp-mcp`)

### JWT verification middleware (`tp_mcp/auth/clerk.py`)

- **Library**: `pyjwt[crypto]` + `httpx` for JWKS fetching. Chose over `clerk-sdk-python` because the latter drags FastAPI into `tp_core`'s dependency graph; we stay minimal.
- **JWKS cache**: In-process async-safe TTL cache, 10-minute TTL, background refresh on 429 or network error (serves stale for up to 24h with a WARN log).
- **Verification steps**: decode header → look up kid in JWKS → verify signature → verify `iss`, `azp`, `exp`, `nbf`, `iat`. Clock skew: 30s.
- **Rejection**: any failure returns 401 with structured error `{"error": "unauthorized", "reason": "<machine_code>"}`. Never includes token content or stack traces in the response.
- **Performance target**: p95 < 5ms for JWKS-hit verifications.
- **Dev bypass**: `TP_MCP_AUTH_IMPL=env` activates `EnvDevAuth` which accepts a self-signed JWT minted by `scripts/fake-jwt.py`. Compiled out of the prod container by a build-time flag (`CLERK_ENV=prod` refuses to load `EnvDevAuth`).

### UserContext propagation

```python
@dataclass(frozen=True)
class UserContext:
    user_id: str           # Clerk sub
    email: str | None
    org_id: str | None
    plan: str              # Matches JWT plan claim
    tp_connected: bool
    request_id: str        # UUID, generated per request
```

Attached to the ASGI scope at middleware time. Tool handlers pull it via dependency injection, never a global.

### CredentialStore (`tp_mcp/credentials/`)

Abstract base with three implementations:

```python
class CredentialStore(Protocol):
    async def put(self, user_id: str, cookie: str) -> None: ...
    async def get(self, user_id: str) -> str | None: ...
    async def delete(self, user_id: str) -> None: ...
    async def status(self, user_id: str) -> CredentialStatus: ...  # age, last refresh
```

- `SQLiteCredentialStore` (dev) — single file, libsodium-`secretbox` encrypted blobs, key from `CREDENTIAL_STORE_KEY` env var (32-byte, base64).
- `PostgresCredentialStore` (prod, CLK-7) — Postgres with `pgcrypto` for envelope encryption; data-encryption-key wrapped by KMS.
- `InMemoryCredentialStore` (tests only) — no persistence, clears on teardown.

**Hard rules** (enforced by tests):
- `get()` returns plaintext only to the process that called it; never returned from an HTTP endpoint.
- `status()` returns booleans and timestamps, never plaintext or ciphertext.
- Every write logs an audit row: `{user_id_hash, action, timestamp}` — no payload.

### Endpoints

```
POST   /credentials            # Upload TP cookie, encrypt, store
DELETE /credentials            # Delete current user's stored cookie
GET    /credentials/status     # { connected, cookie_age_days, last_refresh_at }
POST   /webhooks/clerk         # Svix-verified Clerk lifecycle events
```

OpenAPI schema in `docs/api/openapi.yaml`; generated from Pydantic v2 models in CLK-2.

### Webhooks (`tp_mcp/webhooks/clerk.py`)

- **Svix verification**: every POST verified against the tenant's signing secret (env `CLERK_WEBHOOK_SECRET`). Failure → 401.
- **Event routing**:
  - `user.deleted` → `CredentialStore.delete(user_id)`; audit row.
  - `user.updated` — claims refresh hint; no direct action (JWTs are short-lived, claims auto-refresh).
  - `organization.deleted`, `organizationMembership.deleted` — no-op until org support lands.
  - All other events — logged at DEBUG, dropped.
- **Idempotency**: Svix provides `svix-id`; we dedupe in an in-memory LRU (10k entries, 1h TTL) to tolerate retries.
- **Replay window**: reject events with `svix-timestamp` older than 5 minutes.

## Wix Coexistence & Migration

### Billing bridge

Wix Pricing Plans remains authoritative for subscriptions. A small **Vercel serverless function** in `Jarasport/Race Day Hub/api/wix-webhooks.ts` receives Wix subscription events (`order.created`, `order.canceled`, `order.expired`), looks up the Wix Member → Clerk user (by `private_metadata.wix_member_id` or email), and patches `public_metadata.plan` via Clerk's Backend API.

Direction is one-way: Wix → Clerk. Clerk never writes back to Wix.

### Migration of existing access-code users

The seeded codes (`YEARROUND2025`, `COACHDEMO25`, `TRIAL14DAY`) and any AthleteProfiles rows must survive.

**Strategy** (CLK-6, triggered by cutover):

1. A one-shot migration script (`scripts/migrate-wix-to-clerk.ts`) runs against the Wix CMS:
   - For each AthleteProfile with an active Wix Member, create a Clerk user via Backend API using the Member's verified email.
   - Populate `private_metadata.wix_member_id`, `private_metadata.athlete_profile_id`, `public_metadata.plan`.
   - Send a Clerk password-reset invitation (users set a Clerk password on first sign-in).
2. On next RDH visit while `AUTH_IMPL=wix`, the wixBridge detects an active Wix session, checks Clerk for a pre-created user with matching email, silently bridges the session (issues a Clerk sign-in magic link auto-accepted by the frontend).
3. After 14 days with `AUTH_IMPL=clerk` default and zero bridge-fallback events, the bridge is removed and `wixBridge.auth.*` is deleted.

Users who miss the automated bridge (e.g., new device, cookie cleared) sign in via email + password reset.

## Development Mode & Test Fixtures

### Fake JWT minting

`jarasport-tp-mcp/scripts/fake-jwt.py` generates a JWT signed with a local RSA key matching a checked-in JWKS fixture in `tests/fixtures/jwks-dev.json`. The `EnvDevAuth` provider swaps the JWKS URL for this fixture when `TP_MCP_AUTH_IMPL=env`.

Example:

```bash
.venv/bin/python scripts/fake-jwt.py --sub user_2abc --email jara@example.com --plan annual --tp-connected > /tmp/dev.jwt
curl -H "Authorization: Bearer $(cat /tmp/dev.jwt)" http://localhost:8000/credentials/status
```

### Test fixtures

- `tests/fixtures/jwks-dev.json` — checked-in JWKS with a fixed kid (`dev-key-001`).
- `tests/fixtures/clerk-webhooks/*.json` — sample Svix-signed webhook payloads for every handled event.
- `tests/conftest.py` provides `fake_jwt(sub, **claims)` factory, `mock_clerk_jwks()` fixture, and `svix_signed_webhook(event, payload)` factory.

### Frontend dev

RDH dev mode (`pnpm dev`) uses `VITE_CLERK_PUBLISHABLE_KEY` from `.env.local` pointing at the `jarasport-dev` tenant. No fake-JWT path on the frontend — devs sign in to the dev tenant with a test account.

## Testing Strategy

### Backend

- **Unit**: every function in `tp_mcp/auth/`, `tp_mcp/credentials/`, `tp_mcp/webhooks/`, `tp_mcp/routes/credentials.py`. ≥90% line / ≥85% branch.
- **Contract**: every endpoint + webhook event has a contract test validating request/response schema roundtrip.
- **Integration**: `respx` mocks the JWKS endpoint; end-to-end test: fake JWT → middleware → tool handler → response.
- **Security** (non-negotiable):
  - **Cross-user isolation**: user A cannot read user B's credentials via JWT swap, `user_id` injection, or cache bleed. Explicit test with two fixtures.
  - **JWT replay**: reject reused JWT after `exp`, reject tampered signature, reject `kid` not in JWKS.
  - **Webhook replay**: reject `svix-id` dedup, reject stale `svix-timestamp`, reject unsigned payload.
  - **Log safety**: plant a known-secret cookie via fixture, run every endpoint + webhook, assert secret does not appear in any log line or response body.
- **Performance**: `pytest-benchmark` on `verify_jwt()` p95 < 5ms with JWKS hit, < 150ms with JWKS miss.

### Frontend

- **Unit** (Vitest): `tpMcpClient.ts` token injection, `ProtectedRoute` redirect behaviour.
- **Integration**: MSW mocks `/credentials/*`; test the Connect-TP happy path with a mocked Clerk `useAuth()`.
- **E2E** (Playwright): sign-up → email verify (test-mode bypass) → connect TP → land on dashboard. `axe-core` accessibility checks.
- **Coverage gate**: 70% lines / 70% functions / 60% branches — matches existing RDH thresholds.

## Phase Breakdown

See [CLK master plan](../plans/2026-04-25-jarasport-clerk-integration-master.md) for full detail.

| Phase  | Name | Scope | Est. | Depends on |
|:-------|:-----|:------|:----:|:-----------|
| CLK-0  | Tenant + ADR-0001 | Clerk tenant provisioning (dev + prod), JWT template, JWKS URL documented, ADR-0001 signed | 2 d | — |
| CLK-1  | Backend JWT middleware | `tp_mcp/auth/clerk.py`, JWKS cache, UserContext, EnvDevAuth, fake-JWT script, fixtures | 3 d | CLK-0 |
| CLK-2  | CredentialStore + endpoints | SQLite backend, encryption, `POST/DELETE/GET /credentials`, OpenAPI schema, log-safety tests | 4 d | CLK-1 |
| CLK-3  | Frontend auth shell | ClerkProvider mount, sign-in/up routes, ProtectedRoute, tpMcpClient, coexistence flag | 3 d | CLK-0 (parallel with CLK-1/2) |
| CLK-4  | Connect-TP flow | ConnectTrainingPeaks screen + helper CLI, end-to-end happy path, status + disconnect | 3 d | CLK-2 + CLK-3 |
| CLK-5  | Webhooks + lifecycle | Svix verification, `user.deleted` → credential delete, replay/dedup, signing-secret rotation runbook | 2 d | CLK-2 (parallel with CLK-4) |
| CLK-6  | Wix migration + cutover | Wix Pricing → Clerk metadata sync, access-code migration script, `AUTH_IMPL=clerk` default, wixBridge auth retirement | 5 d | CLK-4 + CLK-5 + TP MCP P3 |

**Total**: ~22 working days (~4–5 weeks). CLK-0/1/2 are the critical path for unblocking TP MCP P2.

## Rollout & Migration

- **Day 0–2 (CLK-0)**: tenants up, ADR-0001 signed, frontmatter-only artefacts committed.
- **Day 3–9 (CLK-1/2)**: backend complete. TP MCP P2 replaces its stub. Dev can run end-to-end with `EnvDevAuth` and fake JWTs.
- **Day 3–6 (CLK-3, parallel)**: frontend Clerk shell in RDH behind `VITE_AUTH_IMPL=wix` (still default). No user-visible change yet.
- **Day 10–12 (CLK-4)**: Connect-TP ships to staging with `VITE_AUTH_IMPL=clerk` behind a `?preview=clerk` query-string toggle for internal testing.
- **Day 13–14 (CLK-5)**: webhooks live in staging; deletion flow exercised via manual test.
- **Day 15–19 (CLK-6)**: migration script dry-run against prod Wix data (report only), then run. `VITE_AUTH_IMPL=clerk` rolled out to 10% → 50% → 100% via Vercel Edge Config over 5 days.
- **Day 20+ (soak)**: monitor error rates, bridge-fallback frequency, Clerk dashboard for sign-in failures. Declare cutover complete when bridge-fallback events = 0 for 14 days, then delete wixBridge auth path.

## Success Criteria

Must all be green to declare CLK complete:

1. `jarasport-tp-mcp` P2 middleware is real (`ClerkUserAuth`, not `StubClerkAuth`), with p95 JWT verification < 5ms.
2. Cross-user isolation test passes: user A cannot access user B's credentials by any path.
3. Log-safety test passes: plant secret is absent from every log line and response body across every endpoint and webhook.
4. Every webhook event has a contract test; Svix-verification test passes for positive and negative cases.
5. RDH serves `/sign-in`, `/sign-up`, `/app/*` under Clerk with `VITE_AUTH_IMPL=clerk` as production default.
6. Happy-path E2E (sign-up → connect TP → first tool call) passes in Playwright against staging.
7. Wix migration script completes a full prod run with zero orphaned users (every active AthleteProfile maps to a Clerk user or is explicitly flagged as archived).
8. Zero bridge-fallback events in production for 14 consecutive days.
9. ADR-0001 signed by owner; ADR-0002 (Wix coexistence strategy) signed.
10. Runbook covers Clerk JWKS rotation, webhook secret rotation, credential-store key rotation, and "user reports 'Connect TP failed' " triage.

## Risks & Mitigations

| Risk | Impact | Mitigation |
|:-----|:------:|:-----------|
| Clerk tenant misconfigured (wrong `azp`, wrong template name) blocks all JWT verification | High | CLK-0 DoD includes a smoke test: mint a JWT from the dev tenant and verify with a harness script. Fail CLK-0 until green. |
| JWKS endpoint latency spikes or outages | High | 10-min in-process cache with 24h stale-serve window on refresh failure; WARN log on stale serve; `/health/live` decoupled from Clerk reachability. |
| Wix→Clerk plan sync loses events during rollout | Medium | Vercel function logs every event + hash; a nightly reconciliation cron compares Wix subscriptions to Clerk `public_metadata.plan` and alerts on drift. |
| Users lose access during migration | High | Dry-run the migration script against prod Wix data and a disposable Clerk tenant first; reconciliation report must show 100% match before production run; bridge-fallback path catches any miss. |
| Clerk pricing shifts (e.g., org-feature paywall) | Medium | Org model is behind a feature flag; we fall back to single-user mode cleanly. |
| Webhook signing secret leaked | High | Secret stored in platform secret manager; never in env files or images; quarterly rotation in runbook. |
| Token theft from browser | High | Clerk tokens are 60s-lived and rotated per call; no localStorage; HttpOnly session cookie only; CSRF protection on `/credentials` via Clerk session check. |
| Frontend bundle size regression from Clerk SDK | Low | Measure in CLK-3 DoD; Clerk SDK is tree-shaken; budget +80kb gzipped, fail CI if exceeded. |

## Open Questions

| ID | Question | Owner | Resolution |
|:---|:---------|:------|:-----------|
| CQ-001 | Keep `@greatsumini/react-facebook-login`? | Product | **Recommended: remove.** Clerk doesn't gain us FB provider by default and the dep is unused after migration. Confirm in CLK-3. |
| CQ-002 | Keep `@react-oauth/google` when Clerk provides Google OAuth natively? | Product | **Recommended: remove.** Clerk's `<SignIn/>` handles Google. |
| CQ-003 | Should the migration script email users proactively? | Product | Defer; first rely on the auto-bridge in wixBridge. Only email if bridge-fallback > 1% at day 7. |
| CQ-004 | Staging: separate Clerk tenant or ring-fenced prod instance? | CLK-0 session | Default to ring-fenced prod tenant with a `STAGING` environment flag; revisit if it produces test-data pollution. |
| CQ-005 | `tp_connected` claim: push from webhook or poll from endpoint on token refresh? | CLK-2 session | Push from webhook for latency; fallback to refresh-on-failure. |
| CQ-006 | Clerk Backend API key rotation cadence? | CLK-5 session | Quarterly; documented in runbook. |

## Interface Contracts

### ADR-0001 — Clerk Boundary (prerequisite artefact)

See [`trainingpeaks-mcp/docs/adr/ADR-0001-clerk-boundary.md`](../adr/ADR-0001-clerk-boundary.md). Summary:

- Clerk owns: issuance, JWKS hosting, user lifecycle, webhooks.
- `jarasport-tp-mcp` owns: JWT verification, UserContext, CredentialStore, /credentials endpoints, webhook handler.
- RDH owns: ClerkProvider mount, sign-in/up UI, Connect-TP UI, Authorization header injection, session-link migration during Wix coexistence.
- **Wire format**: JWT in `Authorization: Bearer`, claims per the `jarasport-mcp` template.
- **Webhook format**: Svix-signed POST to `/webhooks/clerk`, events `user.deleted` and `user.updated` handled; all others dropped.

### Contract with TP MCP rebuild

- CLK-1 satisfies the `CLK-to-P2` handoff in the rebuild master plan (§4): Clerk JWT verification SDK choice, JWKS URL, expected claims.
- CLK-4/6 satisfy the `CLK-to-P7` handoff: onboarding UI routes, "Connect TP" entry point, cutover gating.
- CLK-2 delivers `CredentialStore` API used by TP MCP P3 tool handlers (they resolve a per-request `TPClient` via `UserContext`).

## Index of Related Docs

- Companion spec: [jarasport-tp-mcp-design.md](2026-04-25-jarasport-tp-mcp-design.md)
- ADR-0001: [../adr/ADR-0001-clerk-boundary.md](../adr/ADR-0001-clerk-boundary.md) (this session writes it)
- CLK master plan: [../plans/2026-04-25-jarasport-clerk-integration-master.md](../plans/2026-04-25-jarasport-clerk-integration-master.md)
- CLK phase plans: `../plans/2026-04-25-jarasport-clerk-integration-CLK-{0..6}-<name>.md`
- TP MCP master plan: [../plans/2026-04-25-jarasport-tp-mcp-master.md](../plans/2026-04-25-jarasport-tp-mcp-master.md) — CLK row in §1
- RDH plan pointer: `Jarasport/Race Day Hub/docs/superpowers/plans/2026-04-25-clerk-integration-pointer.md`

---

_Last updated: 2026-04-25 by CLK planning session._
