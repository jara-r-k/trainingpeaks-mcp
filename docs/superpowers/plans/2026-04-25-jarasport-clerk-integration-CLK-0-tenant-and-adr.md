---
title: jarasport-clerk-integration-CLK-0-tenant-and-adr
plan: CLK Phase 0 — Clerk Tenant Provisioning + ADR-0001 Sign-off
status: pending
owner: jara-r-k
date: 2026-04-25
project: trainingpeaks-mcp
parent: jarasport-clerk-integration-master
phase: CLK-0
actionable: auto
next_action: Task 1 — Create Clerk dev tenant
depends_on: none
---

# CLK-0 — Clerk Tenant + ADR-0001 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL — use `superpowers:executing-plans` or `superpowers:subagent-driven-development`. Each task uses `- [ ]` for tracking.

**Before you start:** read the [CLK master plan](./2026-04-25-jarasport-clerk-integration-master.md) §12 Session Protocol and claim this phase in §3.

**Goal:** Provision the Clerk tenants (dev + prod), configure the `jarasport-mcp` JWT template, document the JWKS URL, secure the secrets, and obtain owner sign-off on ADR-0001. Produces no application code but ships the infrastructure and contract artefacts that every later CLK phase depends on.

**Architecture:** Two Clerk tenants — `jarasport-dev` and `jarasport-prod`. Identical custom JWT templates named `jarasport-mcp`. Publishable keys, secret keys, and webhook signing secrets stored in platform secret managers (Vercel for frontend, Fly/Cloud Run or equivalent for backend). ADR-0001 ([docs/adr/ADR-0001-clerk-boundary.md](../../adr/ADR-0001-clerk-boundary.md)) is already drafted (2026-04-25); CLK-0 signs it off and promotes it from `accepted-draft` to `accepted-operational`.

**Estimated effort:** 2 working days.

---

## Prerequisites

- Owner has a Clerk account (or creates one in Task 1).
- Owner has owner-level access to Vercel project `jarasport-race-day-hub` (for publishable-key injection later).
- Owner has identified where the backend will deploy (Fly.io or Cloud Run) — exact platform may defer to TP MCP P5; CLK-0 only needs to know the secret-manager target.
- Read:
  - [CLK spec §Identity & Claims Model](../specs/2026-04-25-jarasport-clerk-integration-design.md)
  - [ADR-0001 draft](../../adr/ADR-0001-clerk-boundary.md)

---

## Tasks

### Task 1 — Create Clerk dev tenant

- [ ] 1.1 Sign in to Clerk dashboard (clerk.com) as owner. If no account, create one with `jara@…`.
- [ ] 1.2 Create an application named `jarasport-dev`. Choose "standalone" (not organization-first — orgs are stubbed in JWT only).
- [ ] 1.3 Configure sign-in methods: email + password, Google OAuth. Disable Facebook, Twitter, Apple for now (Apple to be added in CLK-6 if mobile app materialises).
- [ ] 1.4 Set instance region to match the expected user base (Australia → ap-southeast-2 if available; else closest).
- [ ] 1.5 Enable email verification, require on sign-up.
- [ ] 1.6 Capture publishable key (`pk_test_...`) and secret key (`sk_test_...`). Do NOT paste to chat or commit.
- [ ] 1.7 Document the Frontend API URL and JWKS URL (format: `https://<instance>.clerk.accounts.dev/.well-known/jwks.json`).
- [ ] 1.8 Record everything in a local, uncommitted `docs/clerk-tenant-dev.md.gitignored` note (path added to .gitignore in Task 5).

### Task 2 — Configure `jarasport-mcp` JWT template (dev)

- [ ] 2.1 In Clerk dashboard → JWT templates → New template → Name `jarasport-mcp`.
- [ ] 2.2 Set the claims JSON to match ADR-0001 §Wire format — JWT:
  ```json
  {
    "iss": "{{clerk.frontend_api}}",
    "sub": "{{user.id}}",
    "email": "{{user.primary_email_address}}",
    "email_verified": "{{user.primary_email_address.verification.status == 'verified'}}",
    "org_id": "{{org.id}}",
    "org_role": "{{org.role}}",
    "plan": "{{user.public_metadata.plan}}",
    "tp_connected": "{{user.public_metadata.tp_connected}}",
    "azp": "{{request.origin}}"
  }
  ```
- [ ] 2.3 Set lifetime to 60 seconds.
- [ ] 2.4 Set signing algorithm to RS256 (should be default).
- [ ] 2.5 Save template. Verify template name is exactly `jarasport-mcp`.

