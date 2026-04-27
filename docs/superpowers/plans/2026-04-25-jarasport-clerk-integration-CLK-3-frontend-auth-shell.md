---
title: jarasport-clerk-integration-CLK-3-frontend-auth-shell
plan: CLK Phase 3 — Frontend Auth Shell (Race Day Hub)
status: not-started
owner: jara-r-k
date: 2026-04-25
project: Jarasport
parent: jarasport-clerk-integration-master
phase: CLK-3
actionable: blocked
blocked_on: CLK-0
next_action: (Blocked) Await CLK-0 DoD sign-off
depends_on: CLK-0
---

# CLK-3 — Frontend Auth Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL — `superpowers:test-driven-development` + `superpowers:executing-plans`. This phase primarily modifies `Jarasport/Race Day Hub` (RDH), with a single tiny touch on `jarasport-tp-mcp` (a canary `/health` route). Follow RDH's [CLAUDE.md](../../../../Jarasport/CLAUDE.md): **pnpm**, React 19, TS 5, Vite 6, Tailwind 4, shadcn/Radix, Australian English.

**Before you start:** read the [CLK master](./2026-04-25-jarasport-clerk-integration-master.md) §12 + `HANDOFFS/CLK-0-to-CLK-3.md`. Claim the phase.

**Goal:** Mount `ClerkProvider` at the RDH React root, ship `/sign-in` and `/sign-up` routes via Clerk's prebuilt components themed to the Jarasport palette, ship a `ProtectedRoute` wrapper, and deliver `tpMcpClient.ts` which injects `Authorization: Bearer` via Clerk's `getToken({ template: "jarasport-mcp" })`. Leave `VITE_AUTH_IMPL=wix` as default — this phase ships the shell dormant behind a flag.

**Architecture:** `@clerk/clerk-react` v5+. Router-bridging via `useNavigate` + Clerk's `routerPush` / `routerReplace` to avoid double-navigation. Appearance config uses Jarasport brand tokens from [Jarasport/CLAUDE.md](../../../../Jarasport/CLAUDE.md) §Brand Reference.

**Tech Stack:** `@clerk/clerk-react` ≥5, `react-router-dom` 7 (already installed), Vitest 4, MSW 2, Playwright 1.58, `@axe-core/playwright`, Jarasport Tailwind 4 tokens.

**Estimated effort:** 3 working days. Runnable in parallel with CLK-1/2.

---

## Prerequisites

- CLK-0 DONE; handoff readable; `VITE_CLERK_PUBLISHABLE_KEY_DEV` populated in Vercel + `.env.local`.
- RDH dev server runs (`pnpm dev` inside `Jarasport/Race Day Hub/`).

---

## Tasks

### Task 1 — Dependencies

- [ ] 1.1 `cd "Jarasport/Race Day Hub"`
- [ ] 1.2 `pnpm add @clerk/clerk-react`
- [ ] 1.3 Commit: `chore(deps): add @clerk/clerk-react for CLK-3`.
- [ ] 1.4 Confirm via `pnpm list @clerk/clerk-react` the resolved version is v5+.

### Task 2 — Bundle-size budget (R-008 mitigation)

- [ ] 2.1 Run `pnpm build`, note `dist/` size before changes.
- [ ] 2.2 Reference the baseline in commit message.
- [ ] 2.3 Add a CI step (in `.github/workflows/rdh-build-check.yml` — create if absent) that fails if the main JS bundle grows more than +80kb gzipped vs pre-CLK-3 baseline.

### Task 3 — ClerkProvider mount (TDD)

- [ ] 3.1 Write `__tests__/auth/ClerkProviderWrapper.test.tsx` with MSW+Vitest:
  - Renders children when `publishableKey` provided.
  - Throws a clear error when missing `VITE_CLERK_PUBLISHABLE_KEY`.
- [ ] 3.2 Create `src/auth/ClerkProviderWrapper.tsx`:
  - Reads `import.meta.env.VITE_CLERK_PUBLISHABLE_KEY`.
  - Wraps `<ClerkProvider>` with `appearance={jarasportAppearance}` (colours + fonts from Jarasport CLAUDE.md).
  - Bridges Clerk router to React Router v7 via `routerPush` / `routerReplace`.
- [ ] 3.3 Update `src/main.tsx` to wrap the router tree:
  ```tsx
  <ClerkProviderWrapper>
    <RouterProvider router={router} />
  </ClerkProviderWrapper>
  ```
