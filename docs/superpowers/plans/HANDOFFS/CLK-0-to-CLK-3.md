# Handoff: CLK-0 → CLK-3 (frontend auth shell)

Date: 2026-06-10. Produced by CLK-0 execution against the live Clerk dashboard.

## What the frontend inherits

- **Clerk application:** "RDH", Development instance
  (`ins_3Evo3V3KvP5zlnT8IHWp58FtMBs`), Frontend API
  `https://hip-emu-91.clerk.accounts.dev`.
- **Sign-in methods (configured, live):** email + password (Client Trust on,
  min length 8) and Google OAuth (shared dev credentials — custom credentials
  required before production). Email required, **verified at sign-up** via
  one-time code.
- **JWT template to request:** `getToken({ template: 'jarasport-mcp' })` —
  60s lifetime, so request a fresh token per outbound call.

## Env var conventions

- `VITE_CLERK_PUBLISHABLE_KEY` — per-environment value in Vercel
  (`pk_test_…` from the Development instance's API Keys page for
  preview/development scopes; `pk_live_…` once the production instance
  exists). Stubs added to RDH `.env.example` by CLK-0.
- `VITE_AUTH_IMPL=wix | clerk` — feature flag, default `wix` until CLK-6
  cutover.

## Routes and UI

- Sign-in: `/sign-in/*`, sign-up: `/sign-up/*` (Clerk-hosted components).
- `<ClerkProvider>` mounts in `src/main.tsx`; appearance tokens come from the
  Jarasport brand definitions in the project CLAUDE.md.

## First task for CLK-3

After mounting the provider with the dev publishable key, complete the CLK-0
smoke test: sign in as a dev user, call
`getToken({ template: 'jarasport-mcp' })`, and POST it to the jarasport-tp-mcp
`/credentials` endpoint (or verify with the `ClerkJwtAuth` provider directly)
— this closes the full mint-and-verify loop that CLK-0 could only take to the
JWKS level.