### Task 3 — End-to-end smoke test against dev tenant

- [ ] 3.1 Create a test Clerk user via the dashboard (`test-clk0@example.com`, password `test`). Set `public_metadata.plan = "annual"`, `public_metadata.tp_connected = false`.
- [ ] 3.2 Use Clerk's JWT tester (Dashboard → JWT templates → `jarasport-mcp` → "Try it"). Generate a test JWT.
- [ ] 3.3 Verify the JWT locally with a throwaway Python snippet using `pyjwt` + JWKS fetch (do NOT commit; this is a one-shot sanity check):
  - Signature valid
  - `iss`, `sub`, `email`, `plan`, `tp_connected` present
  - `exp - iat == 60`
  - `azp` present (even if empty in test harness)
- [ ] 3.4 Record the smoke test outcome in the handoff file (Task 9).
- [ ] 3.5 Delete the test user from the dashboard.

### Task 4 — Create Clerk prod tenant (mirrored)

- [ ] 4.1 In Clerk dashboard, create application `jarasport-prod` with the same sign-in method config as dev.
- [ ] 4.2 Configure the same `jarasport-mcp` JWT template (identical claims JSON).
- [ ] 4.3 Capture production publishable key (`pk_live_...`) and secret key (`sk_live_...`).
- [ ] 4.4 Document production Frontend API URL and JWKS URL.
- [ ] 4.5 Do NOT create any test users on prod.
- [ ] 4.6 Record staging strategy: prod tenant is ring-fenced by `azp` (staging uses `https://staging.raceday.jarasport.com.au`, prod uses `https://raceday.jarasport.com.au`). This answers open question CQ-004.

### Task 5 — Secrets management

- [ ] 5.1 Store `VITE_CLERK_PUBLISHABLE_KEY_DEV` in Vercel project env (scope: preview + development).
- [ ] 5.2 Store `VITE_CLERK_PUBLISHABLE_KEY_PROD` in Vercel project env (scope: production).
- [ ] 5.3 Add `docs/clerk-tenant-dev.md.gitignored` and `docs/clerk-tenant-prod.md.gitignored` to `.gitignore` in both `jarasport-tp-mcp` and `Jarasport/Race Day Hub`.
- [ ] 5.4 Backend secret keys will be stored in the chosen platform's secret store in CLK-1 (deferred; CLK-0 does not deploy the backend).
- [ ] 5.5 Commit a `docs/secrets-inventory.md` to `jarasport-tp-mcp` listing every secret name, owner, rotation cadence, and where it is stored (contents only, never values).

### Task 6 — Update existing RDH `.env.example`

- [ ] 6.1 Read `Jarasport/Race Day Hub/.env.example` (create if absent).
- [ ] 6.2 Add:
  ```env
  # Clerk
  VITE_CLERK_PUBLISHABLE_KEY=
  VITE_AUTH_IMPL=wix  # wix | clerk
  ```
- [ ] 6.3 Commit with message `chore(env): add Clerk env stubs for CLK-0`.

### Task 7 — ADR-0001 promotion to accepted-operational

- [ ] 7.1 Read the ADR at `trainingpeaks-mcp/docs/adr/ADR-0001-clerk-boundary.md`.
- [ ] 7.2 Reconcile §Wire format — JWT against the Task 2 template. If mismatch, prefer the template and update the ADR with a `Revision` note at the bottom.
- [ ] 7.3 Change frontmatter `status: accepted` → `status: accepted-operational`.
- [ ] 7.4 Append a "Sign-offs" section at the bottom:
  ```markdown
  ## Sign-offs

  | Role  | Name | Date       | Notes |
  |:------|:-----|:-----------|:------|
  | Owner | Jara | YYYY-MM-DD | —     |
  ```
- [ ] 7.5 Commit with message `docs(adr): promote ADR-0001 to accepted-operational after CLK-0 smoke test`.

### Task 8 — Decide CQ-004: staging tenant strategy

- [ ] 8.1 Based on Tasks 4 and 3, confirm CQ-004 resolution: "ring-fenced prod tenant distinguished by `azp`".
- [ ] 8.2 Update master plan §8 CQ-004 row: resolution `ring-fenced prod; revisit if data pollution`. Mark resolved with today's date.
- [ ] 8.3 Add a `docs/staging-strategy.md` one-pager capturing the decision and its implications (test data hygiene, dashboard conventions).

