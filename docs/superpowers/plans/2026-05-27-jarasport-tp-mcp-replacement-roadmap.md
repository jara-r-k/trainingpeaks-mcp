---
type: plan
title: jarasport-tp-mcp Replacement Roadmap (TypeScript, Clerk-fronted)
slug: 2026-05-27-jarasport-tp-mcp-replacement-roadmap
date: 2026-05-27
parent: 2026-04-25-jarasport-tp-mcp-master.md
supersedes:
  - 2026-04-25-jarasport-tp-mcp-master.md (Python design — superseded for the language pivot; Clerk boundary + ADR-0001 carry forward)
  - 2026-04-25-jarasport-tp-mcp-P0-foundations.md (Python scaffold — superseded; TS equivalent in §5 P0)
related:
  - 2026-04-25-jarasport-tp-mcp-master.md
  - 2026-04-25-jarasport-tp-mcp-P0-foundations.md
  - ../adr/ADR-0001-clerk-boundary.md
  - ../../../Jarasport/Race Day Hub/docs/superpowers/plans/2026-05-09-coach-tp-rest-proxy.md
  - ../../.omc/findings-stream1.md
  - ../../.omc/findings-stream2.md
  - ../../.omc/deltas/recommended-actions.md
  - ../../.omc/deltas/tools-parity-matrix.md
  - ../../.omc/deltas/auth-env-contract.md
  - ../../.omc/deltas/breaking-changes.md
  - ../../.omc/deltas/http-client-parity.md
status: REVISED — pending re-review
revision: 1
critic_review: .omc/critic-roadmap-review.md
owner: jara-r-k
repo: ~/projects/jarasport-tp-mcp/ (to be created — locked)
language: TypeScript (Node ≥ 20)
identity: Clerk (per ADR-0001)
---

# jarasport-tp-mcp Replacement Roadmap

> **Why this exists.** The original Python program (master + P0 plans dated 2026-04-25) committed to a Python rebuild. After Stream 1–3 audits, three facts moved us off that path:
>
> 1. Race Day Hub already ships a working TS port of the TP REST surface (`Race Day Hub/api/_lib/tp-client.ts`). It is read-only, deliberately narrow, and battle-tested by the coach cron. Throwing it away to rewrite in Python costs months.
> 2. The new MCP must live behind Clerk (ADR-0001) and integrate with the same Vercel deployment that hosts RDH. Same edge runtime, same auth middleware, same env. A Python service would be a second deployment surface.
> 3. The Python fork's worst defects (events.py mega-file, cache invalidation bug, urllib3/idna CVEs, in-function imports) all trace back to Python-idiomatic patterns that TS sidesteps for free. Porting the bugs forward is a wasted commitment.
>
> The Python plans are not deleted — they remain a reference for the Clerk boundary, parity matrix, and phase discipline. The language pivot is the only structural change. Everything else (Clerk JWT, per-user credential store, tool surface, cutover criteria) carries over.

---

## §1 Executive Summary

- **Why now.** RDH cannot scale past Coach Simon while the cookie lives in one env var and the upstream Python MCP is single-tenant. Stream 2 also flagged urllib3 + idna CVEs in the Python venv that TS sidesteps natively, plus a rate-limit-bypass race in `tp_reorder_workouts` that the TS port already handles correctly via promise coalescing.
- **Target end state.** A TypeScript MCP server at `~/projects/jarasport-tp-mcp/` exposing the read-heavy TrainingPeaks surface Race Day Hub depends on, authenticated by Clerk JWT (per ADR-0001), deployable to the same Vercel project as RDH, with per-user TP cookie storage server-side and one-tool-per-file discipline.
- **Cutover headline.** Race Day Hub flips a single env var (`TP_MCP_IMPL=jarasport`) and stops calling `tp-client.ts` directly. The upstream Python fork at `jara-r-k/trainingpeaks-mcp` is archived with a deprecation README. Coach Simon's TP cookie continues to work without rotation.
- **Scope discipline.** This roadmap does not propose feature work. It is a *displacement* plan — every tool ships at parity with the Python behaviour we are replacing, minus the defects flagged in Streams 1–2. New features (multi-tenant SaaS, additional sports, mobile clients) are explicitly out of scope (§10).
- **Phase shape.** P0 Foundations → P1 MVP tools → P2 Should-have tools → P3 Defer (writes, library, niche analyses) → P4 Cutover. Five phases. Solo dev with Claude. Conservative effort: ~6–10 weeks calendar.

---

## §2 Status Audit of Existing Plans

### `2026-04-25-jarasport-tp-mcp-master.md` (Python master)

**Shipped:** Spec written. Master coordination doc written. P0 plan written. ADR-0001 (Clerk boundary) drafted and accepted. Risk register and open-questions tracker established. Session ledger started (one entry — the planning session itself).

**Outstanding:** All implementation phases (P0–P7). No code written. No PyPI name claimed. No GitHub repo created (`jara-r-k/jarasport-tp-mcp` does not exist yet — confirmed 2026-05-27).

**Stale:** The language commitment (Python) is now stale — superseded by this roadmap. Everything else (Clerk wire format, ownership matrix, parity matrix structure, DoD discipline, session ledger pattern) carries forward unchanged. The §6 Parity Matrix in the master plan is reused as the §4 tool inventory below; the only change is the implementation column moves from Python-ports to TS-handlers.

**Action:** Mark master as `superseded for language; spirit preserved`. Keep it as the reference for the Clerk wire format, parity discipline, and session ledger pattern. Cross-link from this roadmap's front matter.

### `2026-04-25-jarasport-tp-mcp-P0-foundations.md` (Python P0)

**Shipped:** Plan written, no work executed (Task 1 — PyPI name check — never run; repo never created).

**Outstanding:** Every task.

**Stale:** Python-specific bits (uv, hatchling, mypy, pytest, pip-audit, gitleaks, ruff, pyproject.toml). The principles transfer cleanly to TS though — every Python tool has a clear TS analogue (uv → pnpm; hatchling → tsup/tsc; mypy → tsc strict; pytest → vitest; ruff → biome/eslint; pip-audit → npm audit; bandit → semgrep; pre-commit hooks → lefthook/husky; trivy → still trivy).

**Action:** Use the Python P0 plan as the structural template for the TS P0. Reuse the §1 file structure, the §2 pyproject.toml table-of-contents (translate to package.json + tsconfig.json), the §7 test-coverage enforcement (translate to a tsc-based check), and the §11 security gate (semgrep + npm audit + trivy). Reuse the §16 branch-protection invocation almost verbatim.

### `Race Day Hub/.../2026-05-09-coach-tp-rest-proxy.md` (TS port we're displacing)

**Shipped:** The plan was executed. `Race Day Hub/api/_lib/tp-client.ts`, `tp-types.ts`, `auth.ts`, `coach-snapshot-strip.ts`, `tp-sync-queue.ts` all exist on disk. Wix singleton `TPCoachAuth` collection is live. `/api/cron/coach-tp-refresh` (or its equivalent in the current RDH) is running. Coach Simon's cookie lives in `TP_COACH_AUTH_COOKIE` (TS) and rotates via Wix.

