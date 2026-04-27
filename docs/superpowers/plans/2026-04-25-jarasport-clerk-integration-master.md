---
title: jarasport-clerk-integration-master
plan: jarasport-clerk-integration master plan
status: in-progress
owner: jara-r-k
date: 2026-04-25
project: trainingpeaks-mcp
phases: CLK-0 to CLK-6
actionable: auto
next_action: Start CLK-0 Task 1 (Clerk tenant provisioning)
parent: jarasport-tp-mcp-master
---

# jarasport-clerk-integration — Master Plan

> **For agentic workers:** This is the **program-level coordination document** for the CLK track, parallel to the `jarasport-tp-mcp` rebuild master. It is the single source of truth for phase status, cross-session handoffs, and "nothing falls through cracks" tracking across two repos (`jarasport-tp-mcp` + `Jarasport/Race Day Hub`). Every CLK session **must** read this first and update it on exit.

**Goal:** Deliver a Clerk-based identity layer for the Jarasport product, unblocking `jarasport-tp-mcp` P2 and replacing the Wix Members access-code auth bridge in Race Day Hub, with zero bridge-fallback events after cutover.

**Architecture:** Clerk issuer (RS256, custom `jarasport-mcp` JWT template) → RDH `ClerkProvider` injects Authorization header → `jarasport-tp-mcp` verifies JWT via cached JWKS → per-user `CredentialStore` keyed by Clerk `sub` → Svix-verified webhooks close the lifecycle loop.

**Tech Stack:** Clerk React SDK (`@clerk/clerk-react`), `pyjwt[crypto]`, `httpx`, `libsodium` (PyNaCl), SQLite/Postgres, Svix, Vercel serverless (Wix bridge), React 19 + Vite 6 + TypeScript 5 (RDH), Python 3.10–3.14 (`jarasport-tp-mcp`).

**Ref specs:**
- CLK design: [../specs/2026-04-25-jarasport-clerk-integration-design.md](../specs/2026-04-25-jarasport-clerk-integration-design.md)
- Rebuild design: [../specs/2026-04-25-jarasport-tp-mcp-design.md](../specs/2026-04-25-jarasport-tp-mcp-design.md)
- ADR-0001: [../../adr/ADR-0001-clerk-boundary.md](../../adr/ADR-0001-clerk-boundary.md)

**Parent program:** [jarasport-tp-mcp-master](./2026-04-25-jarasport-tp-mcp-master.md) — CLK is the "Clerk integration session" row (row `CLK`) in that document's §1 Phase Status Matrix.

---

## 0. How to Use This Document

**Every session:**

1. **On start** — read this file top-to-bottom. Identify the current phase, open handoffs, unresolved risks, unanswered questions. Check the Session Ledger (§11) to see what the last session did. Read the referenced phase plan file.
2. **Mid-session** — update the Risk Register (§7) and Open Questions (§8) as they arise. Never leave a question only in conversation history.
3. **On exit** — append an entry to the Session Ledger (§11), update the Phase Status Matrix (§1), commit this file along with any code.

**Golden rule:** if it is not written in this document, it does not exist. Conversation memory is not a valid coordination mechanism across sessions.

**Cross-repo rule:** CLK-3, CLK-4, and CLK-6 touch both `jarasport-tp-mcp` and `Jarasport/Race Day Hub`. A session touching RDH **must** commit in the RDH repo and reference the commit SHA in the Session Ledger. The RDH plan-pointer doc (see §15) lists what changed, so the next session can reconstruct state without reading both repos' full histories.

---

## 1. Phase Status Matrix

Update whenever a phase transitions between statuses. Timestamps in `YYYY-MM-DD`.

