---
title: jarasport-tp-mcp-master
plan: jarasport-tp-mcp master integration
status: in-progress
owner: jara-r-k
date: 2026-04-25
project: trainingpeaks-mcp
phases: P0-P7
actionable: auto
next_action: Start P0 Task 1 (PyPI name check + repo creation)
---

# jarasport-tp-mcp — Master Integration Plan

> **For agentic workers:** This is the **program-level coordination document**, not a TDD plan. It is the single source of truth for phase status, cross-session handoffs, and "nothing falls through cracks" tracking. Every session **must** read this first and update it on exit. Per-phase TDD plans live alongside this file as `2026-04-25-jarasport-tp-mcp-P<N>-<name>.md`.

**Goal:** Deliver a commercial-grade, owned, Clerk-authenticated TrainingPeaks MCP service across 8 sequential phases and one parallel Clerk integration session, with zero work slipping through cracks.

**Architecture:** Two-layer (`tp_core` + `tp_mcp`), Clerk JWT identity, per-user encrypted credential store, HTTP/SSE transport, multi-tenant.

**Tech Stack:** Python 3.10–3.14, httpx, Pydantic v2, structlog, OpenTelemetry, Prometheus, Clerk, Postgres/SQLite, Docker, GitHub Actions, sigstore.

**Ref spec:** [docs/superpowers/specs/2026-04-25-jarasport-tp-mcp-design.md](../specs/2026-04-25-jarasport-tp-mcp-design.md)

---

## 0. How to Use This Document

**Every session:**

1. **On start** — read this file top-to-bottom. Identify the current phase, open handoffs, unresolved risks, unanswered questions. Check the Session Ledger to see what the last session did.
2. **Mid-session** — update the Risk Register and Open Questions as they arise. Never leave a question only in conversation history.
3. **On exit** — append an entry to the Session Ledger (§11), update the Phase Status Matrix (§1), commit this file along with any code.

**Golden rule:** if it is not written in this document, it does not exist. Conversation memory is not a valid coordination mechanism across sessions.

---

## 1. Phase Status Matrix

Update whenever a phase transitions between statuses. Timestamps in `YYYY-MM-DD`.

| Phase | Name                           | Status      | Plan file                                                            | Started    | Completed  | DoD Signed Off | Blocked On |
|:------|:-------------------------------|:------------|:---------------------------------------------------------------------|:-----------|:-----------|:---------------|:-----------|
| P0    | Foundations                    | PENDING     | `2026-04-25-jarasport-tp-mcp-P0-foundations.md`                      | —          | —          | —              | —          |
| P1    | tp_core                        | NOT STARTED | `2026-04-25-jarasport-tp-mcp-P1-tp-core.md` (to write)               | —          | —          | —              | P0         |
| P2    | tp_mcp shell                   | NOT STARTED | `2026-04-25-jarasport-tp-mcp-P2-tp-mcp-shell.md` (to write)          | —          | —          | —              | P1         |
| P3    | Tool migration                 | NOT STARTED | `2026-04-25-jarasport-tp-mcp-P3-tool-migration.md` (to write)        | —          | —          | —              | P2         |
| P4    | Reliability & observability    | NOT STARTED | `2026-04-25-jarasport-tp-mcp-P4-reliability-observability.md`        | —          | —          | —              | P3         |
| P5    | Release & supply chain         | NOT STARTED | `2026-04-25-jarasport-tp-mcp-P5-release-supply-chain.md`             | —          | —          | —              | P4         |
| P6    | Docs                           | NOT STARTED | `2026-04-25-jarasport-tp-mcp-P6-docs.md`                             | —          | —          | —              | P4 (parallel with P5) |
| P7    | RDH cutover                    | NOT STARTED | `2026-04-25-jarasport-tp-mcp-P7-rdh-cutover.md`                      | —          | —          | —              | P5 + Clerk |
| CLK   | Clerk integration (other session) | PENDING     | [`./2026-04-25-jarasport-clerk-integration-master.md`](./2026-04-25-jarasport-clerk-integration-master.md) | —          | —          | —              | — (CLK-0 is `actionable: auto`; ADR-0001 drafted 2026-04-25, owner sign-off is CLK-0 Task 7) |

