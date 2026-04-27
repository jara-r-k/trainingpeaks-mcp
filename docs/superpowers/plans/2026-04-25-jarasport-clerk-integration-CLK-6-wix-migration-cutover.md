---
title: jarasport-clerk-integration-CLK-6-wix-migration-cutover
plan: CLK Phase 6 — Wix Migration + Cutover
status: not-started
owner: jara-r-k
date: 2026-04-25
project: Jarasport
parent: jarasport-clerk-integration-master
phase: CLK-6
actionable: blocked
blocked_on: CLK-4, CLK-5, TP-MCP-P3
next_action: (Blocked) Await CLK-4, CLK-5, and TP MCP P3 DoD
depends_on: CLK-4, CLK-5, TP-MCP-P3
---

# CLK-6 — Wix Migration + Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL — `superpowers:executing-plans` + `superpowers:verification-before-completion`. This is the riskiest phase; every destructive step has a pre-flight dry-run gate.

**Before you start:** read the [CLK master](./2026-04-25-jarasport-clerk-integration-master.md) §12 + `HANDOFFS/CLK-4-to-CLK-6.md` + `HANDOFFS/CLK-5-to-CLK-6.md`. Touch Wix CMS data only after the migration-report gate passes.

**Goal:** Bridge Wix Pricing Plans into Clerk metadata, migrate existing Wix Members to Clerk users (pre-creating accounts), ramp `VITE_AUTH_IMPL=clerk` from 0% → 100% in prod, retire the wixBridge auth path, and reach 14 days of zero bridge-fallback events.

**Architecture:**
- Wix → Clerk plan sync via a Vercel serverless function `api/wix-webhooks.ts`.
- Migration script `scripts/migrate-wix-to-clerk.ts` runs against Wix CMS + Clerk Backend API.
- Rollout controlled via Vercel Edge Config feature flag.
- `wixBridge.ts` auth methods deprecated → deleted at end of soak.

**Estimated effort:** 5 working days (includes 14-day soak in parallel with other work).

---

## Prerequisites

- CLK-4 DONE (Connect-TP flow live in staging).
- CLK-5 DONE (webhooks live, deletion path proven).
- TP MCP P3 DONE (tool migration complete — users actually need working tools on cutover).
- Owner has Wix API credentials with scopes `members.read`, `pricing-plans.read`, and webhook permissions.
- Owner has Clerk Backend API key for both tenants.

---

## Tasks

### Task 1 — Wix → Clerk plan sync (Vercel serverless fn)

- [ ] 1.1 Create `Jarasport/Race Day Hub/api/wix-webhooks.ts` (Vercel serverless function):
  - Accepts `POST /api/wix-webhooks`.
  - Verifies Wix webhook signature (Wix docs specify HMAC-SHA-256 with a shared secret).
  - Event types handled: `order.created`, `order.paid`, `order.canceled`, `order.expired`.
  - For each: look up Wix Member by ID, derive email, find Clerk user by email, patch `public_metadata.plan`.
  - Plan mapping table:
    - Monthly plan ID `75e5191b-dd6c-41c2-9d2c-77a9275d1489` → `plan = "monthly"`
    - Annual plan ID `8afd59bb-4ced-4938-831e-a0132657e66b` → `plan = "annual"`
    - Canceled/expired → `plan = "none"`
    - Seeded access codes (`YEARROUND2025`, etc.) → handled by migration script, not webhooks.
- [ ] 1.2 Write `api/__tests__/wix-webhooks.test.ts`:
  - Valid `order.paid` event → Clerk Backend API `users.updateMetadata` called.
  - Invalid signature → 401, no Clerk call.
  - Unknown event type → 200, no-op.
  - Clerk user not found → 404, metric `wix_webhook_orphan_total` incremented.
- [ ] 1.3 Configure Wix webhook in the Wix dashboard pointing at `https://raceday.jarasport.com.au/api/wix-webhooks` (and a staging equivalent).
- [ ] 1.4 Commit: `feat(wix-bridge): Vercel fn syncing Wix plans to Clerk metadata`.

### Task 2 — Reconciliation cron (R-003 mitigation)

- [ ] 2.1 Create `scripts/reconcile-wix-clerk-plans.ts`:
  - Lists all active Wix subscriptions.
  - Lists all Clerk users.
  - Diffs `Wix member.email → plan` against `Clerk user → public_metadata.plan`.
  - Outputs a report: users missing plan, users with wrong plan, orphaned Wix members without Clerk users, orphaned Clerk users without Wix members.
- [ ] 2.2 Schedule via GitHub Actions cron (nightly 02:00 UTC).
- [ ] 2.3 Alert on drift: if diff count > 0, open a GitHub issue.
- [ ] 2.4 Commit: `feat(wix-bridge): nightly reconciliation cron + drift alerts`.