| Phase  | Name                            | Status      | Plan file                                                                        | Started    | Completed  | DoD Signed Off | Blocked On |
|:-------|:--------------------------------|:------------|:---------------------------------------------------------------------------------|:-----------|:-----------|:---------------|:-----------|
| CLK-0  | Tenant + ADR-0001               | PENDING     | `2026-04-25-jarasport-clerk-integration-CLK-0-tenant-and-adr.md`                 | —          | —          | —              | —          |
| CLK-1  | Backend JWT middleware          | NOT STARTED | `2026-04-25-jarasport-clerk-integration-CLK-1-backend-jwt-middleware.md`         | —          | —          | —              | CLK-0      |
| CLK-2  | CredentialStore + endpoints     | NOT STARTED | `2026-04-25-jarasport-clerk-integration-CLK-2-credential-store-endpoints.md`     | —          | —          | —              | CLK-1      |
| CLK-3  | Frontend auth shell             | NOT STARTED | `2026-04-25-jarasport-clerk-integration-CLK-3-frontend-auth-shell.md`            | —          | —          | —              | CLK-0      |
| CLK-4  | Connect-TP flow                 | NOT STARTED | `2026-04-25-jarasport-clerk-integration-CLK-4-connect-tp-flow.md`                | —          | —          | —              | CLK-2, CLK-3 |
| CLK-5  | Webhooks + lifecycle            | NOT STARTED | `2026-04-25-jarasport-clerk-integration-CLK-5-webhooks-lifecycle.md`             | —          | —          | —              | CLK-2      |
| CLK-6  | Wix migration + cutover         | NOT STARTED | `2026-04-25-jarasport-clerk-integration-CLK-6-wix-migration-cutover.md`          | —          | —          | —              | CLK-4, CLK-5, TP MCP P3 |

**Status vocabulary:**
- `NOT STARTED` — prerequisites may not be met.
- `PENDING` — prerequisites met, ready to start, plan file written.
- `IN PROGRESS` — a session has claimed it (see §3).
- `BLOCKED` — started but halted on an external dependency. Must list reason.
- `DONE — UNVERIFIED` — tasks complete, DoD not yet signed off.
- `DONE` — DoD signed off in §9.

---

## 2. Dependency Graph

```
CLK-0 ─┬─► CLK-1 ─► CLK-2 ─┬─► CLK-4 ─┐
       │                   │          │
       │                   └─► CLK-5 ─┤
       │                              ├─► CLK-6 ─► DONE
       └─► CLK-3 ─────────────────────┘

External: CLK-6 also requires TP MCP P3 (tool migration) DONE.
External: CLK-1 unblocks TP MCP P2 (swap stub for real middleware).
```

- CLK-0 → CLK-1 and CLK-0 → CLK-3 in parallel.
- CLK-2 → CLK-4 and CLK-2 → CLK-5 in parallel.
- CLK-6 is the last phase and requires convergence.

---

## 3. Session Claims (Concurrent Session Lock)

**Purpose:** prevent two sessions from modifying the same phase. This is the lock table.

When a session begins a phase, it **must** add a row here. On end, it **must** mark `RELEASED` or delete the row. Stale claims (>48h with no §11 entry) may be preempted with a note.

| Phase | Session ID (timestamp + initials) | Claimed At       | Released At      | Status    | Notes |
|:------|:----------------------------------|:-----------------|:-----------------|:----------|:------|
|       |                                   |                  |                  |           |       |

---

## 4. Handoff Artefacts

Between-phase contracts. Written by the producing phase, read by the consuming phase. Stored under `docs/superpowers/plans/HANDOFFS/` in the `jarasport-tp-mcp` repo.

