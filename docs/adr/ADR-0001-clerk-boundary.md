---
title: ADR-0001 — Clerk Boundary
status: accepted
date: 2026-04-25
deciders: Jara (owner)
supersedes: none
superseded_by: none
---

# ADR-0001 — Clerk Boundary

## Status

**Accepted** — 2026-04-25.

This ADR is a prerequisite for CLK-1 (backend JWT middleware) per the CLK master plan. It freezes the contract between Clerk (identity provider), `jarasport-tp-mcp` (authenticated service), and Race Day Hub (frontend client). Changes to this ADR require a new ADR superseding it.

## Context

The `jarasport-tp-mcp` rebuild ([spec](../specs/2026-04-25-jarasport-tp-mcp-design.md)) and the Clerk integration session (CLK, [spec](../specs/2026-04-25-jarasport-clerk-integration-design.md)) both depend on a crisp identity boundary. Without it:

- The rebuild's middleware cannot verify JWTs it doesn't know the shape of.
- RDH cannot inject an Authorization header whose claim set is undefined.
- Wix → Clerk plan sync has no agreed metadata target.
- Webhook handlers have no agreed event surface.

This ADR fills that gap. It is deliberately narrow: it specifies the wire format and ownership boundaries, not the implementation.

## Decision

### Authority model

- **Clerk** is the **sole issuer** of user identity for Jarasport products. No other path creates a `user_id`.
- **`jarasport-tp-mcp`** verifies JWTs and owns server-side credential storage. It does not mint tokens.
- **Race Day Hub** consumes Clerk session state and injects JWTs on outbound calls to `jarasport-tp-mcp`. It does not store raw JWTs.
- **Wix** remains the billing and CMS system but is **not** an identity source after cutover.

### Ownership matrix

| Area | Owner | Notes |
|:-----|:------|:------|
| User creation, deletion, profile updates | Clerk | via Clerk dashboard or Backend API |
| JWT issuance | Clerk | Custom template `jarasport-mcp` |
| JWKS hosting | Clerk | `https://clerk.jarasport.{env}/.well-known/jwks.json` |
| JWT verification | `jarasport-tp-mcp` | `tp_mcp/auth/clerk.py` |
| UserContext extraction | `jarasport-tp-mcp` | `tp_mcp/auth/middleware.py` |
| CredentialStore (TP cookies) | `jarasport-tp-mcp` | `tp_mcp/credentials/*` |
| `/credentials` endpoints | `jarasport-tp-mcp` | POST, DELETE, GET /status |
| Webhook handling | `jarasport-tp-mcp` | `tp_mcp/webhooks/clerk.py`, Svix-verified |
| ClerkProvider mount | Race Day Hub | `src/main.tsx` |
| Sign-in / sign-up UI | Race Day Hub | Clerk-hosted routes |
| Protected routes | Race Day Hub | `<ProtectedRoute>` |
| Authorization header injection | Race Day Hub | `tpMcpClient.ts` via `useAuth().getToken()` |
| Connect-TP UI | Race Day Hub | `ConnectTrainingPeaks.tsx` |
| Wix → Clerk plan sync | Race Day Hub (Vercel fn) | `api/wix-webhooks.ts` |

### Wire format — JWT

- **Transport**: HTTP header `Authorization: Bearer <jwt>` on every call into `jarasport-tp-mcp`.
- **Template name**: `jarasport-mcp` (Clerk dashboard → JWT templates).
- **Algorithm**: RS256 (Clerk default). No symmetric algorithms accepted.
- **Claims** (all required unless noted):
  - `iss` — `https://clerk.jarasport.{env}`, exact-match check.
  - `sub` — Clerk user_id, stable across sessions. This is the canonical `user_id`.
  - `email` — primary verified email; may be `null` if user deleted primary.
  - `email_verified` — boolean.
  - `org_id` — Clerk org_id or `null`.
  - `org_role` — `"admin" | "basic_member" | null`.
  - `plan` — one of `"trial" | "monthly" | "annual" | "comp" | "none"`; synced from Wix.
  - `tp_connected` — boolean; mirrors CredentialStore state.
  - `iat`, `exp`, `nbf` — standard.
  - `azp` — authorised party, must equal `https://raceday.jarasport.com.au` (prod) or `http://localhost:5173` (dev).
- **Lifetime**: 60s. Frontend requests a fresh token per outbound call via `getToken()`.
- **Clock skew tolerance**: 30s.
- **Rejection codes** (structured error body):
  - `unauthorized.missing_token`
  - `unauthorized.bad_signature`
  - `unauthorized.expired`
  - `unauthorized.not_yet_valid`
  - `unauthorized.wrong_issuer`
  - `unauthorized.wrong_azp`
  - `unauthorized.unknown_kid`
  - `unauthorized.malformed_claims`

### Wire format — webhooks