### Task 3 — Split `wixBridge.ts`

- [ ] 3.1 Move billing-only calls (subscription lookup, access code validation) from `src/services/wixBridge.ts` to a new `src/services/wixBilling.ts`.
- [ ] 3.2 Leave auth methods (`getMemberToken`, `validateAccessCode` → app token) in `wixBridge.ts` marked `@deprecated since "CLK-6"`.
- [ ] 3.3 Update all callers to import billing from the new path.
- [ ] 3.4 Run `pnpm test:run` + `tsc --noEmit`; green.
- [ ] 3.5 Commit: `refactor(services): split wixBridge into wixBilling + legacy auth`.

### Task 4 — Migration script (dry-run first)

- [ ] 4.1 Create `Jarasport/Race Day Hub/scripts/migrate-wix-to-clerk.ts`:
  - Argparse: `--mode=dry-run|execute`, `--output=report.json`, `--tenant=dev|prod`.
  - Iterates Wix CMS `AthleteProfiles` collection.
  - For each row:
    - Look up Wix Member → verified email.
    - Check Clerk for existing user by email.
    - If found: update `private_metadata` with `wix_member_id`, `athlete_profile_id`, `public_metadata.plan` (if inferable).
    - If not found: dry-run records "would create"; execute-mode creates via Clerk Backend API with a password-reset invitation.
  - Emits `report.json` with per-row outcomes: `matched | created | failed | skipped` + reason.
- [ ] 4.2 Write `scripts/__tests__/migrate-wix-to-clerk.test.ts`:
  - Fixture Wix CMS data (3 members).
  - Mock Clerk Backend API.
  - Dry-run asserts no side effects.
  - Execute creates users for unseen emails, updates metadata for seen.
  - Idempotent: running twice produces identical final state.
- [ ] 4.3 Commit: `feat(migrate): Wix→Clerk migration script with dry-run mode`.

### Task 5 — Dry-run against prod Wix data (no side effects)

- [ ] 5.1 Run `npx tsx scripts/migrate-wix-to-clerk.ts --mode=dry-run --tenant=prod --output=report.json`.
- [ ] 5.2 Inspect `report.json`:
  - `would create` count matches expected seeded/known users.
  - `matched` count matches users who already signed up via CLK-3 (internal testers).
  - Zero `failed` rows OR: investigate each and patch data before execution.
- [ ] 5.3 Store the dry-run report in `docs/migration/2026-MM-DD-wix-clerk-dry-run.json` (git-LFS if large).
- [ ] 5.4 Owner review gate: owner signs off on the dry-run report before Task 6.

### Task 6 — Execute migration against prod

- [ ] 6.1 Owner-gated: only proceed after Task 5 sign-off.
- [ ] 6.2 Run `npx tsx scripts/migrate-wix-to-clerk.ts --mode=execute --tenant=prod --output=execute-report.json`.
- [ ] 6.3 Watch Clerk dashboard for new-user creations + Backend API rate limits.
- [ ] 6.4 Store execute report alongside dry-run.
- [ ] 6.5 Announce in session ledger + a short Slack/email to Jara with counts.

### Task 7 — Session-link helpers (auto-bridge)