| From   | To      | Handoff file                                          | Status       | Summary of contract |
|:-------|:--------|:------------------------------------------------------|:-------------|:--------------------|
| CLK-0  | CLK-1   | `HANDOFFS/CLK-0-to-CLK-1.md`                          | not written  | JWKS URL, tenant names, JWT template name, expected claims, signing algorithm |
| CLK-0  | CLK-3   | `HANDOFFS/CLK-0-to-CLK-3.md`                          | not written  | Publishable key, sign-in URL, sign-up URL, appearance token schema |
| CLK-1  | CLK-2   | `HANDOFFS/CLK-1-to-CLK-2.md`                          | not written  | `UserContext` shape, middleware mount point, error-body format |
| CLK-1  | TP-P2   | `HANDOFFS/CLK-1-to-P2.md`                             | not written  | `tp_mcp/auth/clerk.py` public API, dev-bypass contract, fake-JWT helper |
| CLK-2  | CLK-4   | `HANDOFFS/CLK-2-to-CLK-4.md`                          | not written  | `/credentials` endpoint contracts, error codes, rate limits |
| CLK-2  | CLK-5   | `HANDOFFS/CLK-2-to-CLK-5.md`                          | not written  | CredentialStore public API, audit-row shape |
| CLK-3  | CLK-4   | `HANDOFFS/CLK-3-to-CLK-4.md`                          | not written  | `tpMcpClient.ts` helper, `ProtectedRoute` pattern, feature-flag hook |
| CLK-4  | CLK-6   | `HANDOFFS/CLK-4-to-CLK-6.md`                          | not written  | Connect-TP route, disconnect route, status endpoint polling pattern |
| CLK-5  | CLK-6   | `HANDOFFS/CLK-5-to-CLK-6.md`                          | not written  | Webhook secret rotation runbook, replay detection metrics |
| CLK-6  | TP-P7   | `HANDOFFS/CLK-6-to-P7.md`                             | not written  | Migration script, cutover flag, bridge-fallback metrics |

**Writing a handoff:** before marking a phase DONE, ensure the handoff file captures every assumption the consumer may make. Consumer's first step is "read handoff and ask questions"; if ambiguous, ping back — don't guess.

---

## 5. Definition of Done per Phase

A phase moves to `DONE` only when every item is green. Sign-off in §9.

### Universal (applies to every phase that ships code)

- [ ] All tasks in the phase's plan file marked complete.
- [ ] Backend changes: `ruff check` + `ruff format --check` + `mypy --strict` clean.
- [ ] Backend changes: `pytest` green across the Python 3.10–3.14 matrix.
- [ ] Frontend changes: `pnpm lint` + `tsc --noEmit` + `pnpm test:run` green.
- [ ] Backend changes: line coverage ≥ 90%, branch ≥ 85% on code introduced this phase.
- [ ] Frontend changes: line coverage ≥ 70%, function coverage ≥ 70%, branch ≥ 60% (matches RDH thresholds).
- [ ] Every new public module/function/class has a docstring or JSDoc.
- [ ] No new `# type: ignore` / `// @ts-ignore` without an inline reason.
- [ ] Handoff files (§4) from this phase written and committed.
- [ ] Session Ledger (§11) updated.
- [ ] Risk register (§7) reviewed — new risks added.
- [ ] Open Questions (§8) reviewed — resolved ones moved to the spec or a follow-up ADR.

### Phase-specific

- **CLK-0** — Two Clerk tenants provisioned (dev, prod); `jarasport-mcp` JWT template live; fake-JWT harness verifies end-to-end against the dev tenant; ADR-0001 signed (already written 2026-04-25; sign-off by owner in CLK-0); tenant secrets captured in platform secret managers.
- **CLK-1** — `tp_mcp/auth/clerk.py` verifies a live Clerk JWT and a fake JWT; p95 < 5ms JWKS-hit; JWKS cache refresh behaviour exercised in tests; integration test with stubbed JWKS server; TP MCP master plan §1 P2 "Blocked On" cleared.
- **CLK-2** — SQLite CredentialStore roundtrips encrypted blobs; `POST/DELETE/GET /credentials/*` respond per ADR-0001; log-safety test with plant secret passes; cross-user isolation test passes; OpenAPI schema committed.
- **CLK-3** — RDH boots with `ClerkProvider` at root; `/sign-in` + `/sign-up` routes functional against dev tenant; `<ProtectedRoute>` guards `/app/*`; `tpMcpClient.ts` injects Authorization on a canary `/health` call; feature flag `VITE_AUTH_IMPL=wix` remains default.
- **CLK-4** — Connect-TP screen ships behind `?preview=clerk` in staging; user can upload a cookie (Path A) and optionally use the helper CLI (Path B); status endpoint polled correctly; Playwright happy-path passes.
- **CLK-5** — Webhook endpoint verifies Svix signatures, processes `user.deleted` and `user.updated`, rejects replays older than 5min, dedupes by `svix-id`; signing-secret rotation procedure exercised end-to-end in staging.
- **CLK-6** — Wix→Clerk sync Vercel function live; migration script dry-run report matches 100% of active AthleteProfiles; `VITE_AUTH_IMPL=clerk` rolled out to 100% in prod via Vercel Edge Config; zero bridge-fallback events for 14 days; wixBridge auth path deleted from main.