**Status vocabulary:**
- `NOT STARTED` — no work done, prerequisites may not be met.
- `PENDING` — prerequisites met, ready to start, plan file written.
- `IN PROGRESS` — a session has claimed it (see §3 Session Claims).
- `BLOCKED` — started but halted on an external dependency. Must list reason in "Blocked On".
- `DONE — UNVERIFIED` — tasks complete, DoD not yet signed off.
- `DONE` — all DoD criteria green, signed off by dated entry in §9.

---

## 2. Dependency Graph

```
P0 ──► P1 ──► P2 ──► P3 ──► P4 ──┬──► P5 ──► P7 ──► DONE
                                 │              ▲
                                 └──► P6 ───────┘

CLK (parallel, runs any time after ADR-0001 is signed) ──► unblocks P7
```

- P4 → P5 and P4 → P6 may run partly in parallel by different sessions if §3 session claims are respected.
- P7 requires both P5 and CLK to be DONE.

---

## 3. Session Claims (Concurrent Session Lock)

**Purpose:** prevent two simultaneous sessions from modifying the same phase. This file is the lock table.

When a session begins work on a phase, it **must** add a row here. When the session ends, it **must** either mark the row `RELEASED` (work continues next session) or delete the row (work complete this session). If the session crashes without releasing, the next session must verify what was actually done before claiming.

| Phase | Session ID (timestamp + initials) | Claimed At       | Released At      | Status    | Notes |
|:------|:----------------------------------|:-----------------|:-----------------|:----------|:------|
|       |                                   |                  |                  |           |       |

**Rule:** a phase with an active (not-RELEASED) claim cannot be picked up by another session. If you must preempt (e.g., the claim is stale >48h), add a new row noting preemption and why.

---

## 4. Handoff Artefacts

Between-phase contracts. Each handoff is a markdown file under `docs/superpowers/plans/HANDOFFS/`. The **producing phase** writes the handoff; the **consuming phase** reads it before starting.

| From | To  | Handoff file                           | Status       | Summary of contract |
|:-----|:----|:---------------------------------------|:-------------|:--------------------|
| P0   | P1  | `HANDOFFS/P0-to-P1.md`                 | not written  | Scaffold, lint/type/test conventions, package layout |
| P1   | P2  | `HANDOFFS/P1-to-P2.md`                 | not written  | `tp_core` public API, `AuthProvider` protocol, `TPClient` constructor signature |
| P2   | P3  | `HANDOFFS/P2-to-P3.md`                 | not written  | `UserContext` shape, tool registry API, schema plumbing, error taxonomy |
| P3   | P4  | `HANDOFFS/P3-to-P4.md`                 | not written  | Full tool surface, known performance baselines, known rough edges |
| P4   | P5  | `HANDOFFS/P4-to-P5.md`                 | not written  | Observability configuration surface, release-readiness of service |
| P4   | P6  | `HANDOFFS/P4-to-P6.md`                 | not written  | Architecture facts, runbook inputs |
| P5   | P7  | `HANDOFFS/P5-to-P7.md`                 | not written  | Deployment coordinates, migration tooling, feature-flag scheme |
| CLK  | P2  | `HANDOFFS/CLK-1-to-P2.md`              | scheduled (CLK-1 Task 12) | Clerk JWT verification SDK choice, JWKS URL, expected claims — produced by CLK-1 |
| CLK  | P7  | `HANDOFFS/CLK-6-to-P7.md`              | scheduled (CLK-6 Task 13) | Onboarding UI routes, "Connect TP" entry point, cutover gating — produced by CLK-6 |
| ADR  | CLK | `docs/adr/ADR-0001-clerk-boundary.md`  | drafted 2026-04-25; sign-off in CLK-0 Task 7 | Auth boundary; ownership matrix; wire format; rejection codes |

**Writing a handoff:** before marking a phase DONE, the producing session must ensure the handoff file exists and captures every assumption the consumer may make. The consuming session's first step is "read handoff and ask questions" — if the handoff is ambiguous, the consumer pings back, doesn't guess.

---

## 5. Definition of Done per Phase

A phase cannot move to `DONE` until every item here is green. Sign-off in §9.

### Universal (applies to every phase that ships code)

