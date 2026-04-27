---
title: jarasport-clerk-integration-CLK-4-connect-tp-flow
plan: CLK Phase 4 — Connect-TrainingPeaks Flow
status: not-started
owner: jara-r-k
date: 2026-04-25
project: Jarasport
parent: jarasport-clerk-integration-master
phase: CLK-4
actionable: blocked
blocked_on: CLK-2, CLK-3
next_action: (Blocked) Await CLK-2 and CLK-3 DoD
depends_on: CLK-2, CLK-3
---

# CLK-4 — Connect-TrainingPeaks Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL — `superpowers:test-driven-development` + `superpowers:executing-plans`. Touches both RDH and `jarasport-tp-mcp`. Playwright e2e is required here (it was scaffolded-skipped in CLK-3).

**Before you start:** read the [CLK master](./2026-04-25-jarasport-clerk-integration-master.md) §12 + `HANDOFFS/CLK-2-to-CLK-4.md` + `HANDOFFS/CLK-3-to-CLK-4.md`.

**Goal:** Ship the end-to-end "Connect TrainingPeaks" user journey. A signed-in RDH user can upload their TP cookie (Path A — always available) OR run `tp-mcp auth-import --from-browser chrome` locally to upload without pasting plaintext into the UI (Path B — recommended). Connection status is visible; disconnect works. Playwright e2e covers the happy path against a staging deploy.

**Architecture:** New RDH screen `ConnectTrainingPeaks.tsx`; `/credentials` endpoint consumed via `tpMcpClient` from CLK-3; helper CLI `tp-mcp auth-import` ported from the existing fork (lives in `jarasport-tp-mcp/src/tp_mcp/cli.py`) and enhanced to upload via a signed Clerk session handshake.

**Estimated effort:** 3 working days.

---

## Prerequisites

- CLK-2 DONE (endpoints live).
- CLK-3 DONE (frontend shell + `tpMcpClient` + ProtectedRoute).
- Staging deploy target for RDH (Vercel preview or explicit staging) available.

---

## Tasks

### Task 1 — Screen scaffolding (RDH)

- [ ] 1.1 Write `__tests__/screens/ConnectTrainingPeaks.test.tsx`:
  - Renders "Not connected" state when `/credentials/status` returns `connected=false`.
  - Renders "Connected" state with age + last refresh when `connected=true`.
  - Renders error state on 500.
- [ ] 1.2 Create `src/screens/ConnectTrainingPeaks.tsx`:
  - Uses `tpMcpClient.credentials.status()` on mount + polled every 30s while visible.
  - Three visual states: not-connected, connected, error.
  - Uses Jarasport shadcn components (Card, Button, Alert) from `src/components/`.
- [ ] 1.3 Add route `/app/connect-training-peaks` behind `<ProtectedRoute>`.
- [ ] 1.4 Run tests; green.
- [ ] 1.5 Commit: `feat(connect-tp): screen with status polling`.

### Task 2 — Path A: manual cookie upload (TDD)

- [ ] 2.1 Extend `__tests__/screens/ConnectTrainingPeaks.test.tsx`:
  - Paste a cookie into textarea → submit → POST `/credentials` sent with body `{ tp_cookie }`.
  - 204 → status flips to `connected=true` after poll.
  - 400 (malformed) → inline error shown; textarea retains value.
  - 422 (rejected by TP validator) → helpful message with link to help.
- [ ] 2.2 Implement cookie-upload form in the screen:
  - Textarea + "Connect" button.
  - Help text pointing to a `/docs/connect-tp.md` page (create in Task 5).
  - Client-side validation: non-empty, looks like a cookie header (no `\r\n`, length <8k).
- [ ] 2.3 Run tests; green.
- [ ] 2.4 Commit: `feat(connect-tp): manual cookie upload path`.

### Task 3 — Disconnect flow (TDD)

- [ ] 3.1 Test: connected state shows "Disconnect" button → click → confirm dialog → DELETE `/credentials` → status flips to `connected=false`.
- [ ] 3.2 Test: cancel in confirm dialog → no API call.
- [ ] 3.3 Implement using shadcn `<AlertDialog>`.
- [ ] 3.4 Commit: `feat(connect-tp): disconnect with confirmation dialog`.

### Task 4 — Path B: helper CLI (`jarasport-tp-mcp`)

- [ ] 4.1 Port the existing `tp-mcp auth --from-browser chrome` logic from the fork into `jarasport-tp-mcp/src/tp_mcp/cli.py` with a new subcommand `auth-import`.
- [ ] 4.2 The CLI:
  - Prompts the user for a Clerk session ticket (URL printed by RDH when the user clicks "Use CLI helper").
  - Extracts the TP cookie from the selected browser.
  - Exchanges the ticket for a short-lived JWT via Clerk's `client.signIn.attemptTicketSignIn` (or equivalent; verify exact API in CLK-4 spike).
  - POSTs `/credentials` with that JWT.
- [ ] 4.3 RDH: add a "Use CLI helper" button that generates a one-time ticket via Clerk Backend API (requires a tiny Vercel serverless function `api/create-clerk-ticket.ts` to hold the Backend secret).
- [ ] 4.4 Write `tests/test_cli_auth_import.py`:
  - Mock the browser cookie extraction.
  - Mock the ticket → JWT exchange.
  - Assert POST body is `{ "tp_cookie": "<value>" }`.