---

## 6. Interface Inventory

Concrete artefacts this program produces. Track by status.

### Frontend (RDH — `Jarasport/Race Day Hub/`)

| Artefact | Path | Phase | Status |
|:---------|:-----|:------|:-------|
| ClerkProvider mount | `src/main.tsx` | CLK-3 | ☐ |
| ClerkProviderWrapper | `src/auth/ClerkProviderWrapper.tsx` | CLK-3 | ☐ |
| ProtectedRoute | `src/auth/ProtectedRoute.tsx` | CLK-3 | ☐ |
| useApi hook | `src/auth/useApi.ts` | CLK-3 | ☐ |
| Sign-in route | `src/screens/SignIn.tsx` | CLK-3 | ☐ |
| Sign-up route | `src/screens/SignUp.tsx` | CLK-3 | ☐ |
| ConnectTrainingPeaks screen | `src/screens/ConnectTrainingPeaks.tsx` | CLK-4 | ☐ |
| tpMcpClient | `src/services/tpMcpClient.ts` | CLK-3 | ☐ |
| wixBilling split | `src/services/wixBilling.ts` | CLK-6 | ☐ |
| Wix webhook bridge | `api/wix-webhooks.ts` | CLK-6 | ☐ |
| Migration script | `scripts/migrate-wix-to-clerk.ts` | CLK-6 | ☐ |
| sessionLink helpers | `src/auth/sessionLink.ts` | CLK-6 | ☐ |
| Auth E2E | `e2e/auth.spec.ts` | CLK-3/4 | ☐ |

### Backend (`jarasport-tp-mcp/src/tp_mcp/`)

| Artefact | Path | Phase | Status |
|:---------|:-----|:------|:-------|
| Clerk JWT middleware | `auth/clerk.py` | CLK-1 | ☐ |
| UserContext | `auth/context.py` | CLK-1 | ☐ |
| ASGI middleware | `auth/middleware.py` | CLK-1 | ☐ |
| EnvDevAuth | `auth/env_dev.py` | CLK-1 | ☐ |
| fake-jwt script | `scripts/fake-jwt.py` | CLK-1 | ☐ |
| CredentialStore ABC | `credentials/store.py` | CLK-2 | ☐ |
| SQLite backend | `credentials/sqlite.py` | CLK-2 | ☐ |
| Encryption wrapper | `credentials/encryption.py` | CLK-2 | ☐ |
| `/credentials` routes | `routes/credentials.py` | CLK-2 | ☐ |
| Webhook handler | `webhooks/clerk.py` | CLK-5 | ☐ |
| Postgres backend | `credentials/postgres.py` | CLK-6 (TP-P5-aligned) | ☐ |
| OpenAPI schema | `docs/api/openapi.yaml` | CLK-2 | ☐ |

### Infrastructure

| Artefact | Location | Phase | Status |
|:---------|:---------|:------|:-------|
| Clerk dev tenant | Clerk dashboard | CLK-0 | ☐ |
| Clerk prod tenant | Clerk dashboard | CLK-0 | ☐ |
| `jarasport-mcp` JWT template | Clerk dashboard | CLK-0 | ☐ |
| Webhook endpoint registration | Clerk dashboard | CLK-5 | ☐ |
| `CLERK_WEBHOOK_SECRET` | Platform secret store | CLK-5 | ☐ |
| `CREDENTIAL_STORE_KEY` | Platform secret store | CLK-2 | ☐ |
| Runbook | `docs/RUNBOOK.md` | CLK-5/6 | ☐ |

---

## 7. Risk Register

Live. Each risk: ID, description, impact, likelihood, mitigation, status.