- [ ] All tasks in the phase's plan file marked complete.
- [ ] `ruff check` + `ruff format --check` clean on all changed files.
- [ ] `mypy --strict` clean on all changed files.
- [ ] `pytest` green on Python 3.10, 3.11, 3.12, 3.13, 3.14.
- [ ] Line coverage ≥ 90%, branch coverage ≥ 85% on code introduced this phase.
- [ ] Every new public module/function/class has a docstring.
- [ ] No new `# type: ignore`, `# noqa`, or `pragma: no cover` without an inline comment explaining why.
- [ ] Handoff file (§4) for this phase is written and committed.
- [ ] Session Ledger (§11) updated.
- [ ] Risk register (§7) reviewed — any new risks added.
- [ ] Open questions (§8) reviewed — any resolved questions moved to the spec or an ADR.

### Phase-specific

- **P0** — CI pipeline runs on a no-op commit and all jobs pass; container builds; pre-commit hooks installed and effective.
- **P1** — `tp_core` importable standalone (no `tp_mcp` imports); property tests for every parser; integration test hits a mock TP via `respx` and exercises the full HTTP → cache → model roundtrip.
- **P2** — HTTP/SSE server accepts a faked Clerk JWT and routes a hello-world tool; SQLite credential store round-trips an encrypted blob; stub `ClerkUserAuth` allows P2 to ship before the CLK session completes.
- **P3** — All 52 tools behave identically to the old fork on recorded cassettes; parity matrix (§6) is fully green; property tests cover every parser on random sport/tier inputs.
- **P4** — `/metrics` endpoint scrapes clean in Prometheus; traces visible end-to-end in an OTLP collector; log-safety test with a plant secret produces zero leaks; circuit breaker and rate limiter validated under simulated load.
- **P5** — Signed release on PyPI (sigstore verified); signed OCI image on ghcr.io (cosign verified); SBOM attached; deploy pipeline green to the chosen platform; production health green 72 hours.
- **P6** — All docs in `docs/` reviewed; ADRs 0001–0004 present; runbook exercised by running each documented procedure end-to-end at least once in a staging environment.
- **P7** — RDH runs `TP_MCP_IMPL=jarasport` for 14 days without regression; old fork repository archived with a deprecation README; all users migrated via the onboarding flow.

---

## 6. Parity Matrix — 52 Tools

Every tool from the current fork must reach the final column green before P3 closes. This is the anti-drop-through guard for the tool surface.

| # | Tool | Port | Unit | Contract | Integration (VCR) | Property (if parser) | Behaviour vs old fork |
|---|------|:----:|:----:|:--------:|:-----------------:|:--------------------:|:----------------------:|
| 1 | tp_add_workout_comment | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 2 | tp_analyze_workout | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 3 | tp_auth_status | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 4 | tp_copy_workout | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 5 | tp_create_availability | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 6 | tp_create_equipment | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 7 | tp_create_event | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 8 | tp_create_library | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 9 | tp_create_library_item | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 10 | tp_create_note | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 11 | tp_create_workout | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 12 | tp_delete_availability | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 13 | tp_delete_equipment | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 14 | tp_delete_event | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 15 | tp_delete_library | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 16 | tp_delete_note | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 17 | tp_delete_workout | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 18 | tp_delete_workout_file | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 19 | tp_download_workout_file | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 20 | tp_get_athlete_settings | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 21 | tp_get_atp | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 22 | tp_get_availability | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 23 | tp_get_equipment | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 24 | tp_get_events | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 25 | tp_get_fitness | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 26 | tp_get_focus_event | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 27 | tp_get_libraries | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 28 | tp_get_library_item | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 29 | tp_get_library_items | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 30 | tp_get_metrics | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 31 | tp_get_next_event | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 32 | tp_get_nutrition | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 33 | tp_get_peaks | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 34 | tp_get_pool_length_settings | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 35 | tp_get_profile | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 36 | tp_get_weekly_summary | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 37 | tp_get_workout | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 38 | tp_get_workout_comments | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 39 | tp_get_workout_prs | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 40 | tp_get_workout_types | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 41 | tp_get_workouts | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 42 | tp_list_athletes | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 43 | tp_log_metrics | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 44 | tp_refresh_auth | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 45 | tp_reorder_workouts | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 46 | tp_schedule_library_workout | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 47 | tp_update_equipment | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 48 | tp_update_event | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 49 | tp_update_ftp | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 50 | tp_update_hr_zones | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 51 | tp_update_library_item | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 52 | tp_update_nutrition | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 53 | tp_update_speed_zones | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 54 | tp_update_workout | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 55 | tp_upload_workout_file | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |
| 56 | tp_validate_structure | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 57 | tp_delete_library | ☐ | ☐ | ☐ | ☐ | n/a | ☐ |