### Task 9 — Write handoff CLK-0 → CLK-1

- [ ] 9.1 Create `trainingpeaks-mcp/docs/superpowers/plans/HANDOFFS/CLK-0-to-CLK-1.md`.
- [ ] 9.2 Include:
  - Dev JWKS URL (exact)
  - Prod JWKS URL (exact)
  - JWT template name (`jarasport-mcp`)
  - Expected claim set (copy from ADR-0001)
  - Signing algorithm (`RS256`)
  - Clerk SDK library choice for Python: `pyjwt[crypto]` + `httpx` for JWKS fetch (justified in CLK spec §Backend)
  - Dev smoke test result (pass/fail with note)
  - Clock skew tolerance: 30s
  - Token lifetime: 60s
- [ ] 9.3 Commit with message `docs(plans): write CLK-0 to CLK-1 handoff`.

### Task 10 — Write handoff CLK-0 → CLK-3

- [ ] 10.1 Create `trainingpeaks-mcp/docs/superpowers/plans/HANDOFFS/CLK-0-to-CLK-3.md`.
- [ ] 10.2 Include:
  - Dev publishable key env var name (`VITE_CLERK_PUBLISHABLE_KEY_DEV`)
  - Prod publishable key env var name (`VITE_CLERK_PUBLISHABLE_KEY_PROD`)
  - Sign-in URL pattern: `/sign-in/*`
  - Sign-up URL pattern: `/sign-up/*`
  - `<ClerkProvider>` appearance tokens (Jarasport brand colours + fonts from CLAUDE.md)
  - Feature flag env var: `VITE_AUTH_IMPL` (default `wix`)
  - JWT template name to pass to `getToken({ template })`: `jarasport-mcp`
- [ ] 10.3 Commit with message `docs(plans): write CLK-0 to CLK-3 handoff`.

### Task 11 — Update master plan status

- [ ] 11.1 Edit `2026-04-25-jarasport-clerk-integration-master.md` §1: CLK-0 status `PENDING` → `IN PROGRESS` at session start, `DONE — UNVERIFIED` at session end.
- [ ] 11.2 Edit §3 Session Claims: add row with session ID, claim time. Mark RELEASED at session end.
- [ ] 11.3 Edit §11 Session Ledger: append row for this session.
- [ ] 11.4 Edit §8 Open Questions: mark CQ-004 resolved per Task 8.
- [ ] 11.5 Edit TP MCP master plan `2026-04-25-jarasport-tp-mcp-master.md` §1 CLK row: status `NOT STARTED` → `IN PROGRESS (CLK-0)`.

### Task 12 — DoD verification

- [ ] 12.1 Run through §5 universal DoD checklist (no code this phase, so most are n/a; handoff files + session ledger still apply).
- [ ] 12.2 Run through §5 CLK-0 phase-specific DoD:
  - Two tenants provisioned? ☐
  - `jarasport-mcp` template live? ☐
  - Smoke test green? ☐
  - ADR-0001 signed? ☐
  - Secrets captured in managers? ☐
- [ ] 12.3 If green, append §9 row for CLK-0 DoD sign-off.

---

## Handoff Outputs

Files this phase produces (written in Tasks 9–10, committed by Task 11):

1. `HANDOFFS/CLK-0-to-CLK-1.md`
2. `HANDOFFS/CLK-0-to-CLK-3.md`
3. `docs/secrets-inventory.md` (new)
4. `docs/staging-strategy.md` (new)
5. Updated `docs/adr/ADR-0001-clerk-boundary.md` (status flip + sign-offs)

---

## Open Questions (phase-local)

None at CLK-0 start. CQ-001, CQ-002 defer to CLK-3; CQ-003 to CLK-6; CQ-005 to CLK-2; CQ-006 to CLK-5; CQ-007 to CLK-6.

---

## Exit Criteria

Phase transitions to `DONE` when:

- All 12 tasks checked off.
- DoD §5 universal + CLK-0 specific all green.
- §9 sign-off row appended.
- Master plan §1 CLK-0 row shows `DONE` with date.
- Handoff files exist and are committed.

Next phase: **CLK-1 and CLK-3 unblock in parallel.** Either or both may begin.

---

_Template source: shape matches TP MCP P0 plan file ([../plans/2026-04-25-jarasport-tp-mcp-P0-foundations.md](./2026-04-25-jarasport-tp-mcp-P0-foundations.md)) for session-protocol consistency._