| ID     | Risk                                                                  | Impact | Likelihood | Mitigation                                                                  | Status | Opened     | Closed |
|:-------|:----------------------------------------------------------------------|:------:|:----------:|:----------------------------------------------------------------------------|:-------|:-----------|:-------|
| CR-001 | Clerk tenant misconfigured blocks all JWT verification                | High   | Low        | CLK-0 DoD includes end-to-end smoke test against dev tenant                 | Open   | 2026-04-25 | —      |
| CR-002 | JWKS endpoint latency spikes or outages                               | High   | Low        | 10-min in-process cache; 24h stale-serve; `/health/live` decoupled          | Open   | 2026-04-25 | —      |
| CR-003 | Wix→Clerk plan sync loses subscription events                         | Medium | Medium     | Nightly reconciliation cron; drift alerting                                 | Open   | 2026-04-25 | —      |
| CR-004 | Users lose access during migration                                    | High   | Low        | Dry-run vs disposable Clerk tenant; 100%-match gate before prod; bridge-fallback catches misses | Open | 2026-04-25 | — |
| CR-005 | Clerk pricing shift                                                   | Medium | Medium     | Org features behind flag; graceful fallback to single-user mode              | Open   | 2026-04-25 | —      |
| CR-006 | Webhook signing secret leaked                                         | High   | Low        | Platform secret manager only; never in env files; quarterly rotation runbook | Open   | 2026-04-25 | —      |
| CR-007 | Token theft from browser                                              | High   | Low        | 60s token lifetime; no localStorage; HttpOnly session cookie; CSRF on /credentials | Open | 2026-04-25 | — |
| CR-008 | Frontend bundle size regression from Clerk SDK                        | Low    | Medium     | +80kb gzipped budget; CI fails over budget                                   | Open   | 2026-04-25 | —      |
| CR-009 | Wix Members email mismatch with Clerk verified email blocks migration | Medium | Medium     | Dry-run report flags mismatches; ops reviews before prod run                 | Open   | 2026-04-25 | —      |
| CR-010 | CLK session lag blocks TP MCP P2 for >1 week                          | High   | Medium     | CLK-0/1/2 are critical path; stub fallback exists in TP MCP P2               | Open   | 2026-04-25 | —      |

---

## 8. Open Questions Tracker

Live. Ambiguities raised during execution; each gets a resolution path. Mirrors CQ-001…006 in the spec plus any runtime additions.

| ID     | Question                                                                  | Raised     | Owner         | Resolution path                 | Resolved |
|:-------|:--------------------------------------------------------------------------|:-----------|:--------------|:--------------------------------|:---------|
| CQ-001 | Keep `@greatsumini/react-facebook-login` after Clerk adoption?            | 2026-04-25 | CLK-3 session | Default remove; confirm at CLK-3 | —        |
| CQ-002 | Keep `@react-oauth/google` when Clerk provides Google OAuth natively?     | 2026-04-25 | CLK-3 session | Default remove; confirm at CLK-3 | —        |
| CQ-003 | Proactive migration emails needed?                                        | 2026-04-25 | Product       | Defer; monitor bridge-fallback rate | —    |
| CQ-004 | Staging: separate Clerk tenant vs ring-fenced prod?                       | 2026-04-25 | CLK-0 session | Ring-fenced prod; revisit if data pollution | — |
| CQ-005 | `tp_connected` claim: push from webhook or poll on refresh?               | 2026-04-25 | CLK-2 session | Push from webhook; poll fallback | —       |
| CQ-006 | Clerk Backend API key rotation cadence?                                   | 2026-04-25 | CLK-5 session | Quarterly; documented in runbook | —       |
| CQ-007 | Does Wix CMS provide a reliable event for every plan change, or do we need polling? | 2026-04-25 | CLK-6 session | Verify during CLK-6 spike; fallback = nightly reconciliation cron | — |

---

## 9. DoD Sign-Offs

| Phase | Signed Off At       | Session ID     | Notes |
|:------|:--------------------|:---------------|:------|
|       |                     |                |       |

---

## 10. Feature Flag & Rollout Tracker

Live state of the `VITE_AUTH_IMPL` feature flag and related rollout controls.

