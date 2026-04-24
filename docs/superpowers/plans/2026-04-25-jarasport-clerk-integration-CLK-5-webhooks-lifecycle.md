---
title: jarasport-clerk-integration-CLK-5-webhooks-lifecycle
plan: CLK Phase 5 — Clerk Webhooks + Lifecycle
status: not-started
owner: jara-r-k
date: 2026-04-25
project: trainingpeaks-mcp
parent: jarasport-clerk-integration-master
phase: CLK-5
actionable: blocked
blocked_on: CLK-2
next_action: (Blocked) Await CLK-2 DoD
depends_on: CLK-2
---

# CLK-5 — Webhooks + Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL — `superpowers:test-driven-development` + `superpowers:executing-plans`. Security-sensitive: all inbound requests are Svix-verified before any state change.

**Before you start:** read the [CLK master](./2026-04-25-jarasport-clerk-integration-master.md) §12 + `HANDOFFS/CLK-2-to-CLK-5.md`.

**Goal:** Implement `POST /webhooks/clerk` with Svix signature verification, replay protection, dedup, handling for `user.deleted` and `user.updated`, and a signing-secret rotation runbook. Runnable in parallel with CLK-4.

**Architecture:** `tp_mcp/webhooks/clerk.py` with a `svix` signature verifier; in-process LRU for dedup keyed by `svix-id`; 5-minute replay window using `svix-timestamp`; handlers invoke `CredentialStore.delete(user_id)` on `user.deleted`; logs `user.updated` without side effects.

**Tech Stack:** `svix>=1.0` (official Clerk-recommended SDK), `cachetools` for LRU + TTL, `pytest-asyncio`, `freezegun`.

**Estimated effort:** 2 working days.

---

## Prerequisites

- CLK-2 DONE.
- `CLERK_WEBHOOK_SECRET` provisioned in the platform secret store.

---

## Tasks

### Task 1 — Dependencies

- [ ] 1.1 Add `svix>=1.28,<2` and `cachetools>=5.3,<6`.
- [ ] 1.2 Commit: `chore(deps): add svix + cachetools for CLK-5`.

### Task 2 — Svix signature verifier (TDD)

- [ ] 2.1 Write `tests/tp_mcp/test_webhooks_svix.py`:
  - Positive: valid signed payload verifies.
  - Negative: wrong secret → rejected.
  - Negative: tampered body → rejected.
  - Negative: missing `svix-signature` header → rejected.
  - Negative: `svix-timestamp` > 5min old → rejected with `replay_window_exceeded`.
- [ ] 2.2 Create `src/tp_mcp/webhooks/svix_verifier.py`:
  - Thin wrapper around `svix.webhooks.Webhook.verify(body, headers)`.
  - Additional clock-skew check on `svix-timestamp` (5min window).
- [ ] 2.3 Fixtures: `tests/fixtures/clerk-webhooks/{user_deleted,user_updated}.json` with pre-signed headers.
- [ ] 2.4 Run tests; green.
- [ ] 2.5 Commit: `feat(webhooks): Svix signature verification with replay window`.

### Task 3 — Dedup (TDD)

- [ ] 3.1 Write `tests/tp_mcp/test_webhooks_dedup.py`:
  - Same `svix-id` within 1h → second call returns 202 Accepted (dedup) without re-running handler.
  - Same `svix-id` after 1h TTL → re-runs handler (expected Svix retry behaviour is within 24h; our LRU is 1h so we rely on Svix idempotency within that window and replay-rejection beyond).
  - LRU caps at 10k entries.
- [ ] 3.2 Create `src/tp_mcp/webhooks/dedup.py`:
  - `class SvixDedupCache(maxsize=10_000, ttl=3600)` using `cachetools.TTLCache`.
  - `async check_and_mark(svix_id: str) -> bool` — returns `True` if new, `False` if seen.
- [ ] 3.3 Commit: `feat(webhooks): svix-id dedup with 1h TTL`.

### Task 4 — Event router (TDD)

- [ ] 4.1 Write `tests/tp_mcp/test_webhooks_router.py`:
  - `user.deleted` event → `CredentialStore.delete(user_id)` called, 200 returned.
  - `user.deleted` where user had no cookie → still 200 (idempotent delete).
  - `user.updated` event → no store mutation, INFO log emitted with user_id_hash + fields changed summary, 200 returned.
  - Unknown event type (e.g. `organization.created`) → 200, DEBUG log, no action.
  - Malformed event body → 400.
- [ ] 4.2 Create `src/tp_mcp/webhooks/router.py`:
  - Pydantic model per event.
  - Dispatch via an enum-keyed dict.
  - Audit log row on every handled event.
- [ ] 4.3 Commit: `feat(webhooks): event router with user.deleted handler`.

### Task 5 — `/webhooks/clerk` endpoint