- [ ] 3.4 Run `pnpm test:run`; green.
- [ ] 3.5 Commit: `feat(auth): mount ClerkProvider with Jarasport appearance`.

### Task 4 — Sign-in / sign-up routes

- [ ] 4.1 Create `src/screens/SignIn.tsx`:
  - `<SignIn routing="path" path="/sign-in" signUpUrl="/sign-up" afterSignInUrl="/app" />`
- [ ] 4.2 Create `src/screens/SignUp.tsx` mirror.
- [ ] 4.3 Add routes in `src/router.tsx` (or wherever the React Router v7 tree is defined): `/sign-in/*`, `/sign-up/*` as children. The `*` suffix is required by Clerk for path-based routing.
- [ ] 4.4 Write `__tests__/screens/SignIn.test.tsx`: renders without crashing behind a mocked `<ClerkProvider>`.
- [ ] 4.5 Commit: `feat(auth): add /sign-in and /sign-up routes`.

### Task 5 — ProtectedRoute (TDD)

- [ ] 5.1 Write `__tests__/auth/ProtectedRoute.test.tsx`:
  - `SignedOut` → redirects to `/sign-in?redirect_url=<current>`.
  - `SignedIn` → renders child.
- [ ] 5.2 Create `src/auth/ProtectedRoute.tsx`:
  ```tsx
  export function ProtectedRoute({ children }: PropsWithChildren) {
    return (
      <>
        <SignedIn>{children}</SignedIn>
        <SignedOut>
          <RedirectToSignIn />
        </SignedOut>
      </>
    );
  }
  ```
  (Or hand-roll redirect with `useLocation` + `<Navigate>` if `RedirectToSignIn` doesn't support query-string preservation as needed.)
- [ ] 5.3 Do NOT yet wrap `/app/*` — that happens at CLK-6 cutover. CLK-3 ships the component but keeps it dormant.
- [ ] 5.4 Run tests; green.
- [ ] 5.5 Commit: `feat(auth): add ProtectedRoute wrapper`.

### Task 6 — `useApi` hook + `tpMcpClient` (TDD)

- [ ] 6.1 Write `__tests__/services/tpMcpClient.test.ts` using MSW:
  - Client calls `getToken({ template: "jarasport-mcp" })` before each request.
  - Sets `Authorization: Bearer <jwt>`.
  - Handles 401 by throwing a typed `UnauthorizedError` (does NOT auto-sign-out — UI decides).
  - Handles 5xx by retrying once with jittered backoff (50–150ms).
- [ ] 6.2 Create `src/auth/useApi.ts`:
  - Hook that returns a typed `fetch` wrapper, scoped to the MCP base URL.
  - Uses Clerk's `useAuth()` to obtain token per-call.
- [ ] 6.3 Create `src/services/tpMcpClient.ts`:
  - Typed client for `/credentials` + future MCP tool calls.
  - Base URL from `VITE_TP_MCP_BASE_URL`.
  - Consumes `useApi()` under the hood (or takes a `getToken` fn for testability).
- [ ] 6.4 Run tests; green. RDH coverage gates hold.
- [ ] 6.5 Commit: `feat(services): tpMcpClient with Clerk bearer token injection`.

### Task 7 — Feature flag plumbing

- [ ] 7.1 Add `src/auth/authImpl.ts`:
  ```ts
  export type AuthImpl = "wix" | "clerk";
  export function currentAuthImpl(): AuthImpl {
    const v = import.meta.env.VITE_AUTH_IMPL;
    return v === "clerk" ? "clerk" : "wix";
  }
  ```
- [ ] 7.2 Wire routes: when `currentAuthImpl() === "wix"`, existing wixBridge auth paths remain active; when `"clerk"`, Clerk routes take over. Use a top-level conditional in `src/router.tsx`.
- [ ] 7.3 `.env.example` and `.env.local` include `VITE_AUTH_IMPL=wix` by default.
- [ ] 7.4 Write `__tests__/auth/authImpl.test.ts`: default is `wix`; `"clerk"` env returns `"clerk"`; junk values return `"wix"`.
- [ ] 7.5 Commit: `feat(auth): feature flag VITE_AUTH_IMPL (default wix)`.

### Task 8 — Canary end-to-end check

- [ ] 8.1 In `jarasport-tp-mcp`, add a trivial `GET /health/authed` route that returns `{"user_id": ctx.user_id}`. (This is a one-file addition to the work landed in CLK-1/2.)
- [ ] 8.2 Start MCP dev server locally on port 8000.
- [ ] 8.3 With `VITE_AUTH_IMPL=clerk` set locally, `pnpm dev` on RDH, sign in with a test Clerk dev user, call the canary endpoint from the browser console using `tpMcpClient`.
- [ ] 8.4 Verify 200 + correct `user_id` matching Clerk `sub`.
- [ ] 8.5 Record the result in the session ledger.
- [ ] 8.6 Revert `VITE_AUTH_IMPL=wix` before committing.
- [ ] 8.7 Remove or gate the canary endpoint behind `DEBUG` flag before TP MCP merges P2.

### Task 9 — Playwright scaffolding

- [ ] 9.1 Add `e2e/auth.spec.ts` scaffold:
  - Uses Clerk's test-mode features (see Clerk docs for `testing_token`).
  - Sign-up → email verification bypass (Clerk test-mode) → redirected to `/app`.
  - Skipped by default (`test.skip()`), unskipped in CLK-4.
- [ ] 9.2 Run `pnpm e2e` as a syntax check.
- [ ] 9.3 Commit: `test(e2e): scaffold auth spec (skipped until CLK-4)`.

### Task 10 — Decide CQ-001 + CQ-002

- [ ] 10.1 Confirm `@greatsumini/react-facebook-login` and `@react-oauth/google` are no longer referenced after Clerk provides the equivalent flows.
- [ ] 10.2 If truly unreferenced: `pnpm remove @greatsumini/react-facebook-login @react-oauth/google`. If still referenced somewhere: flag in open questions and defer to CLK-6.
- [ ] 10.3 Update master plan §8 CQ-001 and CQ-002 with resolution + date.
- [ ] 10.4 Commit: `chore(deps): remove legacy Facebook + Google OAuth libraries replaced by Clerk`.

### Task 11 — Accessibility + keyboard UX

- [ ] 11.1 Playwright spec: run `axe-core` against `/sign-in` and `/sign-up` (even if skipped in default run, it's ready for CLK-4).
- [ ] 11.2 Manually verify keyboard navigation lands on sign-in form fields in natural order.
- [ ] 11.3 Confirm Clerk's components respect the Jarasport dark background (contrast ratio ≥4.5:1 for all text).

### Task 12 — Documentation

- [ ] 12.1 In `Jarasport/Race Day Hub/docs/`, add `clerk-frontend.md`:
  - How to run locally with Clerk dev tenant.
  - Feature flag usage.
  - `tpMcpClient` API summary.
  - Link back to the CLK master plan.
- [ ] 12.2 Commit: `docs(auth): frontend Clerk shell reference`.

### Task 13 — Handoff: CLK-3 → CLK-4

- [ ] 13.1 Create `HANDOFFS/CLK-3-to-CLK-4.md` (in `trainingpeaks-mcp/docs/superpowers/plans/HANDOFFS/`):
  - `tpMcpClient.ts` method signatures.
  - `ProtectedRoute` usage pattern.
  - Feature flag behaviour.
  - Clerk `<UserButton/>` is available globally — where to mount it.

### Task 14 — Master plan + RDH pointer updates

- [ ] 14.1 CLK master §1: CLK-3 → DONE.
- [ ] 14.2 CLK master §6: check off frontend artefacts.
- [ ] 14.3 CLK master §10 Feature Flag Tracker: dev flag flipped to `clerk` (Task 8 canary); staging + prod remain `wix`.
- [ ] 14.4 Update RDH pointer doc `Jarasport/Race Day Hub/docs/superpowers/plans/2026-04-25-clerk-integration-pointer.md` with commit SHAs.

---

## DoD (extends master §5)

- [ ] RDH coverage gates green.
- [ ] Bundle size within +80kb gzipped budget.
- [ ] `pnpm build` succeeds with no new TypeScript errors.
- [ ] Canary end-to-end test produced a correct `user_id` from a live Clerk JWT.
- [ ] `VITE_AUTH_IMPL=wix` remains default; RDH user-facing behaviour unchanged.
- [ ] CQ-001 + CQ-002 resolved (legacy OAuth libs removed or explicitly retained with reason).

---

## Handoff Outputs

1. `HANDOFFS/CLK-3-to-CLK-4.md`
2. `Jarasport/Race Day Hub/docs/clerk-frontend.md`
3. Updated RDH plan pointer.

---

## Exit Criteria

- All 14 tasks complete.
- DoD green.
- Master §9 sign-off.
- Dev flag = `clerk`; staging + prod = `wix`.
- CLK-4 unblocks.