(Row count reflects the currently visible MCP tool list; verify against `git grep -l '^@tool' src/` in the old fork during P3 kick-off and correct this matrix before starting the port.)

**Tool-counts drift check:** the spec says "52 tools"; the old fork's CLAUDE.md says "52 tools" but the MCP deferred-tool list enumerates more. P3's first task is reconcile the true count and update this table.

---

## 7. Risk Register

Live. Each risk has an ID (`R-NNN`), a description, impact, likelihood, mitigation, and status.

| ID    | Risk                                                                 | Impact | Likelihood | Mitigation                                                                 | Status  | Opened     | Closed     |
|:------|:---------------------------------------------------------------------|:------:|:----------:|:---------------------------------------------------------------------------|:--------|:-----------|:-----------|
| R-001 | TP changes internal API, breaks cookie→JWT exchange                  | High   | Medium     | Circuit breaker, weekly synthetic probe, alerting on known-endpoint 404s   | Open    | 2026-04-25 | —          |
| R-002 | Clerk session slips behind this work                                 | High   | Medium     | P2 ships a `StubClerkAuth` returning a fake user_id; swap later is 1-day  | Open    | 2026-04-25 | —          |
| R-003 | Postgres KMS integration is platform-specific                        | Medium | Medium     | ADR-0002 picks backend early; SQLite covers P0–P4                         | Open    | 2026-04-25 | —          |
| R-004 | Parity suite produces divergent behaviour during migration           | High   | Low        | Run parity suite against both impls in CI; flag-gated rollout              | Open    | 2026-04-25 | —          |
| R-005 | Credential-store encryption key lost                                 | High   | Low        | KMS-backed key escrow; documented rotation; tested restore runbook         | Open    | 2026-04-25 | —          |
| R-006 | Actual TP rate limit tighter than 100/min                            | Medium | Medium     | Empirical calibration in P4; per-endpoint overrides; bulk batching         | Open    | 2026-04-25 | —          |
| R-007 | Supply-chain compromise via dependency takeover                      | High   | Low        | Pinned deps, Renovate with CI gates, cosign verification, no post-install  | Open    | 2026-04-25 | —          |
| R-008 | Session-continuity failure — work done in one session invisible to next | High | Medium | **This document.** Session Ledger + DoD enforcement                          | Open    | 2026-04-25 | —          |
| R-009 | Tool parity drift — upstream fork adds features mid-rebuild          | Medium | Medium     | Lock parity snapshot at P3 start; track upstream deltas in §10 changelog   | Open    | 2026-04-25 | —          |
| R-010 | Test-coverage gate gamed with trivial tests                          | Medium | Medium     | Mutation testing (stretch) + manual PR review; branch coverage ≥85%        | Open    | 2026-04-25 | —          |

**Adding a risk:** next session that spots one appends a new row. Never delete rows — mark `Closed` with a date and a `Closed` status.

---

## 8. Open Questions Tracker

Live. Questions that surface during execution and are not answered in the spec. Each question gets a resolution path.

| ID    | Question                                                                        | Raised     | Owner    | Resolution path                 | Resolved   |
|:------|:--------------------------------------------------------------------------------|:-----------|:---------|:--------------------------------|:-----------|
| Q-001 | PyPI name: `jarasport-tp-mcp` — available? Check before P0.                     | 2026-04-25 | P0 session | `pip index versions jarasport-tp-mcp` | —      |
| Q-002 | Deploy target: Fly.io or Cloud Run?                                             | 2026-04-25 | P5 session | ADR-0002 + cost comparison     | —          |
| Q-003 | Should `tp_core` be published as a separate PyPI package?                       | 2026-04-25 | P5 session | Defer; revisit post-P5          | —          |
| Q-004 | Will Jarasport's existing Clerk tenant be reused, or a separate tenant?         | 2026-04-25 | CLK session | Cross-session sync               | —          |
| Q-005 | Target SaaS audience: internal only, or external coaches?                       | 2026-04-25 | Product | Owner decision before P5        | —          |
| Q-006 | Adaptive rate-limit (observe 429s) vs fixed budget?                             | 2026-04-25 | P4 session | Fixed first, revisit after load tests | —    |
| Q-007 | Mutation-testing coverage target (75%?) — stretch goal validity                 | 2026-04-25 | P3 session | Revisit after P3 coverage data  | —          |