- [ ] 4.5 Commit: `feat(cli): auth-import subcommand for Clerk-handshake cookie upload`.

### Task 5 — User-facing documentation

- [ ] 5.1 Create `Jarasport/Race Day Hub/public/docs/connect-tp.md`:
  - Why we need the cookie.
  - Path A: step-by-step with screenshots (capture via Playwright in Task 8).
  - Path B: CLI install + run command.
  - Troubleshooting: common failure modes (expired cookie, wrong browser profile).
- [ ] 5.2 Link from the ConnectTrainingPeaks screen via a Help link.
- [ ] 5.3 Commit: `docs(connect-tp): user-facing help page`.

### Task 6 — `tp_connected` claim population

- [ ] 6.1 On successful `POST /credentials`, the backend calls Clerk Backend API to set `public_metadata.tp_connected = true`. On `DELETE /credentials`, set to `false`.
- [ ] 6.2 Add a new backend dependency: `clerk-sdk-python` (needed here for Backend API; does NOT pollute `tp_core`).
- [ ] 6.3 Guard: when `CLERK_BACKEND_SECRET_KEY` is unset (dev), skip the metadata update and log a WARN.
- [ ] 6.4 Write `tests/tp_mcp/test_routes_credentials_metadata.py`:
  - Mock Clerk SDK.
  - Assert `users.update_user_metadata(user_id, public_metadata={"tp_connected": True})` called on successful POST.
  - Assert reverse on DELETE.
- [ ] 6.5 Commit: `feat(credentials): sync tp_connected to Clerk metadata on put/delete`.

### Task 7 — RDH rendering of `tp_connected` claim

- [ ] 7.1 On pages other than ConnectTrainingPeaks, use the JWT's `tp_connected` claim (cached by Clerk) to gate UI elements — avoids a round-trip to `/credentials/status`.
- [ ] 7.2 If claim says `false`, show a "Connect TrainingPeaks" banner with CTA.
- [ ] 7.3 If claim says `true`, no banner.
- [ ] 7.4 Test: mock `useAuth()` with each claim value, assert banner presence.
- [ ] 7.5 Commit: `feat(connect-tp): banner driven by tp_connected JWT claim`.

### Task 8 — Playwright e2e happy path

- [ ] 8.1 Unskip and flesh out `e2e/auth.spec.ts` from CLK-3:
  - Sign up new user via Clerk test mode (`testing_token`).
  - Land on `/app/connect-training-peaks` (redirected from welcome).
  - Upload a fake cookie (backend in dev mode accepts anything non-empty).
  - Assert "Connected" state renders with age.
  - Click "Disconnect", confirm, assert back to "Not connected".
- [ ] 8.2 Run against a staging deploy (`VITE_AUTH_IMPL=clerk` is required for this test).
- [ ] 8.3 `@axe-core/playwright`: zero violations on `/sign-in`, `/sign-up`, `/app/connect-training-peaks`.
- [ ] 8.4 Commit: `test(e2e): happy-path Connect-TP under Clerk`.

### Task 9 — Staging rollout with query-string toggle

- [ ] 9.1 Deploy RDH to a staging URL with `VITE_AUTH_IMPL=wix` default but a query-string override `?preview=clerk` that flips to Clerk at runtime.
- [ ] 9.2 Implement the override in `src/auth/authImpl.ts` (non-persistent, sessionStorage-only).
- [ ] 9.3 Document how to share `staging.raceday.jarasport.com.au/?preview=clerk` with internal testers.

### Task 10 — Error taxonomy + observability

- [ ] 10.1 Every failure mode in the screen logs a structured event via the RDH analytics service (if present) or console in dev.
- [ ] 10.2 Backend: increment `credential_operations_total{action="put", outcome}` with outcomes `success`, `validator_rejected`, `store_error`, `clerk_metadata_error`.

### Task 11 — Handoff: CLK-4 → CLK-6

- [ ] 11.1 Create `HANDOFFS/CLK-4-to-CLK-6.md`:
  - Routes added.
  - Disconnect behaviour.
  - Status polling cadence (30s).
  - Known limits (textarea size, rate limits once P4 lands).

### Task 12 — Master plan updates

- [ ] 12.1 CLK master §1: CLK-4 → DONE.
- [ ] 12.2 CLK master §6: check off `ConnectTrainingPeaks.tsx`, CLI `auth-import`.
- [ ] 12.3 CLK master §10 Feature Flag: staging flipped to `clerk` for `?preview=clerk` overrides; prod remains `wix` at 0%.
- [ ] 12.4 RDH plan pointer updated with CLK-4 commit SHAs.

---

## DoD (extends master §5)

- [ ] Playwright happy-path passes against staging.
- [ ] Accessibility: zero axe violations on the three covered pages.
- [ ] `tp_connected` metadata sync verified end-to-end.
- [ ] Help doc published at `/docs/connect-tp.md`.
- [ ] Coverage gates hold across both repos.

---

## Handoff Outputs

1. `HANDOFFS/CLK-4-to-CLK-6.md`
2. `Jarasport/Race Day Hub/public/docs/connect-tp.md`
3. Updated RDH plan pointer.

---

## Exit Criteria

- Tasks 1–12 complete.
- DoD green.
- Master §9 sign-off.
- Staging exercised internally; ready for CLK-5 webhook pairing.