- [ ] 5.1 Integrate Tasks 2–4 into a FastAPI endpoint `POST /webhooks/clerk`.
- [ ] 5.2 Flow:
  1. Read raw body + headers.
  2. `SvixVerifier.verify()` — 401 on failure.
  3. Check `svix-timestamp` replay window — 401 on failure.
  4. `SvixDedupCache.check_and_mark()` — 202 on dedup hit.
  5. Parse event, dispatch.
  6. Return 200 on success.
- [ ] 5.3 Mount under the FastAPI app from CLK-2.
- [ ] 5.4 Integration test: send the signed fixture webhook via `httpx.AsyncClient`, assert end-to-end behaviour.
- [ ] 5.5 Commit: `feat(webhooks): /webhooks/clerk endpoint end-to-end`.

### Task 6 — Structured logging + metrics

- [ ] 6.1 Log every webhook decision point:
  - `webhook.received` (with svix-id, event_type, user_id_hash)
  - `webhook.signature_valid`
  - `webhook.dedup_hit`
  - `webhook.handler_invoked`
  - `webhook.error` (on failures)
- [ ] 6.2 Metrics:
  - Counter `clerk_webhook_events_total{event_type, outcome}` (outcomes: `handled`, `dedup`, `unknown`, `rejected`).
  - Histogram `clerk_webhook_duration_seconds{event_type}`.
- [ ] 6.3 Commit: `feat(webhooks): structured logs + metrics`.

### Task 7 — Signing-secret rotation runbook

- [ ] 7.1 Create `docs/RUNBOOK.md` (or append if exists).
- [ ] 7.2 Document procedure:
  1. In Clerk dashboard, rotate webhook endpoint signing secret; Clerk supports overlap windows.
  2. Deploy `jarasport-tp-mcp` with `CLERK_WEBHOOK_SECRET_NEXT` populated alongside `CLERK_WEBHOOK_SECRET`.
  3. Verifier accepts either during overlap window.
  4. After Clerk cutover, remove `CLERK_WEBHOOK_SECRET`, rename `NEXT` to primary.
  5. Confirm no 401s in metrics for 24h.
- [ ] 7.3 Add a `scripts/validate-webhook-secret.py` that pings Clerk's webhook test-send and verifies locally.
- [ ] 7.4 Commit: `docs(runbook): webhook signing-secret rotation procedure`.

### Task 8 — Register endpoint in Clerk dashboard

- [ ] 8.1 In Clerk dev tenant, add webhook endpoint pointing to the staging MCP URL `/webhooks/clerk`.
- [ ] 8.2 Subscribe to `user.deleted`, `user.updated`, and `organization.*` (future-ready).
- [ ] 8.3 Capture `CLERK_WEBHOOK_SECRET` (dev) into platform secret manager.
- [ ] 8.4 Repeat for prod tenant once prod MCP URL is known (defer if TP MCP P5 hasn't deployed; register during CLK-6 cutover).

### Task 9 — Manual exercise in staging

- [ ] 9.1 Create a test Clerk user in the dev tenant, set `public_metadata.plan=annual`.
- [ ] 9.2 Perform a `PUT /credentials` with a dummy cookie as that user.
- [ ] 9.3 Delete the user via dashboard.
- [ ] 9.4 Within 60s, `GET /credentials/status` for that user should error or return `connected=false`.
- [ ] 9.5 Verify the audit log contains the webhook-triggered delete.
- [ ] 9.6 Record in session ledger.

### Task 10 — Handoff: CLK-5 → CLK-6

- [ ] 10.1 Create `HANDOFFS/CLK-5-to-CLK-6.md`:
  - Webhook endpoint URL format.
  - Registered events.
  - Dedup + replay parameters.
  - Signing-secret rotation link (`docs/RUNBOOK.md`).

### Task 11 — Master plan + open-question resolution

- [ ] 11.1 CLK master §1: CLK-5 → DONE.
- [ ] 11.2 §6: check off `webhooks/clerk.py`.
- [ ] 11.3 §8 CQ-006: resolved — "Quarterly; runbook in docs/RUNBOOK.md".

---

## DoD (extends master §5)

- [ ] Svix verification passes positive + all four negative cases.
- [ ] Dedup test passes.
- [ ] Manual exercise in staging: user deletion triggers credential deletion within 60s.
- [ ] Runbook exercised end-to-end once (rotation simulation with two secrets in env).
- [ ] Metrics scraped and confirmed present.

---

## Handoff Outputs

1. `HANDOFFS/CLK-5-to-CLK-6.md`
2. `docs/RUNBOOK.md` (new or appended)

---

## Exit Criteria

- Tasks 1–11 complete.
- DoD green.
- Master §9 sign-off.
- Webhook endpoint live in dev (and prod if feasible).
- CLK-6 unblocks (in conjunction with CLK-4).