| Env     | Flag Name          | Current Value | Target Value | Rollout % | Last Changed | Notes |
|:--------|:-------------------|:--------------|:-------------|:---------:|:-------------|:------|
| dev     | `VITE_AUTH_IMPL`   | `wix`         | `clerk`      | n/a       | —            | Flip to `clerk` at CLK-3 DoD |
| staging | `VITE_AUTH_IMPL`   | `wix`         | `clerk`      | n/a       | —            | Flip during CLK-4 soak |
| prod    | `VITE_AUTH_IMPL`   | `wix`         | `clerk`      | 0%        | —            | Ramped via Vercel Edge Config during CLK-6 |
| prod    | Bridge-fallback count | —          | 0 / 14d      | —         | —            | Metric, not a flag — ends at CLK-6 DoD |

---

## 11. Session Ledger

**Every session appends one row before exiting.** Even if no code changed.

| Date       | Session ID          | Phase   | What changed                                                                                      | Files touched                                                | Tests added | Coverage delta | Commits | Next step for next session |
|:-----------|:--------------------|:--------|:--------------------------------------------------------------------------------------------------|:-------------------------------------------------------------|:-----------:|:--------------:|:-------:|:---------------------------|
| 2026-04-25 | 2026-04-25-JRK-plan | master+all phase plans | CLK spec, ADR-0001, master plan, CLK-0…CLK-6 phase plans, wiki concept, memory, index updates | `trainingpeaks-mcp/docs/superpowers/specs/` + `plans/` + `docs/adr/` + `Jarasport/Race Day Hub/docs/superpowers/plans/` + `wiki/concepts/` | 0 | n/a | pending | Owner signs ADR-0001, then start CLK-0 task 1 (provision Clerk dev tenant) |

---

## 12. Session Protocol

### On start

1. `git fetch --all && git pull` (in both `jarasport-tp-mcp` and `Jarasport` if the phase touches RDH).
2. Read this file top-to-bottom. Resolve "Next step for next session" from the last row of §11.
3. Read the current phase's plan file.
4. Read handoff files for phases upstream of this one.
5. Check §3 Session Claims. Claim the phase.
6. If this phase touches RDH, also read `Jarasport/Race Day Hub/docs/superpowers/plans/2026-04-25-clerk-integration-pointer.md`.
7. Announce: "Resuming CLK-<N> task <M>. Last session ended at task <K>."

### Mid-session

- Every completed task is checked off in the phase plan.
- Every code-touching task adds at least one test in the same commit.
- New risks / questions / assumptions logged in §7 / §8 before session end.
- Conventional-commit style on both repos.

### On exit

1. Append §11 Session Ledger row. Include RDH commit SHA if touched.
2. Update §1 Phase Status Matrix.
3. Update §3 Session Claims (release or mark in-progress).
4. If phase complete: run DoD, if green add §9 row.
5. Write/update handoff file(s) (§4).
6. Commit this plan along with code in each affected repo.
7. Update the TP MCP master plan §1 CLK row if its status changed.

### Recommended execution context

- CLK-1, CLK-2, CLK-5: work in `jarasport-tp-mcp` repo, use a worktree per phase.
- CLK-3, CLK-4: work primarily in `Jarasport/Race Day Hub` repo.
- CLK-6: straddles both — advisable to open two worktrees in parallel.
- CLK-0: mostly dashboard + single-file ADR sign-off; no worktree needed.

---

## 13. Test-All-Code Policy

Matches the rebuild master plan §13, adapted for the frontend.

### Enforcement

- **Backend CI gate**: coverage ≥90% line, ≥85% branch on changed files.
- **Frontend CI gate**: coverage ≥70% line, ≥70% function, ≥60% branch on changed files.
- **Pre-commit hook**: rejects a commit adding `src/**/*.py` without a matching `tests/**/test_*.py`; same for RDH `src/**/*.{ts,tsx}` without `__tests__/**/*.test.{ts,tsx}`.

### Test kinds required per code kind

| Code kind | Required tests |
|:----------|:---------------|
| JWT verification | Unit + integration (stub JWKS) + negative-path (bad sig / expired / wrong iss / wrong azp / unknown kid) |
| CredentialStore backend | Unit + concurrency test (two async puts) + log-safety test |
| HTTP endpoint | Contract test + unit + integration + negative-auth test |
| Webhook handler | Unit + Svix signature test (positive + negative) + replay test + dedup test |
| React auth component | Vitest unit + MSW integration + Playwright e2e (for user-facing flows) |
| Migration script | Unit (transform logic) + dry-run integration against Wix fixture + idempotency test |
| Vercel serverless fn | Unit + contract test |