- **Endpoint**: `POST /webhooks/clerk` on `jarasport-tp-mcp`.
- **Verification**: Svix signature headers `svix-id`, `svix-timestamp`, `svix-signature`. Secret in env `CLERK_WEBHOOK_SECRET`.
- **Replay window**: reject events with `svix-timestamp` older than 5 minutes.
- **Idempotency**: dedupe by `svix-id` in an in-process LRU (10k entries, 1h TTL).
- **Events handled**:
  - `user.deleted` → `CredentialStore.delete(user_id)` + audit row.
  - `user.updated` → logged at INFO; no side effects (claims refresh is pull-based via short-lived JWTs).
- **Events dropped silently** (logged DEBUG): all other Clerk event types.
- **Response**: `200 OK` on success, `401 Unauthorized` on signature failure, `202 Accepted` on dedup hit.

### `/credentials` API

Under `jarasport-tp-mcp`, authenticated via the JWT above.

```
POST /credentials
  Body:   { "tp_cookie": "<cookie_value>" }
  200:    204 No Content
  401:    invalid/missing JWT
  400:    malformed cookie
  422:    cookie rejected by TP (validator failure)

DELETE /credentials
  200:    204 No Content
  401:    invalid/missing JWT
  404:    no cookie on file (idempotent — also return 204)

GET /credentials/status
  200:    { "connected": bool, "cookie_age_days": int | null, "last_refresh_at": iso8601 | null }
  401:    invalid/missing JWT
```

### Environment conventions

| Env | Clerk tenant | `azp` | Notes |
|:----|:-------------|:------|:------|
| dev | `jarasport-dev` | `http://localhost:5173` | Fake-JWT path active via `TP_MCP_AUTH_IMPL=env` |
| staging | `jarasport-prod` (ring-fenced) | `https://staging.raceday.jarasport.com.au` | Same tenant as prod, different `azp` |
| prod | `jarasport-prod` | `https://raceday.jarasport.com.au` | `TP_MCP_AUTH_IMPL=env` is refused |

## Consequences

### Positive

- CLK-1 can ship against a written contract without cross-session coordination.
- TP MCP P2 can remove its `StubClerkAuth` on CLK-1 landing (single-day swap per the rebuild risk register R-002).
- A single issuer makes user-isolation testing tractable: one identity source, one canonical `user_id`.
- Short-lived tokens (60s) reduce the blast radius of token theft.
- Explicit rejection codes let RDH show useful sign-in error messages without leaking internals.

### Negative

- Clerk becomes a hard runtime dependency of `jarasport-tp-mcp`. JWKS reachability is required for any authenticated request.
  - *Mitigation*: 10-minute in-process JWKS cache with 24h stale-serve window on refresh failure.
- Custom JWT template claims (`plan`, `tp_connected`) create a light coupling between Clerk and `jarasport-tp-mcp`. If we ever swap IdPs, the template must be re-implemented.
  - *Mitigation*: claims are documented above; swap would be scoped work, not unknown work.
- Two Clerk tenants (dev, prod) doubles ops surface: separate rotation schedules, separate dashboards.
  - *Mitigation*: runbook in CLK-5 covers both tenants.

### Neutral

- Webhooks create an async path from Clerk → `jarasport-tp-mcp`; monitoring must cover webhook failure modes (Svix will retry, but prolonged outages pile events).

## Alternatives considered

### A1 — Auth0 instead of Clerk

Rejected. RDH's existing ecosystem already leans toward Clerk via prior scoping; Auth0's pricing is less favourable at Jarasport's scale; no technical advantage identified.

### A2 — Self-hosted Keycloak

Rejected. Operational cost outweighs benefit; we do not need on-prem identity; JWKS hosting, webhook infra, and dashboards are all free with Clerk's plan.

### A3 — Continue Wix Members as IdP

Rejected. Wix Members lacks JWT issuance, JWKS hosting, and webhook signing; building a shim to wrap it is strictly more work than adopting Clerk.

### A4 — Short-lived opaque tokens instead of JWTs

Rejected. Opaque tokens require a session lookup per request, adding latency and a Clerk API dependency to the hot path. Short-lived JWTs with JWKS verification stay local to `jarasport-tp-mcp` after the initial key fetch.

## Review cadence

This ADR is revisited when:

- Clerk changes their JWT template schema.
- Jarasport adds a second IdP (e.g., enterprise SSO for a B2B tier).
- `org_id` / `org_role` claims become load-bearing (currently provisioned but inert).
- Webhook surface expands beyond the two handled events.

Next scheduled review: 2026-10-25 (6 months).

## References

- Clerk docs: https://clerk.com/docs (consulted 2026-04-25)
- Svix webhook verification: https://docs.svix.com/receiving/verifying-payloads/how
- Rebuild spec §Auth: [../specs/2026-04-25-jarasport-tp-mcp-design.md](../specs/2026-04-25-jarasport-tp-mcp-design.md)
- CLK spec: [../specs/2026-04-25-jarasport-clerk-integration-design.md](../specs/2026-04-25-jarasport-clerk-integration-design.md)