**Adding a question:** any session that encounters ambiguity adds a row and proceeds with the most conservative interpretation, noting the decision in the Session Ledger.

---

## 9. DoD Sign-Offs

When a phase's universal + phase-specific DoD is green, the session that signs off appends an entry here with date and session ID. A DoD entry is **the** audit trail of completion.

| Phase | Signed Off At       | Session ID     | Notes |
|:------|:--------------------|:---------------|:------|
|       |                     |                |       |

---

## 10. Upstream Drift Tracker

`JamsusMaximus/trainingpeaks-mcp` may add features during the rebuild. We do not follow them automatically, but we track them to decide whether to backport into our scope.

**Cadence:** the owning session for any in-progress phase runs `git fetch origin && git log HEAD..origin/main --oneline` weekly and appends deltas here.

| Date       | Upstream commit range | Summary | Decision (ignore / backport / note) |
|:-----------|:----------------------|:--------|:------------------------------------|
| 2026-04-25 | origin/main at `1d19786` (baseline) | Baseline at program start | Ignore — we are a clean rebuild |

---

## 11. Session Ledger

**Every session appends one row before exiting.** Even if no code changed. This is the single most important hygiene rule in this document.

| Date       | Session ID | Phase | What changed | Files touched | Tests added | Coverage delta | Commits | Next step for next session |
|:-----------|:-----------|:------|:-------------|:--------------|:-----------:|:--------------:|:-------:|:---------------------------|
| 2026-04-25 | 2026-04-25-JRK-plan | master+P0 | Spec + master plan + P0 plan written | `docs/superpowers/specs/` + `docs/superpowers/plans/` | 0 | n/a | 2 | Start P0 task 1 (PyPI name check) |

---

## 12. Session Protocol

### On start

1. `git fetch --all && git pull`
2. Read this file top-to-bottom. Resolve anything in "Next step for next session" from the last row of §11.
3. Read the current phase's plan file.
4. Read any handoff files that are inputs to this phase.
5. Check §3 Session Claims. If the phase is unclaimed, claim it. If claimed and stale (>48h, no §11 entry), preempt with a note.
6. Read the upstream drift tracker §10 — if a fetch reveals new upstream commits, add a row and decide.
7. Announce in chat: "Resuming P<N> task <M>. Last session ended at task <K>."

### Mid-session

- Every completed task is checked off in the phase plan file.
- Every task that adds code adds at least one test **in the same commit** (enforced by the phase DoD and by pre-commit hooks starting in P0).
- Any new risk, question, or assumption is written into §7 / §8 **before** the session ends.
- Commits follow conventional-commit style (`feat:`, `fix:`, `test:`, `docs:`, `chore:`). Each task is one or more commits, never fewer.

### On exit

1. Append a row to §11 Session Ledger.
2. Update §1 Phase Status Matrix.
3. Update §3 Session Claims (release or mark still-in-progress).
4. If phase is complete, run the DoD checklist (§5); if green, add a row to §9.
5. Write or update the handoff file (§4) if this session produced output the next phase consumes.
6. Commit this file along with code.
7. If this session ended in a worktree, state the worktree location in the ledger.

### Recommended execution context

Run phase sessions in a dedicated git worktree per phase (`git worktree add ../jarasport-tp-mcp-P<N> feature/P<N>-<name>`). Keeps parallel sessions isolated. `superpowers:using-git-worktrees` skill handles this.

---

## 13. Test-All-Code Policy

**The rule:** every production code file has a matching test file. A file without tests is treated as a bug, not a feature.

### Enforcement