### Test-coverage discipline

- Assertion-free tests count as failures in PR review.
- Do not test private internals. Test behaviour.
- Mocks at boundaries only (JWKS, Clerk Backend API, Wix). `tp_core` internals use real objects in `tp_core` tests.

---

## 14. Definition of "Done" for the whole program

Must all be ticked before declaring CLK complete. Maps 1:1 to spec Success Criteria.

- [ ] Rebuild P2 middleware is real (`ClerkUserAuth`, not `StubClerkAuth`); p95 JWT verify < 5ms.
- [ ] Cross-user isolation test passes.
- [ ] Log-safety test passes across every endpoint and webhook.
- [ ] Every webhook event has a contract test; Svix verification test positive + negative.
- [ ] RDH production default: `VITE_AUTH_IMPL=clerk`.
- [ ] Happy-path E2E (sign-up → connect TP → first tool call) passes in Playwright against staging.
- [ ] Wix migration full prod run: zero orphaned active AthleteProfiles.
- [ ] Zero bridge-fallback events for 14 consecutive days.
- [ ] ADR-0001 signed.
- [ ] ADR-0002 (Wix coexistence) signed.
- [ ] Runbook covers: Clerk JWKS rotation, webhook secret rotation, credential-store key rotation, "Connect TP failed" triage.
- [ ] All §7 risks closed or accepted with rationale.
- [ ] All §8 questions resolved.

---

## 15. Index of Related Docs

- CLK spec: [../specs/2026-04-25-jarasport-clerk-integration-design.md](../specs/2026-04-25-jarasport-clerk-integration-design.md)
- ADR-0001: [../../adr/ADR-0001-clerk-boundary.md](../../adr/ADR-0001-clerk-boundary.md)
- TP MCP master: [./2026-04-25-jarasport-tp-mcp-master.md](./2026-04-25-jarasport-tp-mcp-master.md)
- TP MCP spec: [../specs/2026-04-25-jarasport-tp-mcp-design.md](../specs/2026-04-25-jarasport-tp-mcp-design.md)
- CLK-0: [./2026-04-25-jarasport-clerk-integration-CLK-0-tenant-and-adr.md](./2026-04-25-jarasport-clerk-integration-CLK-0-tenant-and-adr.md)
- CLK-1: [./2026-04-25-jarasport-clerk-integration-CLK-1-backend-jwt-middleware.md](./2026-04-25-jarasport-clerk-integration-CLK-1-backend-jwt-middleware.md)
- CLK-2: [./2026-04-25-jarasport-clerk-integration-CLK-2-credential-store-endpoints.md](./2026-04-25-jarasport-clerk-integration-CLK-2-credential-store-endpoints.md)
- CLK-3: [./2026-04-25-jarasport-clerk-integration-CLK-3-frontend-auth-shell.md](./2026-04-25-jarasport-clerk-integration-CLK-3-frontend-auth-shell.md)
- CLK-4: [./2026-04-25-jarasport-clerk-integration-CLK-4-connect-tp-flow.md](./2026-04-25-jarasport-clerk-integration-CLK-4-connect-tp-flow.md)
- CLK-5: [./2026-04-25-jarasport-clerk-integration-CLK-5-webhooks-lifecycle.md](./2026-04-25-jarasport-clerk-integration-CLK-5-webhooks-lifecycle.md)
- CLK-6: [./2026-04-25-jarasport-clerk-integration-CLK-6-wix-migration-cutover.md](./2026-04-25-jarasport-clerk-integration-CLK-6-wix-migration-cutover.md)
- RDH cross-repo pointer: `Jarasport/Race Day Hub/docs/superpowers/plans/2026-04-25-clerk-integration-pointer.md`
- Wiki concept: `wiki/concepts/clerk-identity-layer.md`
- Handoffs: `./HANDOFFS/`

---

_Last updated: 2026-04-25 by CLK planning session._