**Outstanding:** Multi-tenancy. The TS port is single-coach. Per-user credential storage was deferred to a later phase ("Multi-tenant Clerk auth — deferred until the second paying coach exists" per the plan's Out-of-Scope section). That is now this roadmap's P0 and P1 work.

**Stale:** Only the env var name (`TP_COACH_AUTH_COOKIE` will be retired in favour of `TP_AUTH_COOKIE` — see §3 and §8). Everything else is the seed for `jarasport-tp-mcp/src/tp-core/` — we extract, generalise, and rehome.

**Action:** P0 starts by lifting `tp-client.ts`, `tp-auth.ts`, `tp-mappers.ts`, `tp-types.ts` into the new repo and elevating them. Not a rewrite. We carry the existing test corpus too.

### ADR-0001 (Clerk boundary)

**Shipped:** Accepted 2026-04-25. Wire format, ownership matrix, JWT claims, webhook contract, `/credentials` API all specified.

**Outstanding:** Implementation (lives in this roadmap's P0).

**Stale:** Nothing. The ADR is language-agnostic — every claim still holds for a TS implementation. The `tp_mcp/auth/clerk.py` path in the ownership matrix becomes `src/auth/clerk.ts`. The `tp_mcp/credentials/*` path becomes `src/credentials/*`. The `tp_mcp/webhooks/clerk.py` path becomes `src/webhooks/clerk.ts`. No semantic change.

**Action:** Carry forward unchanged. The wire format is the contract; this roadmap only specifies how TS implements it.

---

## §3 Architectural Decisions

### A1 — Repo location and language

- **Repo:** `~/projects/jarasport-tp-mcp/` (sibling of `trainingpeaks-mcp/`, RDH, ArbitrageSystem, etc.). **Locked** per user decision 2026-05-27. Will resolve to GitHub repo `jara-r-k/jarasport-tp-mcp`.
- **Language:** TypeScript on Node ≥ 20 (LTS). Strict mode. No `any` without explicit comment + reason (mirrors the Python plan's no-`Any`-without-reason rule).
- **Why TS and not Python:** see §1 bullets. Short version: the existing TS code is the de facto reference implementation already; the urllib3/idna CVE class disappears in the Node world (Node uses its native fetch / undici); Vercel deployment surface is unified with RDH.

### A2 — MCP framework

- **Choice:** `@modelcontextprotocol/sdk` (TypeScript reference SDK from Anthropic). Use the high-level `Server` API plus `StdioServerTransport` for local dev and the streamable HTTP transport for the Vercel-hosted multi-tenant flow.
- **Alternative considered and rejected:** FastMCP-TS (`fastmcp` npm package, Punkpeye). Excellent ergonomics, but adds a layer between us and the spec; we want full control over the Clerk middleware and the credential-resolution hook. Punkpeye's framework can be revisited at P2 if we want a thinner adapter — but the official SDK is the safe default.
- **Why not stay with stdio-only:** Race Day Hub is a deployed web app. It needs a remote MCP. We support both: stdio for local Claude Code dev, HTTP/SSE for Vercel.

### A3 — Identity boundary

- **Decision:** Clerk JWT in, TP cookie out. Per ADR-0001. The MCP verifies a Clerk-signed JWT on every incoming call (HTTP transport) and resolves the caller's `user_id` from the `sub` claim. From the `user_id` we look up the encrypted TP cookie in our credential store and use that to talk to TP. **The MCP never accepts a raw TP cookie from a client over the wire.**
- **Stdio dev mode escape hatch:** Local stdio sessions (Claude Code) accept a `TP_AUTH_COOKIE` env var as a single-user fallback. This is gated by `TP_MCP_AUTH_IMPL=env`, which is refused in production per ADR-0001's env table.
- **Why this matters for cutover:** RDH's current `Authorization` header injection is already Clerk-aware (RDH owns the ClerkProvider). The Race Day Hub `tp-client.ts` reads the cookie from a Wix singleton — that responsibility moves to `jarasport-tp-mcp`'s credential store under Clerk-keyed lookup. RDH no longer touches the cookie at all post-cutover.

### A4 — Deployment surface

- **Local dev:** stdio (Claude Code, Claude Desktop). Same `claude_desktop_config.json` shape as the upstream Python fork — drop-in replacement at the config level.
- **Production:** Vercel Functions, **Node runtime** for the MCP server family. **Evidence-corrected rationale (revision 1):** RDH's TP-touching endpoints today all run `runtime: 'edge'` (verified: `api/cron/tp-coach-deep-sync-worker.ts:54`, `tp-coach-deep-sync-kickoff.ts:29`, `tp-freshness-check.ts:20`, `tp-coach-roster-aggregate.ts:26`, `api/coach-tp-sync.ts:1`, `api/sync-profile.ts:1`, `api/tp-sync.ts:1`, etc.). Edge *can* fanout — RDH does it via the `claimNext/markDone` per-athlete worker decomposition. The MCP chooses Node anyway because:
  1. **`@clerk/backend` JWT verification surface** — `verifyToken` works on edge but the broader `@clerk/backend` SDK (session lookup, user lookup) has Node-only code paths we may want during P0–P2.
  2. **`better-sqlite3` credential store (dev)** is Node-only; staying on Node keeps dev/prod runtimes uniform until Q-102 picks a prod backend.
  3. **MCP `StreamableHTTPServerTransport`** uses streaming patterns easier to debug on Node (raw `Response` body manipulation, `AsyncIterable` from `@modelcontextprotocol/sdk`).
  4. **`maxDuration: 800`** on Pro (or 300 on Hobby) is available on Node, not on edge — edge is capped at 25 s response-start. We expect single MCP requests to stay well under 25 s (we are NOT doing roster fanout inside one MCP request — that's RDH's cron decomposing into per-athlete `claimNext` workers calling individual MCP tools), but the optionality of long-running tools (e.g. `tp_analyze_workout` cross-host latency) is worth the Node choice.
- **Revisit at P2:** if the credential store lands on Vercel KV/Postgres (Q-102) and we're not using `better-sqlite3` in prod, edge becomes viable for read-heavy tool families. P2 may carve out an edge variant for hot reads.
- **Why Vercel and not Fly.io/Cloud Run:** RDH is already on Vercel. Co-located. Single Vercel project, two function families (RDH UI + MCP routes). Resolves Q-002 from the Python master plan.

### A5 — Cache strategy

- **Decision:** No module-scope **response** cache. Per-request cache only for tool-result data. Per Stream 3 finding (`breaking-changes.md` §3): "module-scope state, wrong layer for Vercel edge". A Vercel Node lambda instance has unpredictable warm/cold behaviour; module-scope state leaks across users when warm and disappears entirely when cold. Both behaviours are wrong for response data.
- **Implementation (response cache):** `Map<string, {expiresAt, data}>` constructed per `MCPRequest`, passed via the context object exposed to tool handlers. Lives only for the request duration.
- **Token cache — disambiguated (revision 1):** there are two distinct caches with different lifecycles. Pick consciously per layer:
  - **Clerk JWKS cache:** module-scope, 10-min TTL, 24h stale-serve. Safe because JWKS is global (not per-user) and identical across all lambda instances. ADR-0001 mitigation.
  - **TP access-token cache:** persisted in the **credential-store row** keyed by `user_id`, with `tp_access_token`, `tp_access_token_expires_at` columns. TTL ~55 min (TP's 60 min minus 5 min buffer). **This is database state, not in-memory.** The 55-min TTL is enforced by the row, not by a Map. Survives lambda cold start. Survives concurrent lambdas. Race condition on refresh handled by the credential store's per-row write lock (Postgres `SELECT FOR UPDATE` or SQLite `BEGIN EXCLUSIVE`) — pick one when Q-102 resolves.
  - **Promise coalescing on refresh:** in-memory per-lambda `Map<user_id, Promise<TPAccessToken>>` to avoid duplicate refreshes *within* a single lambda. Acceptable to do duplicate refresh across lambda instances (rare, idempotent at TP's side, logged). Alarm if cross-lambda duplicates exceed N/hour (signals warm-pool churn or a refresh storm).
- **Write invalidation:** writes go to TP directly, and the response is returned. No response cache to invalidate. Reads following a write happen on the next request. (Stream 1's `cache list-invalidation` bug — exact-key vs prefix — does not arise because we are not building a list cache. If we later add one, the Stream 1 fix is the design — prefix-match invalidation.)

### A6 — Test strategy

- **Default mocking layer:** intercept HTTP at the fetch boundary using `msw` (Node mode) or a thin `fetch` mock. Mirrors the Python project's `respx`. Same philosophy: do not mock our own internals, only mock the boundary with TP.
- **Coverage gate:** 90% line, 85% branch on changed files (carry over from Python P0). Enforced in CI.
- **Test layers (mirroring Python plan §13):**
  - **Unit:** every pure function (mappers, validators, helpers).
  - **Contract:** every MCP tool round-trips its JSON Schema input/output.
  - **Integration:** every TP API path exercised via mocked HTTP.
  - **Property:** parsers tested with `fast-check` (TS equivalent of `hypothesis`).
  - **E2E (defer to P3):** a smoke test against a real Clerk dev tenant + a recorded TP cassette.

### A7 — Env contract (resolving the rename)

- **Canonical:** `TP_AUTH_COOKIE` for the dev/stdio fallback cookie. Matches the upstream Python fork (`auth/storage.py:19`) and the original RDH plan doc.
- **Retired:** `TP_COACH_AUTH_COOKIE` (current RDH name). The TS port renamed mid-build to disambiguate from a per-athlete cookie that never materialised. Stream 3 `auth-env-contract.md` and `recommended-actions.md` §3c both call this out.
- **Migration path:** P4 cutover ships a one-shot script that copies the value from `TP_COACH_AUTH_COOKIE` to `TP_AUTH_COOKIE` in Vercel env, then removes the old name. Production downtime: zero (both names are read during the transition window).
- **Why this rename, not the other:** the upstream Python fork is the older codebase, has more downstream consumers (Claude Code sessions everywhere), and is the source of truth in the wider ecosystem. RDH is one consumer; rename it, not them.

---

## §4 Tool Inventory and Tiering

**Canonical count: 63 tools** (revision 1). Verified via `grep -o "name=\"tp_[a-z_]*\"" src/tp_mcp/server.py | sort -u | wc -l` → 63, and `grep -oE "^\s+tp_[a-z_]+," src/tp_mcp/server.py | sort -u | wc -l` → 63 (imports match registrations). The previous "52" came from a stale Stream 3 matrix that pre-dated commits c10965b (notes API) and ca70dda (`tp_get_notes`). The §6 Parity Matrix in the master plan double-counted one row.

Tier rule:

- **MVP (P1)** — Race Day Hub `api/` currently imports this from `tp-client.ts` OR the cron sync calls it. Cutover from upstream Python cannot ship without these.
- **Should (P2)** — Useful but not critical-path. Coach Simon uses these in Claude Code sessions; absence is annoying, not blocking. Includes RDH features that have a planned consumer but not a current one.
- **Defer (P3)** — Write-heavy or niche. Ship after MVP is stable in production.

| #  | Tool                          | MVP (P1) | Should (P2) | Defer (P3) | Notes |
|----|-------------------------------|:--------:|:-----------:|:----------:|-------|
| 1  | `tp_auth_status`              | ✓        |             |            | Cutover safety — RDH and Claude Code both call this on session start |
| 2  | `tp_refresh_auth`             | ✓        |             |            | Cookie rotation path; replaces `/api/coach-rotate-tp-cookie` |
| 3  | `tp_list_athletes`            | ✓        |             |            | Coach roster — verified import: `api/cron/tp-coach-deep-sync-kickoff.ts:25`. `getUserData` is the internal helper feeding `listAthletes`; not a separate consumer |
| 4  | `tp_get_workouts`             | ✓        |             |            | Coach cron critical-path. Verified import: `api/cron/tp-coach-deep-sync-worker.ts:30-41` |
| 5  | `tp_get_fitness`              | ✓        |             |            | CTL/ATL/TSB — coach dashboard core. Verified import: worker line 30-41. Use `getFitnessRange` shape (Stream 3 §2a). Fix Stream 1 output-shape (`data` vs `daily_data`) at the boundary |
| 6  | `tp_get_peaks`                | ✓        |             |            | PR widget. Verified import: worker line 30-41 |
| 7  | `tp_get_athlete_settings`     | ✓        |             |            | Zones for the dashboard. Verified import: worker line 30-41 + kickoff line 25 |
| 8  | `tp_get_events`               | ✓        |             |            | Race calendar. Verified import: worker line 30-41. Adopt 730-day cap (Stream 3 breaking §1) |
| 9  | `tp_get_focus_event`          | ✓        |             |            | Coach dashboard "next race" widget. Verified import: worker line 30-41 |
| 10 | `tp_get_atp`                  | ✓        |             |            | Annual plan view. Verified import: worker line 30-41 |
| 11 | `tp_get_equipment`            | ✓        |             |            | Equipment chooser. Verified import: worker line 30-41 |
|    | **MVP subtotal: 11 tools** (revision 1: was 16) | | | | Cut 5 — see "MVP justification" below |
| 12 | `tp_get_profile`              |          | ✓           |            | Sync foundation but no current `api/` consumer (`getUserData` is internal to `tp-client.ts:279`; not imported elsewhere in `api/`). P1.5 once RDH "first connect" UX needs it. **Was MVP in draft — moved P2 in revision 1** |
| 13 | `tp_get_workout`              |          | ✓           |            | Detail endpoint. **No current RDH consumer** (workout-detail modal not yet built). P1.5 with the modal. **Was MVP in draft — moved P2 in revision 1** |
| 14 | `tp_get_workout_comments`     |          | ✓           |            | **No current RDH consumer.** Comments-thread UI is unbuilt. P1.5 / P2 with the journal feature. **Was MVP in draft — moved P2 in revision 1** |
| 15 | `tp_add_workout_comment`      |          | ✓           |            | **No current RDH consumer**, and the only write in the prior MVP. Coach reply flow is unbuilt. **Was MVP in draft — moved P2 in revision 1** (simplifies P1 to read-only) |
| 16 | `tp_get_weekly_summary`       |          | ✓           |            | **Not called from TP**; RDH computes `compliancePercent` locally in `src/utils/tp-coach-analytics.ts:71-307`. P2 only if a future feature needs the upstream-computed summary. **Was MVP in draft — moved P2 in revision 1** |
| 17 | `tp_get_next_event`           |          | ✓           |            | Convenience over `tp_get_events` — derive in TS or thin wrapper |
| 18 | `tp_get_notes`                |          | ✓           |            | Calendar notes list — Race Day Hub journal feature wants it (Stream 3 §1a) |
| 19 | `tp_get_note`                 |          | ✓           |            | Note detail (Stream 3 §1b) |
| 20 | `tp_get_note_comments`        |          | ✓           |            | Threaded note comments |
| 21 | `tp_get_metrics`              |          | ✓           |            | HRV/weight/sleep wellness panel (Stream 3 §1d) |
| 22 | `tp_get_nutrition`            |          | ✓           |            | Nutrition log read |
| 23 | `tp_get_workout_prs`          |          | ✓           |            | Per-workout PR list (vs aggregate peaks) |
| 24 | `tp_get_workout_types`        |          | ✓           |            | Static enum lookup; pure-fn TS port is trivial |
| 25 | `tp_validate_structure`       |          | ✓           |            | Pure-fn local validator (Stream 3 breaking §5) — port the logic, no HTTP |
| 26 | `tp_get_availability`         |          | ✓           |            | Coach availability read |
| 27 | `tp_get_pool_length_settings` |          | ✓           |            | Swim-specific setting; rare but cheap to expose |
|    | **P2 Should subtotal: 16 tools** (revision 1: was 12; +5 from MVP, -1 `tp_analyze_workout` moved to P3 — see R5 fix) | | | | |
| 29 | `tp_create_workout`           |          |             | ✓          | Write; coach planning workflow — Phase 3 of RDH coach roadmap |
| 30 | `tp_update_workout`           |          |             | ✓          | Write |
| 31 | `tp_delete_workout`           |          |             | ✓          | Write |
| 32 | `tp_copy_workout`             |          |             | ✓          | Write |
| 33 | `tp_reorder_workouts`         |          |             | ✓          | Write — re-implement with Stream 2 H1 fix (per-request lock or sequential loop) |
| 34 | `tp_pair_workout`             |          |             | ✓          | Write |
| 35 | `tp_unpair_workout`           |          |             | ✓          | Write |
| 36 | `tp_create_note`              |          |             | ✓          | Write |
| 37 | `tp_update_note`              |          |             | ✓          | Write — pick writable fields explicitly (Stream 1 medium finding) |
| 38 | `tp_delete_note`              |          |             | ✓          | Write |
| 39 | `tp_add_note_comment`         |          |             | ✓          | Write |
| 40 | `tp_create_event`             |          |             | ✓          | Write |
| 41 | `tp_update_event`             |          |             | ✓          | Write — pick writable fields explicitly |
| 42 | `tp_delete_event`             |          |             | ✓          | Write |
| 43 | `tp_create_availability`      |          |             | ✓          | Write |
| 44 | `tp_delete_availability`      |          |             | ✓          | Write |
| 45 | `tp_update_ftp`               |          |             | ✓          | Write |
| 46 | `tp_update_hr_zones`          |          |             | ✓          | Write |
| 47 | `tp_update_speed_zones`       |          |             | ✓          | Write |
| 48 | `tp_update_nutrition`         |          |             | ✓          | Write |
| 49 | `tp_log_metrics`              |          |             | ✓          | Write |
| 50 | `tp_create_equipment`         |          |             | ✓          | Write — niche |
| 51 | `tp_update_equipment`         |          |             | ✓          | Write — niche |
| 52 | `tp_delete_equipment`         |          |             | ✓          | Write — niche |
| 53 | `tp_upload_workout_file`      |          |             | ✓          | Binary write — Stream 2 M4 path-traversal hardening required before ship |
| 54 | `tp_download_workout_file`    |          |             | ✓          | Binary read — Stream 2 M1 body-leak fix + path-traversal hardening |
| 55 | `tp_delete_workout_file`      |          |             | ✓          | Write |
| 56 | `tp_get_libraries`            |          |             | ✓          | Library subsystem — niche |
| 57 | `tp_get_library_items`        |          |             | ✓          | Library |
| 58 | `tp_get_library_item`         |          |             | ✓          | Library |
| 59 | `tp_create_library`           |          |             | ✓          | Library write |
| 60 | `tp_delete_library`           |          |             | ✓          | Library write |
| 61 | `tp_create_library_item`      |          |             | ✓          | Library write |
| 62 | `tp_update_library_item`      |          |             | ✓          | Library write |
| 63 | `tp_schedule_library_workout` |          |             | ✓          | Library write |
| 64 | `tp_analyze_workout`          |          |             | ✓          | Cross-host call to `api.peakswaresb.com`. UI consumer (workout-detail "deep dive" modal) is **explicitly out of scope** (§10). Ship the tool only when the consuming UI lands. **Was P2 in draft — moved P3 in revision 1 (R5 fix)** |
|    | **P3 Defer subtotal: 36 tools** (revision 1: was 35; +1 `tp_analyze_workout`) | | | | |
|    | **Total: 11 + 16 + 36 = 63 tools** ✓ matches canonical count | | | | |

Note (revision 1): canonical count is 63. The earlier "52" was stale Stream 3 documentation pre-dating recent fork commits c10965b (notes API expansion) and ca70dda (`tp_get_notes` list endpoint). Numbers reconcile: 11 MVP + 16 P2 + 36 P3 = 63 = unique imports = unique registrations in `server.py`.

**MVP justification — what's the smallest set that frees Race Day Hub from upstream Python? (Revision 1 — tightened to current consumers only.)**

The MVP cut is **11 tools** (was 16). Evidence: `grep -rn "from '../_lib/tp-client'" "Race Day Hub/api/"` returns 3 production importers — `cron/tp-coach-deep-sync-worker.ts`, `cron/tp-coach-deep-sync-kickoff.ts`, `coach-rotate-tp-cookie.ts`. The union of their imports is exactly:

- Worker (line 30-41): `getATP, getAthleteSettings, getEquipment, getEvents, getFitness, getFocusEvent, getPeaks, getWorkouts` (8 reads).
- Kickoff (line 25): `getAthleteSettings, listAthletes` (1 new — `listAthletes`).
- Cookie rotate: `tp_refresh_auth` semantic (one writer of the cookie state).
- `tp_auth_status` is the session-start probe both RDH and Claude Code call before any other tool.

Total: 9 reads (`getATP, getAthleteSettings, getEquipment, getEvents, getFitness, getFocusEvent, getPeaks, getWorkouts, listAthletes`) + 2 auth (`tp_auth_status, tp_refresh_auth`) = **11 MVP tools**.

**5 tools cut from MVP (now P2)** with evidence:

| Tool | Reason for cut |
|------|----------------|
| `tp_get_profile` | `getUserData` only called internally inside `tp-client.ts:279` to derive athleteId for `listAthletes`. No standalone `api/` consumer. RDH "first connect" UX is unbuilt. |
| `tp_get_workout` | Zero `api/` consumers — workout-detail modal is unbuilt. |
| `tp_get_workout_comments` | Zero `api/` consumers — comments thread UI is unbuilt. |
| `tp_add_workout_comment` | Zero `api/` consumers. Coach reply flow is unbuilt. Removing it makes P1 read-only (no write-path test burden). |
| `tp_get_weekly_summary` | Not fetched from TP at all — `compliancePercent` is computed locally in `src/utils/tp-coach-analytics.ts:71-307` from sync data. Only referenced in a code comment in `src/services/tp-coach-roster-sync.ts:165` describing a future call pattern. |

These 5 are not displacement parity — they are RDH **new features** that happen to need TP data. They ship in P1.5 / P2 when (or if) the consuming UI lands. P1's effort estimate tightens accordingly (see §5 P1).

After MVP ships, RDH no longer reads from `tp-client.ts` directly for the 11 production-imported helpers. The upstream Python fork is no longer the source-of-truth for any tool RDH **today** calls. We can flip `TP_MCP_IMPL=jarasport` and run for 14 days. The rest of the tools (P2, P3) ship at our own pace without blocking cutover.

---

## §5 Phase Plan

### P0 — Foundations (effort: M — ~1.5–2 weeks)

**Scope:**
- Create GitHub repo `jara-r-k/jarasport-tp-mcp`. Confirm npm name `jarasport-tp-mcp` is available (no Python PyPI check needed; npm only).
- Repository scaffold: `src/` layout, `tsconfig.json` strict, `package.json` with pnpm, `tsup` build, `vitest` test runner, `biome` (or `eslint+prettier`) lint, `lefthook` pre-commit hooks.
- Two-package layout mirroring Python's `tp_core` / `tp_mcp` split: `src/tp-core/` (pure TP client; no MCP imports) and `src/tp-mcp/` (MCP adapter; Clerk middleware, transport, credential store). Import-boundary test enforces the rule.
- **Auth bridge:** Clerk JWT verifier (using `@clerk/backend`), JWKS cache (10 min, 24h stale-on-failure per ADR-0001), claim shape validation (issuer, azp, expiry, plan, tp_connected). Stub `EnvAuth` provider for stdio dev mode.
- **Credential store:** SQLite (better-sqlite3) for dev, Postgres-ready abstraction (`CredentialStore` interface) for prod. AES-256-GCM encryption at rest. Key derivation from `CREDENTIAL_STORE_KEY` env var (HKDF-SHA256; no PBKDF2 legacy bug like Stream 2 M3).
- **Base TP client:** lift `Race Day Hub/api/_lib/tp-client.ts`, `tp-auth.ts`, `tp-mappers.ts`, `tp-types.ts` into `src/tp-core/`. Generalise from single-coach to multi-user (cookie now resolved from `CredentialStore.get(user_id)`, not from `TP_COACH_AUTH_COOKIE`). Keep the promise-coalesced refresh and the Retry-After-aware 429 handler — they are wins over Python.
- **Server-side result sanitisation:** central `sanitiseToolResult(result)` in the MCP wrapper, recursively walking dicts/arrays and redacting any key matching `/^(access_token|refresh_token|cookie|authorization|token|secret|password|api_key)$/i`. Fixes Stream 2 M2 (per-tool sanitisation lives in only one Python file today).
- **Rate-limit lock done right:** per-user `AsyncLock` (using `async-mutex` or a tiny custom Promise-chain lock) wrapping the 150 ms throttle. Fixes Stream 2 H1 (Python's `_throttle` is not async-safe — concurrent `asyncio.gather` calls race). The TS implementation already promise-coalesces refresh; extend the same pattern to per-call throttling.
- **Path-traversal hardening (preparatory):** define `ALLOWED_UPLOAD_ROOT` and `ALLOWED_DOWNLOAD_ROOT` constants in `src/tp-core/paths.ts` with strict containment checks. No file tools ship until P3, but the helper lands now so the test harness is ready.
- **CI:** GitHub Actions matrix on Node 20 + Node 22. Lint, type-check, vitest, coverage gate, `npm audit --omit=dev` (urllib3/idna are Python-world — the TS equivalent is the supply-chain check), Trivy on the Docker image (we still containerise; Vercel needs it for the Pro plan's container deploys).
- **Pre-commit:** lefthook config running lint, type-check, vitest changed-files, secret-scan (`gitleaks`), conventional-commit-msg check.
- **Drop-through guard:** equivalent of Python plan's `scripts/check_test_coverage.py`. New `src/**/*.ts` requires a matching `tests/**/*.test.ts` or an inline `// pragma: no test-coverage  // reason: ...` escape hatch.
- **One-tool-per-file invariant:** lint rule (custom eslint/biome rule) refusing handler-export count > 1 per file under `src/tp-mcp/tools/`. Hard ban on the events.py-style mega-file pattern.

**Exit criteria:**
- Repo exists, CI green, branch protection on `main`.
- `pnpm dev` starts a stdio MCP server with one hello-world tool that requires a Clerk JWT (or `TP_MCP_AUTH_IMPL=env` in dev).
- `tp_auth_status` ships green: takes Clerk JWT in, returns cookie status from the credential store.
- Cookie round-trip works end-to-end: POST a cookie to `/credentials`, the encrypted blob lands in SQLite, retrieve via `CredentialStore.get(user_id)` returns the same value.
- The TS port's existing test corpus (from RDH `__tests__/integration/api-tp-*.test.ts`) is ported and green in the new repo.
- Handoff `HANDOFFS/P0-to-P1.md` written.

### P1 — MVP Tools (effort: M — ~1.5 weeks, was 2 — revision 1: 11 not 16 tools, read-only)

**Scope:** Ship the 11 MVP tools from §4. Each lands as `src/tp-mcp/tools/<tool_name>.ts` with one default export (the handler) plus contract test + integration test + unit test for any non-trivial helpers. **P1 is read-only** — no writes in MVP (R2 fix moved `tp_add_workout_comment` to P2).

Order of implementation (informed by RDH cron dependencies):

1. `tp_auth_status` (already shipped in P0 — counts here too).
2. `tp_refresh_auth` (cookie rotation — must work before per-user storage is interesting).
3. `tp_list_athletes` (coach roster foundation; reused by everything else; kickoff cron blocker).
4. `tp_get_athlete_settings` (zones; both kickoff and worker import it).
5. `tp_get_workouts` (calendar; worker critical path).
6. `tp_get_fitness`, `tp_get_peaks`, `tp_get_atp` (the analytics calls feeding the coach dashboard — all worker imports).
7. `tp_get_equipment` (equipment chooser — worker import).
8. `tp_get_events`, `tp_get_focus_event` (race calendar widgets — worker imports).

**Fixes applied during P1:**
- `tp_get_fitness` output-shape consolidation: emit `daily_data` in both empty and populated paths (Stream 1 high). Apply at the mapper.
- `tp_get_events` 730-day cap: validated client-side before the request (Stream 3 breaking §1). Single source of truth: `src/tp-core/validators/date-range.ts`.
- Pydantic `extra="ignore"` invariant becomes the TS default — `unknown` everywhere, narrowing with type guards. No equivalent runtime drift.
- `compliancePercent` is computed in RDH (`src/utils/tp-coach-analytics.ts`), not fetched. P1 does **not** ship `tp_get_weekly_summary` — moved to P2 per R2 fix.

**Exit criteria:**
- All 11 MVP tools pass contract + integration tests.
- A parity matrix is filled in: every MVP tool tested against a recorded TP cassette and behaves identically (modulo the documented Stream 1 fixes — empty `daily_data`, list invalidation moot here because we have no cache).
- Race Day Hub can replace its 3 `tp-client.ts` importers (`worker`, `kickoff`, cookie-rotate path) with MCP tool calls behind a feature flag (not yet flipped — that's P4).
- **Latency baseline collection (revision 1, R6 fix):** P1 records a per-tool baseline distribution (p50/p95/p99 over 100 calls) from the TS MCP itself, deployed to a Vercel preview. **No relative comparison to Python**; instead set absolute budgets per workflow (see §6 revised). The baseline is collected during P1 and used to define §6's burn-in alarms.
- Handoff `HANDOFFS/P1-to-P2.md` written.

### P2 — Should-have Tools (effort: M — ~2 weeks, was 1.5 — revision 1: 16 not 12 tools, includes write-path reintroduction)

**Scope:** Ship the 16 P2 tools from §4. Same per-tool discipline as P1. **P2 reintroduces the first write** (`tp_add_workout_comment`) — needs the full write-path test scaffolding (idempotency, error mapping, auth-on-write canary).

Order (revision 1 — 5 ex-MVP tools first, since each unlocks a planned RDH feature):

1. **Ex-MVP reads (R2 fix):** `tp_get_profile`, `tp_get_workout`, `tp_get_workout_comments`, `tp_get_weekly_summary`. Ship behind RDH feature flags; each is paired with the consuming UI shipping in RDH.
2. **First write:** `tp_add_workout_comment` (paired with coach reply UI in RDH). Establishes write-path test scaffolding for P3.
3. `tp_get_notes`, `tp_get_note`, `tp_get_note_comments` (Race Day Hub journal feature — Stream 3 §1a/b).
4. `tp_get_next_event` (thin wrapper over `tp_get_events`).
5. `tp_get_metrics`, `tp_get_nutrition` (wellness panel — Stream 3 §1d).
6. `tp_get_workout_prs`, `tp_get_workout_types` (PR widget + sport enum).
7. `tp_validate_structure` (pure-fn TS port of `_validation.py` interval validator — no HTTP).
8. `tp_get_availability`, `tp_get_pool_length_settings` (rare reads).

`tp_analyze_workout` is **NOT in P2** (revision 1, R5 fix) — moved to P3 because its only consumer (workout-detail "deep dive" modal) is explicitly out of scope (§10).

**Fixes applied:**
- `tp_validate_structure`: port the Python `_validation.py` logic 1:1. Pure function, deterministic. No HTTP. Zero auth risk.
- `tp_add_workout_comment`: write-path canary added to the secret-scan test suite (planted secret in user comment text, asserted scrubbed from response echo).
- `tp_get_weekly_summary`: ships only as a parity-completeness tool. RDH continues to compute `compliancePercent` locally; we test the upstream summary against the local computation as a cross-check.

**Exit criteria:**
- All 27 tools (P1 + P2) green on contract + integration.
- Write-path test scaffolding proven against `tp_add_workout_comment` (idempotency, error mapping, retry behaviour on 5xx).
- Handoff `HANDOFFS/P2-to-P3.md` written.

### P3 — Defer / Writes, File I/O, Analyse (effort: L — ~3 weeks)

**Scope:** Ship the 36 P3 tools from §4. Writes have higher per-tool overhead (idempotency, optimistic concurrency, error mapping). File I/O tools need the Stream 2 hardening. `tp_analyze_workout` lands here (R5 fix) gated by its consuming UI.

Sub-phase order (revision 1 — counts corrected per REC1):

**P3a — Note + event + availability writes (9 tools):**
- `tp_create_note`, `tp_update_note`, `tp_delete_note`, `tp_add_note_comment`, `tp_create_event`, `tp_update_event`, `tp_delete_event`, `tp_create_availability`, `tp_delete_availability`.
- Apply Stream 1 medium-finding fix: `tp_update_note` and `tp_update_event` pick writable fields explicitly. No `dict(get_response.data or {})` echo pattern.

**P3b — Workout writes (7 tools):**
- `tp_create_workout`, `tp_update_workout`, `tp_delete_workout`, `tp_copy_workout`, `tp_reorder_workouts`, `tp_pair_workout`, `tp_unpair_workout`.
- `tp_reorder_workouts` ships with sequential loop OR per-call lock — Stream 2 H1 fix. Test: invoke with 20 workouts, assert TP receives ≤ 1 request per 150 ms.

**P3c — Settings writes (5 tools):**
- `tp_update_ftp`, `tp_update_hr_zones`, `tp_update_speed_zones`, `tp_update_nutrition`, `tp_log_metrics`.
- Straightforward. Pydantic-equivalent input validation on all five via Zod schemas.

**P3d — File I/O (3 tools):**
- `tp_upload_workout_file`, `tp_download_workout_file`, `tp_delete_workout_file`.
- **Mandatory before ship:** Stream 2 M4 path-traversal hardening (allow-list directory with strict containment). Stream 2 M1 fix on error-body propagation (no `response.text` in `RawResponse.message`).

**P3e — Equipment writes (3 tools):**
- `tp_create_equipment`, `tp_update_equipment`, `tp_delete_equipment`. Niche; cheap.

**P3f — Library (8 tools):**
- `tp_get_libraries`, `tp_get_library_items`, `tp_get_library_item`, `tp_create_library`, `tp_delete_library`, `tp_create_library_item`, `tp_update_library_item`, `tp_schedule_library_workout`. Niche subsystem; bundled together.

**P3g — Analyse (1 tool, gated by UI — R5 fix):**
- `tp_analyze_workout` (cross-host `api.peakswaresb.com` call; lift the Origin/Referer headers from the Python implementation; document the dependency on Peaksware's CORS policy as a Stream 1 low-confidence risk).
- **Gate:** ship only when the RDH "deep dive" modal is in flight. Otherwise carry as a P3 backlog item.
- `tp_analyze_workout`: explicit `TPClient.getBearerToken()` public method instead of reaching into private state (Stream 1 high — Python `analyze.py` reaches into `client._token_cache.access_token`).

**Subtotals:** 9 + 7 + 5 + 3 + 3 + 8 + 1 = **36 P3 tools** ✓.

**Exit criteria:**
- All **63 tools** green (revision 1 — canonical count, no hedging).
- Parity matrix fully ticked.
- `tp_reorder_workouts` proven safe under load (200 workouts in one call, no 429s).
- File-tool security review: explicit sign-off that path-traversal is contained.
- `tp_analyze_workout`: ship only when consuming UI is committed in RDH.
- Handoff `HANDOFFS/P3-to-P4.md` written.

### P4 — Cutover (effort: S — ~1 week, but spans 14 days of monitoring)

**Scope:**
- Deploy `jarasport-tp-mcp` to Vercel production (same project as RDH, separate function family `/api/mcp/*`).
- Migrate Coach Simon's existing cookie from RDH's Wix `TPCoachAuth` singleton to the new credential store, keyed by his Clerk `user_id`.
- Race Day Hub feature flag: `VITE_TP_MCP_IMPL=jarasport`. Default off in week 1, then flip to on in week 2 with rollback prepared.
- Rollback procedure: flip `VITE_TP_MCP_IMPL=legacy` env var, redeploy RDH (under 5 minutes). The legacy `tp-client.ts` remains in RDH code for the 14-day burn-in.
- Env-var rename: `TP_COACH_AUTH_COOKIE` → `TP_AUTH_COOKIE` for the dev/stdio fallback. (Production no longer uses the env-var path at all.)
- Archive the upstream Python fork: `jara-r-k/trainingpeaks-mcp` gets a deprecation README pointing to `jara-r-k/jarasport-tp-mcp` and is marked read-only. The fork lives forever as a reference; we stop pulling from upstream.
- Cancel the deferred Python master+P0 plans: append a final session-ledger entry pointing here, mark phases as `SUPERSEDED`.

**Exit criteria:**
- 14 days of green health on the deployed MCP. Error rate < 0.5%. p95 latency under 800 ms.
- Race Day Hub running on `jarasport-tp-mcp` exclusively. The legacy `Race Day Hub/api/_lib/tp-client.ts` is deleted in a final cleanup PR.
- Old Python fork archived. Deprecation README in place.
- Master plan §6 Parity Matrix fully ticked (or moved here and ticked).
- This roadmap's `status:` field moves from `DRAFT` to `DONE`.

---

## §6 Cutover Criteria (Measurable)

**Two-phase gating (revision 1, R6 fix):** baseline collection in P1/P2, then bound thresholds in P4. The previous "≤110% of Python" gate was unfalsifiable (Python fork is not deployed; local-to-local has no production analogue). Replaced with per-workflow absolute budgets tied to RDH SLOs that Coach Simon actually feels.

### Baseline phase (P1 + P2 — collect, don't bind)

| Signal | Collection method | Outcome |
|--------|-------------------|---------|
| Per-tool latency distribution | 100 calls per MVP tool from a deployed Vercel preview to the real TP API (Coach Simon's account, off-hours). Record p50/p95/p99 + cold-vs-warm split | Frozen baseline JSON file committed at end of P1: `docs/superpowers/baselines/p1-latency-baseline.json`. Used to define P4 burn-in alarms |
| Per-workflow latency | 50 invocations of the cron worker's per-athlete fanout flow (one full `claimNext → fetch → markDone` cycle) | Frozen: `docs/superpowers/baselines/p1-workflow-baseline.json` |
| Cold-start frequency | Count of cold starts per 100 invocations from Vercel function logs over 24h | Informs the warming-cron decision (R-102) |

### Binding phase (P4 cutover — gates)

| Criterion | Gate | Measurement |
|-----------|------|-------------|
| **Functional parity** | Every MVP tool (11 in §4 — revision 1) passes contract test AND returns equivalent shape to the Python fork on a recorded TP cassette | Run `pnpm test:contract` in CI. Diff JSON output against frozen Python golden file. Tolerated divergence: documented Stream 1 fixes (empty `daily_data`) |
| **Per-workflow latency — coach roster aggregate** | RDH `coachAthletesAggregate` first-paint p95 ≤ baseline + 200 ms over a 14-day window | Measured at the RDH page (the only surface Coach Simon experiences) — not at the tool level. Compared to P1 baseline JSON |
| **Per-workflow latency — per-athlete deep sync** | Worker `claimNext → tool → markDone` median ≤ baseline × 1.25 over 14 days | Same harness used in baseline; gate is workflow-level, not per-tool |
| **Per-tool latency (smoke check, non-binding)** | Median tool latency reported daily; alert (not block) if any tool's p95 drifts > baseline × 2.0 for 3 consecutive days | Vercel function logs + per-tool tag. **This is a smoke check, not a cutover gate.** Replaces the old "110%/150% of Python" gates |
| **Error rate** | < 0.5% 5xx + auth-rejection rate over a 14-day window in production | Vercel function logs; aggregate via the structured-log fields specified in §8.5 (revision 1) |
| **Token leak surface** | Zero. `pnpm test:secret-scan` runs a planted-secret canary through every tool and asserts the secret never appears in the response. **Test design:** plant a deterministic 32-byte secret in mocked TP responses across all 11 MVP tools + all 5 P2 ex-MVP tools; assert response JSON does not contain the secret; assert log lines do not contain the secret | New test suite added during P0; runs in CI on every PR |
| **Rate-limit safety** | `tp_reorder_workouts` with 20 workouts produces ≤ 1 TP API call per 150 ms (no concurrent burst) | Mock TP, count calls + measure intervals. Asserted in P3b test |
| **Rollback** | Single env-var change in RDH (`VITE_TP_MCP_IMPL=legacy`) returns to the previous implementation within 5 minutes | Practised once during P4 day-1 as a deliberate dry-run |
| **Credential isolation** | User A cannot retrieve or use User B's TP cookie via any tool. **Test design (REC3 fix):** spin up 2 user contexts (User A, User B); issue 50 interleaved tool calls; assert each user's tool result references only their own `athleteId`; assert credential store row lookup for User A's user_id returns User A's cookie only (direct DB inspection); assert no module-scope `Map` retains data between requests (in-process telemetry counter) | Multi-user integration test added during P0; asserted in CI |
| **CVE drift** | `pnpm audit --omit=dev` clean on a moderate threshold; renovate-bot keeping deps current | CI gate + weekly bot run |

Note on baselines: per-tool latency is non-binding because (a) sample size of 100 per tool gives a wide p95 confidence interval, (b) per-tool budgets do not match the per-workflow latency that Coach Simon experiences, (c) GC pauses and TP backend hiccups move single-tool p95 by 30%+ without indicating a regression. The workflow-level budgets above tie to RDH UX SLOs and are the actual cutover gates.

---

## §7 Risk Register

| ID    | Risk | Impact | Likelihood | Mitigation | Status |
|-------|------|:------:|:----------:|------------|--------|
| R-101 | TP cookie expires on first MCP run (cold start, no rotation pipeline yet) | High | Medium | Stdio dev mode keeps the env-var path; manual rotation runbook from RDH carries over (Race Day Hub/docs/runbooks/tp-cookie-rotation.md). P0 ships `tp_refresh_auth` as the rotation entry point | Open |
| R-102 | Vercel cold-start latency dominates p95 budget | Medium | High | Pre-warm via cron ping; consider Vercel "Standard" plan for dedicated capacity if needed. Default to Node runtime (not edge) to avoid the 25s start-of-response constraint | Open |
| R-103 | Clerk JWT verification cost per call adds 50–100 ms per request | Medium | Medium | JWKS cached 10 min in-process; per-`user_id` JWT cache for 60 s (matches Clerk token TTL). ADR-0001 §"Consequences/Negative" already covered | Open |
| R-104 | Dependency CVE drift in TS dep tree (analogous to urllib3/idna in Python — Stream 2 H2) | Medium | Medium | Renovate-bot on weekly cadence; `pnpm audit` in CI on moderate threshold; pinned exact versions with semver-compatible ranges | Open |
| R-105 | Scope creep beyond MVP. Coach Simon asks for "just one more tool" mid-P1 | High | High | This roadmap. §4 tier list is the contract. New tools go into P2/P3 backlog, never injected into the current phase | Open |
| R-106 | RDH parallel changes during the rebuild create a moving target | Medium | Medium | Lock the RDH `tp-client.ts` interface at P0 start. Any RDH change that touches the TP surface goes via the new MCP (or waits) | Open |
| R-107 | TP API changes their internal endpoints mid-build | High | Low | Synthetic probe daily against `/users/v3/token`. Alert on 404 on any known endpoint. Carries over from Python R-001 | Open |
| R-108 | Credential-store encryption key lost (Stream 2 M3 territory) | High | Low | KMS-backed key in production (Vercel project secret); documented rotation; encrypted backup. Carries over from Python R-005 | Open |
| R-109 | One-tool-per-file invariant breached in TS (events.py-style mega-file pattern recurring) | Medium | Medium | Custom lint rule. CI blocks on > 1 handler export per file under `src/tp-mcp/tools/`. Reviewers can override only via `// lint: tools-per-file` comment with a written justification | Open |
| R-110 | Path-traversal regression in file I/O tools (Stream 2 M4) | High | Low | `ALLOWED_UPLOAD_ROOT` / `ALLOWED_DOWNLOAD_ROOT` containment checks land in P0, not P3d. Tests assert symlink-escape + `..` escape both reject | Open |
| R-111 | Result-sanitisation invariant drift (Stream 2 M2 — Python has per-tool sanitisation that lives in only one file) | High | Medium | Server-side `sanitiseToolResult` wraps every handler in P0. No per-tool exemption. Test: planted-secret canary in every tool's mocked TP response, assert never echoed | Open |
| R-112 | Env-var rename (`TP_COACH_AUTH_COOKIE` → `TP_AUTH_COOKIE`) breaks RDH cron during the transition | Medium | Low | Both names supported during P4 week 1. Old name removed only after MCP cutover stable for 7 days. Stream 3 §3c outlines the coordinated deploy | Open |
| R-113 | Session continuity (same as Python R-008) — work in one session invisible to next | High | Medium | This roadmap. Reuse the master plan's Session Ledger pattern (§11 of Python master). Mandatory exit-row per session | Open |
| R-114 | Wix CMS removal mid-rebuild: RDH cookie storage is currently in Wix `TPCoachAuth`. If RDH retires Wix before P0 ships, the cookie source disappears | High | Medium | P0 reads the cookie from `TP_COACH_AUTH_COOKIE` env var (the documented Wix-singleton fallback) as the initial seed. The CMS singleton can be retired the moment P4 ships. **Likelihood raised to Medium in revision 1** — 6-10 week rebuild window overlaps known Wix retirement target | Open |
| R-115 | **Credential store backup loss** (Q-102 unresolved). If the prod backend chosen for the credential store loses data (Vercel volume reset, KV eviction, Postgres backup gap), every user must re-paste their TP cookie | High | Low | Daily encrypted dump of credential store rows to a separate S3/R2 bucket. Restore runbook tested in P4 dry-run. Worst-case manual re-paste flow documented (Coach Simon already does this monthly) | **Added rev 1 (R7)** |
| R-116 | **Clerk JWKS endpoint unreachable for >24h.** ADR-0001 says 24h stale-serve; after that, MCP rejects all calls with `unauthorized.bad_signature` and RDH breaks | High | Low | Degraded read-only mode: serve cached JWKS forever past 24h with a loud INFO alert, do NOT block on JWKS staleness alone. Restore behaviour by replacing the JWKS cache or rolling Clerk keys (manual step). Trade: weakens revocation, but Coach Simon outage is worse | **Added rev 1 (R7)** |
| R-117 | **TP rotates cookie format.** R-107 covers endpoint changes generically. A cookie-format change is separate: `auth/storage.py` parser would need new logic. Likely manifests as 100% auth failure post-rotation | High | Low | Daily synthetic probe (Q-108) extended to check cookie-parsing path (`tp_auth_status` against the real account). Alert pattern matches "all users fail in N minutes" | **Added rev 1 (R7)** |
| R-118 | **Second coach onboards mid-build.** Roadmap is "Coach Simon first" (§10). If a second Jarasport coach onboards during P1-P3, the credential-store schema and the multi-user test corpus must already handle them | Medium | Medium | The schema is multi-tenant from P0 (keyed by Clerk `user_id`). The work is RDH-side onboarding UX. Acceptable: second coach onboards via manual cookie paste through a temporary admin tool while RDH onboarding lands in P5-equivalent | **Added rev 1 (R7)** |

Top 3 risks (impact × likelihood, revision 1): **R-105 (scope creep)**, **R-102 (cold-start latency)**, **R-114 (Wix retirement window — Medium likelihood)**. R-111 (sanitisation drift) is High impact + Medium likelihood but mitigated by the server-side wrapper landing in P0; remains under watch.

---

## §8 Cross-references

### Fixes inherited from Stream 1 (code quality + deslop)

- **events.py mega-file split** — does not arise: TS lint rule enforces one handler per file from P0. Note tools (`tp_get_notes`, `tp_get_note`, `tp_update_note`, etc.) all get their own files; calendar events, availability, and notes are separate folders.
- **Cache list-invalidation bug** — does not arise: no module-scope cache (§3 A5). If we later add one, the design is prefix-match invalidation per Stream 1's recommended remediation.
- **`tp_get_fitness` output-shape inconsistency** (`data` vs `daily_data`) — fixed at the mapper in P1. Both empty and populated paths emit `daily_data`. Tests assert the shape.
- **Pydantic `extra="ignore"` invariant** — does not arise: TS uses `unknown` + type guards. No equivalent runtime default to drift.
- **Reaching into private `client._token_cache.access_token`** — fixed: expose `TPClient.getBearerToken(): Promise<string>` as a public method. `tp_analyze_workout` (P2) calls it explicitly.
- **`dict(get_response.data or {})` echo on `tp_update_note` / `tp_update_event`** — fixed: writable fields enumerated explicitly per tool in P3a.
- **In-function `from datetime import date` imports** — does not arise: TS module imports.

### Fixes inherited from Stream 2 (security)

- **H1 — `_throttle` async-safety race** — fixed: per-user `AsyncLock` wrapping the throttle, applied to every TPClient method in P0. Test asserts `tp_reorder_workouts` ≤ 1 call / 150 ms.
- **H2 — urllib3 + idna CVEs** — does not arise in TS: Node's native fetch and undici don't ship those dependencies. We document the divergence in §3 A1 (Why TS).
- **M1 — `response.text` leaked into `RawResponse.message`** — fixed: file-tool error path emits `HTTP {status} (body suppressed)` only. P3d (file I/O) carries the fix.
- **M2 — server-side result sanitisation** — fixed in P0: central `sanitiseToolResult(result)` wraps every handler. No per-tool sanitisation needed (or trusted).
- **M3 — encrypted-store legacy-key migration silence** — does not arise: TS credential store ships HKDF-SHA256 from day one, no legacy code path. Log INFO on every cookie write so users see when their cookie was last rotated.
- **M4 — path traversal via `tp_upload_workout_file` / `tp_download_workout_file`** — fixed in P0 (helpers land) and P3d (tools use them). `ALLOWED_UPLOAD_ROOT` / `ALLOWED_DOWNLOAD_ROOT` containment checks. Test: symlink escape rejects, `..` escape rejects.
- **L1 — prompt-injection echo from workout descriptions** — partially mitigated: wrap user-text fields in `<tp-untrusted>...</tp-untrusted>` delimiters before serialisation. P1 mapper change.
- **L2–L4 — documentation-only items** — covered in the README and runbooks.

### TS port deltas from Stream 3

- **Env-var rename** (`auth-env-contract.md` + `recommended-actions.md` §3c): canonical is `TP_AUTH_COOKIE`. RDH renames in P4. Justification in §3 A7.
- **`tp_get_events` 730-day cap** (`breaking-changes.md` §1): adopted in P1. Documented as a deliberate divergence from upstream (which still has 90 days). Constants centralised in `src/tp-core/validators/date-range.ts`.
- **Notes API** (`breaking-changes.md` §2): all 7 notes-related tools in P2 (reads — `tp_get_notes`, `tp_get_note`, `tp_get_note_comments`) and P3a (writes — `tp_create_note`, `tp_update_note`, `tp_delete_note`, `tp_add_note_comment`).
- **Module-scope cache rejected** (`breaking-changes.md` §3): see §3 A5. Per-request cache only.
- **`getFitness` signature change** (`breaking-changes.md` §4): TS implementation uses the Python-shape POST (`{atlConstant, ctlConstant, …}` body with date-range path). RDH callers update to the new signature during P1.
- **`tp_validate_structure` pure-fn port** (`breaking-changes.md` §5): trivial; P2.
- **`athlete_override` ContextVar** (`breaking-changes.md` §6): not ported. TS uses explicit-pass `athleteId` per call.
- **Tier 0 hygiene fixes** (`recommended-actions.md` 0a-0c): adopted from P0 — explicit `AbortSignal.timeout(30_000)`, dedicated `TPAuthInvalidError` for 403, `TPNetworkError` wrapping fetch failures.

### Stream 1 deltas not previously cross-referenced (revision 1, REC7)

- **§3 slop deletions (~88 lines, items 1-12):** not ported forward. The TS rebuild starts from the existing TS port + the Python *behaviour* — we do not copy Python comments, docstrings, or stale TODOs. The slop disappears by construction.
- **§2 `server.py` 1623-line file (LOW architectural finding):** addressed structurally by A1 (one-tool-per-file). Custom lint rule in P0 makes the events.py pattern impossible.

---

## §8.5 Observability minimum signals (revision 1, REC5)

§10 descopes the *stack* (Prometheus/OTel) but the §6 cutover gates require concrete signals. The MCP emits the following structured log fields on every tool invocation, queryable in Vercel function logs:

| Field | Type | Purpose |
|-------|------|---------|
| `tool_name` | string | Per-tool aggregation (smoke check + alert routing) |
| `user_id_hash` | string (SHA-256 first 8 chars) | Per-user aggregation without leaking PII |
| `status` | `success` \| `tp_error` \| `auth_error` \| `validation_error` \| `internal_error` | Error-rate gate, P4 burn-in |
| `duration_ms` | number | p50/p95/p99 buckets per `tool_name` |
| `tp_status_code` | number \| null | Distinguish TP-side from MCP-side failures |
| `cold_start` | boolean | Cold-vs-warm latency split (R-102) |
| `cache_hit_jwks` | boolean | JWKS staleness telemetry (R-116) |
| `request_id` | string (uuid) | Correlation across log lines for one tool call |

**Verification before P4:** Vercel built-in dashboard can render `status` rate-of-change per `tool_name`. If it cannot, add a minimal alarm webhook to Slack/email — this is a 2-hour ticket, not a stack rebuild.

**Verification before P0 close:** every handler wraps the tool body in a `withLogging(tool_name, handler)` decorator. CI lint rule rejects un-wrapped handlers.

---

## §8.6 On-call, error budget, runbook (revision 1, REC6)

- **Error budget:** 99.5% availability = ~3.6 hours/month allowed downtime. The 14-day P4 burn-in must show ≤ 0.5% error rate, which leaves ~1 hour/month error budget once stable. If exceeded, P4 cutover is delayed; if exceeded post-cutover, RDH rolls back via the env-var switch.
- **On-call rotation:** Coach Simon = Jara (solo). Alerts via the existing Vercel + email path RDH uses for the coach cron. No dedicated paging tier in this rebuild.
- **Runbook stubs (must exist before P4 ships):**
  1. **TP cookie expiry** (`docs/runbooks/tp-cookie-expiry.md`): user re-pastes cookie via RDH UI → MCP credential store updates → resume.
  2. **Clerk JWKS unreachable** (`docs/runbooks/jwks-outage.md`): R-116 mitigation steps — extend stale-serve, monitor for resolution, manual key roll if persistent.
  3. **Credential store row corrupted** (`docs/runbooks/credential-store-recovery.md`): R-115 mitigation — restore from daily encrypted dump or manual cookie re-paste.

---

## §9 Open Questions

| ID    | Question | Owner | By when |
|-------|----------|-------|---------|
| Q-101 | Vercel plan (Hobby vs Pro) — does Pro's `maxDuration: 800` justify the cost for our use case, or is Hobby's 300s enough? | Owner | **P0 kick-off — BLOCKER** |
| Q-102 | Credential-store prod backend: SQLite-on-Vercel-volume (small, simple) vs Vercel Postgres / Neon (multi-region) vs Vercel KV (Redis-like)? **Revision 1 (REC4):** elevated to P0 kick-off blocker. Interface depends on transactional semantics (per-row write lock for token refresh — see §3 A5). Default recommendation: **Vercel Postgres** for prod (transactional, scales beyond a single Vercel volume), `better-sqlite3` for dev | Owner | **P0 kick-off — BLOCKER (was P0 week 2)** |
| Q-103 | Multi-tenant pricing model: free for Coach Simon's athletes; do we monetise other coaches at all in scope of this rebuild, or is that strictly out-of-scope (deferred to a later product)? | Product | Before P4 cutover |
| Q-104 | MCP framework: stay with `@modelcontextprotocol/sdk` (official) or migrate to FastMCP-TS in P2 if the official SDK's ergonomics frustrate us? **Revision 1 (REC2):** decision moved to P0 before scaffolding. Default recommendation: official SDK + a thin internal `defineTool({ name, schema, handler })` wrapper that mimics FastMCP-TS ergonomics (Zod-derived JSON Schema). Avoids re-litigating at P1 | P0 design | **P0 kick-off (was end of P1)** |
| Q-105 | Renovate-bot configuration: groups (production minor+patch) vs everything-pinned-exact. **Default:** group dev-deps + minor/patch, hold majors for human review | P0 session | P0 task week 2 |
| Q-106 | ~~npm name: `jarasport-tp-mcp` available?~~ **RESOLVED (revision 1):** publish under `@jarasport/tp-mcp` private scope. Sidesteps name-collision risk entirely; aligns with Q-110 default (private until P3) | — | — |
| Q-107 | Local stdio fallback `TP_MCP_AUTH_IMPL=env`: should it work for any `user_id`, or only one (Coach Simon)? **Default:** accept any `user_id` matching a row in the credential store; the env-var path bypasses Clerk but does not invent a `user_id`. Single-user simplification rejected — would block other Jarasport coaches from local development | P0 session | P0 design |
| Q-108 | TP API surface drift detection: should we run a daily synthetic probe in CI/cron that calls every known endpoint and alerts on 404? **Default:** yes, daily probe on Coach Simon's account against the 11 MVP tools after P1 ships; extend to 27 (MVP + P2) after P2 | P2 session | Before P2 close |
| Q-109 | Do we publish `tp-core` as a separate npm package (so the RDH cron and the MCP server share it), or vendor it into both? (Mirrors Python Q-003) | P5-equivalent decision (post-P3) | After MVP stable |
| Q-110 | Open-source the new repo from day 1, or keep private until P3? **Default (revision 1, REC8):** **private until P3 cutover stable.** Aligns with Q-106 `@jarasport/tp-mcp` private scope. Make public when the upstream Python fork is archived and the deprecation notice is live, so anyone migrating from upstream lands on a stable codebase | Owner | Confirmed default — change requires explicit decision |

### Deferred recommendations (rev 1)

- **REC1**: applied (P3a count corrected to 9, subtotals reconciled in §4 and §5 P3).
- **REC2**: applied (Q-104 default + wrapper recommendation above).
- **REC3**: applied (multi-user isolation test design in §6).
- **REC4**: applied (Q-102 elevated to P0 kick-off blocker).
- **REC5**: applied (§8.5 observability minimum signals).
- **REC6**: applied (§8.6 on-call + runbook).
- **REC7**: applied (Stream 1 deltas added to §8).
- **REC8**: applied (Q-110 default + Q-106 resolved).

### Open questions surfaced by R7 follow-ups (rev 1)

- **Cassette scrubbing for parity tests** (raised in critic §9): how do we strip Coach Simon's PII from VCR/msw cassettes before committing? Default: cassette-recording session writes to a gitignored fixtures dir; a `pnpm test:scrub-cassettes` step replaces all `athleteId`, cookie, and email fields with frozen test values before committing.
- **Promise-coalesced refresh generalisation** (raised in critic §9): the TS port's module-scope `refreshPromise` becomes per-user `Map<user_id, Promise<TPAccessToken>>` per §3 A5. Add explicit P0 sub-task: "generalise promise coalescing to per-user keying".
- **`/api/mcp/*` cross-pollination risk** (raised in critic §9): MCP and RDH share a Vercel project. Hard convention: MCP code never imports from RDH; RDH never imports from MCP (only HTTP calls). Enforced via lint rule + import-boundary test.

Top 3 open questions (revision 1): **Q-101 (Vercel plan)**, **Q-102 (credential-store backend — elevated)**, **Q-104 (FastMCP-TS vs official + wrapper — elevated)**.

---

## §10 Out of Scope (Explicit)

These items are not part of this rebuild. They may become future work but do not get smuggled into this roadmap's phases.

- **Replacing `browser-cookie3`-style cookie capture.** Manual cookie ingestion via `POST /credentials` is fine for v1. Browser-extraction automation is a separate UX problem. RDH owns the "Connect TrainingPeaks" UI; the MCP just receives the cookie.
- **Multi-tenant SaaS for coaches outside Jarasport.** Coach Simon is the first user. Other Jarasport coaches plug in via the same Clerk org. A future B2B SaaS launch for non-Jarasport coaches is a separate product decision (covered by Python plan Q-005, still unresolved, deliberately deferred).
- **Mobile client.** RDH is web. The MCP doesn't care about clients — but no mobile work in this roadmap.
- **AI workout generation, training-plan synthesis, athlete coaching automation.** These are RDH features that *consume* the MCP. The MCP is the data layer. Feature work happens on the RDH side.
- **Replacing the upstream Python fork for non-RDH consumers.** The fork is open-source, the Claude Desktop installation path is documented. Other people use it. We are not migrating them — we ship our own thing under our own name (`jarasport-tp-mcp`), and the upstream fork's archive is purely a deprecation note for *our* usage.
- **Backporting TS fixes into the Python fork.** Once `jara-r-k/trainingpeaks-mcp` is archived (P4), we stop. The fork lives forever as a reference but doesn't receive bug fixes. The CVE fixes (urllib3/idna) and the rate-limit lock can be cherry-picked by anyone who needs them — we link to the relevant Stream 1+2 findings in the deprecation README.
- **Sync-engine work** (e.g. RDH's `tp-sync-queue.ts` job orchestration). That stays in RDH. The MCP exposes the TP surface; RDH owns the orchestration of when to sync and what to do with the data.
- **`tp_analyze_workout` deep-dive UI in RDH.** The tool itself is **deferred to P3g (revision 1, R5 fix)** — it ships only when the consuming UI is committed in RDH. Without the UI, shipping the tool is pure inventory.
- **Observability stack rebuild (Prometheus/OTel).** Vercel's built-in observability + the structured-log fields specified in §8.5 (revision 1) are the baseline. No new stack here.
- **Backwards compatibility with the upstream Python fork's CLI** (`tp-mcp auth --from-browser chrome`). The new TS MCP has no equivalent. The cookie comes in via `POST /credentials` (RDH owns the "Connect TrainingPeaks" UI) or via `TP_AUTH_COOKIE` env (stdio dev mode). **Added rev 1.**
- **OAuth flow with TrainingPeaks.** TP has no public OAuth. The MCP is cookie-based forever. If TP ever ships OAuth, this is a future migration. **Added rev 1.**
- **Migration of the historical RDH Wix `TPCoachAuth` singleton to anything other than the new credential store.** §5 P4 mentions the migration. **Post-cutover policy (rev 1):** the Wix singleton row is left orphaned (no consumers) until Wix retirement (R-114) removes it incidentally. We do not actively delete it — read-only audit value remains. **Added rev 1.**

---

## Revision log

| Revision | Date | Trigger | Items applied | Items deferred |
|----------|------|---------|---------------|----------------|
| 1 | 2026-05-27 | Critic review (`.omc/critic-roadmap-review.md`) — verdict APPROVED-WITH-CHANGES | **Required (R1-R7):** R1 (A4 edge/Node justification rewritten with evidence), R2 (MVP cut from 16 → 11 tools, 5 moved to P2 with evidence), R3 (canonical count resolved to 63 across §4/§5 P3/§6; 52 figure removed), R4 (A5 cache scope disambiguated: response-cache per-request, JWKS module-scope, TP access-token in credential-store row with per-row lock + per-lambda coalescing), R5 (`tp_analyze_workout` moved P2 → P3g, gated by consuming UI), R6 (latency gates split into baseline collection in P1/P2 then workflow budgets in P4; per-tool gates downgraded to non-binding smoke), R7 (added R-115 credential-store loss, R-116 JWKS extended outage, R-117 TP cookie format change, R-118 second coach onboard mid-build; raised R-114 likelihood to Medium). **Recommended (REC1-REC8):** REC1 (P3a sub-phase count corrected to 9; new subtotals reconciled), REC2 (Q-104 default = official SDK + Zod wrapper, decision moved to P0), REC3 (multi-user isolation test design specified in §6), REC4 (Q-102 elevated to P0 kick-off blocker; default = Vercel Postgres prod, better-sqlite3 dev), REC5 (§8.5 observability minimum signals added), REC6 (§8.6 on-call + runbook), REC7 (Stream 1 slop deletions + 1623-line file findings added to §8), REC8 (Q-110 default = private until P3; Q-106 resolved as `@jarasport/tp-mcp` private scope). **Other:** §10 expanded with 3 missing out-of-scope items (CLI parity, OAuth, Wix row disposition). | **None deferred** — all R/REC items addressed inline. Three open-question additions from critic §9 (cassette scrubbing, promise-coalescing generalisation, `/api/mcp/*` cross-pollination) added to §9 as new entries, not deferred. |

---

_End of replacement roadmap (revision 1)._