- **CI gate:** coverage ≥90% line, ≥85% branch on the phase's changed files. CI fails if missed.
- **Pre-commit hook** (added in P0): rejects a commit that adds a `src/**/*.py` file without a corresponding `tests/**/test_*.py` file. Override requires `[skip-test-coverage]` in the commit body and a reason.
- **PR review checklist** (P0 template): "Does every new public function have a unit test?" / "Does every new parser have a property test?" / "Does every new tool have a contract test?"

### Test kinds required per code kind

| Code kind | Required tests |
|:----------|:---------------|
| Pure function in `tp_core/` | Unit test + (if it parses anything) property test |
| Pydantic model | Unit test (happy path + `extra='ignore'`) + property test |
| HTTP client method | Unit test + integration test via `respx` |
| Auth provider | Unit test + integration test exercising the full cookie→JWT exchange |
| Cache component | Unit test + concurrency test (asyncio) |
| Rate limiter / circuit breaker | Unit test + behaviour test under simulated load |
| Tool handler | Unit test + contract test (schema roundtrip) + integration test (VCR) |
| Transport | Integration test with a fake client |
| CLI command | Integration test via `CliRunner` or similar |
| Observability middleware | Log-safety test + PII-scrub test |

### Test-coverage discipline

- A test that does not assert anything is worse than no test. PR template calls this out.
- Do not test implementation details (private method internals). Test behaviour.
- Mocks are allowed at the boundary (`httpx` mocked via `respx`). Do not mock `tp_core` internals in `tp_core` tests — use real objects.

---

## 14. Definition of "Done" for the whole program

Every box below must be ticked before declaring the program complete. These map 1:1 to Success Criteria in the spec.

- [ ] Feature parity: parity matrix §6 fully green.
- [ ] Coverage gate green on main for 7 consecutive days.
- [ ] CI matrix green on Python 3.10, 3.11, 3.12, 3.13, 3.14.
- [ ] Benchmarks within 20% of baseline (`tests/benchmarks/baseline.json`).
- [ ] Log-safety test with plant secret passes; zero leaks in scan.
- [ ] User-isolation integration test passes (no cross-user data access).
- [ ] Signed release on PyPI (sigstore) + ghcr.io (cosign) with SBOM.
- [ ] Deployed on chosen platform, health green ≥14 days.
- [ ] RDH running `TP_MCP_IMPL=jarasport` as default ≥14 days.
- [ ] Old fork `jara-r-k/trainingpeaks-mcp` archived with deprecation README pointing at new package.
- [ ] Clerk JWT verification p95 < 5ms in production.
- [ ] All §7 risks closed or accepted with documented rationale.
- [ ] All §8 questions resolved.
- [ ] `docs/adr/ADR-0001-clerk-boundary.md` through `ADR-0004` present.

---

## 15. Index of Related Docs

- Spec: [../specs/2026-04-25-jarasport-tp-mcp-design.md](../specs/2026-04-25-jarasport-tp-mcp-design.md)
- P0 plan: [./2026-04-25-jarasport-tp-mcp-P0-foundations.md](./2026-04-25-jarasport-tp-mcp-P0-foundations.md)
- P1–P7 plans: written at phase-start, filed alongside this file.
- ADRs: `../../adr/` — ADR-0001 (Clerk boundary) drafted 2026-04-25; ADR-0002…0004 created in P5/P6.
- Handoffs: `./HANDOFFS/`.
- State snapshots (optional, for crash recovery): `./STATE/`.
- **CLK (parallel Clerk integration) program**:
  - Spec: [../specs/2026-04-25-jarasport-clerk-integration-design.md](../specs/2026-04-25-jarasport-clerk-integration-design.md)
  - Master: [./2026-04-25-jarasport-clerk-integration-master.md](./2026-04-25-jarasport-clerk-integration-master.md)
  - ADR-0001 (Clerk boundary — prerequisite): [../../adr/ADR-0001-clerk-boundary.md](../../adr/ADR-0001-clerk-boundary.md)
  - Phase plans CLK-0…CLK-6: `./2026-04-25-jarasport-clerk-integration-CLK-*.md`
  - RDH cross-repo pointer: `~/projects/Jarasport/Race Day Hub/docs/superpowers/plans/2026-04-25-clerk-integration-pointer.md`
  - Wiki concept: `~/projects/wiki/concepts/clerk-identity-layer.md`

---

_Last updated: 2026-04-25 by planning session._