- [ ] 7.1 Create `Jarasport/Race Day Hub/src/auth/sessionLink.ts`:
  - On RDH load while `VITE_AUTH_IMPL=wix`, check if user has an active Wix Member session.
  - If yes and email matches a pre-migrated Clerk user: call a Vercel fn `api/create-clerk-magic-link.ts` which uses Clerk Backend API to mint a one-time magic link; front-end auto-consumes it (invisible to user).
  - Emit telemetry event `session_bridge_invoked` + `session_bridge_fallback_triggered` (if user wasn't pre-migrated).
- [ ] 7.2 Test: MSW-mocked scenarios (matched + unmatched).
- [ ] 7.3 Commit: `feat(session-link): auto-bridge Wix → Clerk on first visit post-migration`.

### Task 8 — Gradual rollout

- [ ] 8.1 Configure Vercel Edge Config key `VITE_AUTH_IMPL_ROLLOUT_PCT` (or equivalent hashing strategy).
- [ ] 8.2 Day N: 10% of prod traffic receives `VITE_AUTH_IMPL=clerk` based on a deterministic hash of user IP or cookie (pre-sign-in) + Clerk user_id (post-sign-in).
- [ ] 8.3 Day N+2: 50% if error rate stable and bridge-fallback frequency <0.5%.
- [ ] 8.4 Day N+5: 100% if still clean.
- [ ] 8.5 Document commands + decision log in `docs/migration/rollout-log.md`.

### Task 9 — Monitor + 14-day soak

- [ ] 9.1 Dashboards:
  - `session_bridge_invoked` count and `session_bridge_fallback_triggered` count (target 0 by end of soak).
  - Clerk sign-in failure rate.
  - Wix→Clerk plan drift count (from Task 2 cron).
  - `/credentials` endpoint error rate.
- [ ] 9.2 Alert thresholds:
  - Bridge-fallback > 1% over 1h → page.
  - Clerk sign-in 5xx > 2% over 15min → page.
  - Plan drift > 0 at cron run → issue (non-page).
- [ ] 9.3 Daily review notes in `docs/migration/soak-log.md`.

### Task 10 — wixBridge auth retirement

- [ ] 10.1 Only after 14 consecutive days of zero `session_bridge_fallback_triggered` events.
- [ ] 10.2 Delete auth-path exports from `src/services/wixBridge.ts`:
  - `getMemberToken()`
  - `validateAccessCode()`
  - Any related types.
- [ ] 10.3 Keep the file with only deprecation comments and a link to `wixBilling.ts` for historical context.
- [ ] 10.4 Delete `VITE_AUTH_IMPL` flag entirely (Clerk is now the only path); keep env var but hard-code behaviour.
- [ ] 10.5 Run full test suite + type check; green.
- [ ] 10.6 Commit: `chore(wix): retire wixBridge auth path after 14-day soak`.

### Task 11 — ADR-0002: Wix coexistence (write-up)

- [ ] 11.1 Create `trainingpeaks-mcp/docs/adr/ADR-0002-wix-coexistence.md`:
  - Decision: Clerk is IdP; Wix is billing+CMS only post-migration.
  - Consequences: two vendors in the critical path but each with a single responsibility.
  - Migration history captured; future vendors evaluated against this split.
- [ ] 11.2 Commit: `docs(adr): ADR-0002 Wix coexistence decision`.

### Task 12 — Runbook additions

- [ ] 12.1 Extend `docs/RUNBOOK.md` with:
  - "User reports 'Connect TP failed'" triage (logs, credential status, TP API health).
  - "User reports 'I can't sign in'" triage (Clerk session, email verification, tenant config).
  - Wix→Clerk plan drift resolution.
  - Rollback procedure: revert `VITE_AUTH_IMPL=wix` via Edge Config (no code deploy needed).

### Task 13 — Handoff: CLK-6 → TP MCP P7

- [ ] 13.1 Create `HANDOFFS/CLK-6-to-P7.md`:
  - Cutover-complete date.
  - Final bridge-fallback count (target 0).
  - Credential-store user count.
  - Known post-cutover issues.
  - Approval to archive the old `trainingpeaks-mcp` fork README.

### Task 14 — Master plan closure

- [ ] 14.1 CLK master §1: CLK-6 → DONE.
- [ ] 14.2 CLK master §10: all envs `VITE_AUTH_IMPL=clerk` at 100%.
- [ ] 14.3 CLK master §14 program DoD: every box ticked.
- [ ] 14.4 §8 CQ-003 resolved (proactive emails weren't needed — zero fallback).
- [ ] 14.5 §8 CQ-007 resolved based on Task 2 findings.
- [ ] 14.6 §7 risks closed: CR-003, CR-004, CR-009 closed with date.
- [ ] 14.7 TP MCP master §1 CLK row: `DONE` with sign-off date.
- [ ] 14.8 TP MCP master §14 program DoD: `Migrated` checkbox can be ticked when P7 lands.

---

## DoD (extends master §5)

- [ ] Dry-run report reviewed + signed off by owner.
- [ ] Execute migration completed with zero `failed` rows (or all triaged).
- [ ] 14 consecutive days of zero bridge-fallback events.
- [ ] wixBridge auth path deleted.
- [ ] ADR-0002 signed.
- [ ] Runbook covers cutover + rollback.
- [ ] Reconciliation cron green for ≥7 consecutive nightly runs at CLK-6 close.

---

## Handoff Outputs

1. `HANDOFFS/CLK-6-to-P7.md`
2. `docs/adr/ADR-0002-wix-coexistence.md`
3. Extended `docs/RUNBOOK.md`
4. `docs/migration/` directory with dry-run + execute + rollout + soak logs.

---

## Rollback Triggers

Abort the rollout and revert to `VITE_AUTH_IMPL=wix` via Edge Config (single command, no deploy) if any of the following occur during soak:

- Clerk sign-in 5xx rate exceeds 5% over any 15-minute window.
- Bridge-fallback rate exceeds 2% over any 1-hour window.
- `/credentials` error rate exceeds 10% over any 15-minute window.
- Credential-store key compromised (assume: rotate master key + force re-connect).

Post-rollback: investigate, fix, redo dry-run before another attempt.

---

## Exit Criteria

- Tasks 1–14 complete.
- DoD green.
- Master §9 sign-off.
- CLK program DONE.
- TP MCP master §1 CLK row = DONE.
- Program-level DoD (master §14) all ticked.
