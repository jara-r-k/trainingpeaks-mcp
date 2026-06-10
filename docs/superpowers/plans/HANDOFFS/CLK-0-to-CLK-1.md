# Handoff: CLK-0 → CLK-1 (backend JWT verification)

Date: 2026-06-10. Produced by CLK-0 execution against the live Clerk dashboard.

> **Language-pivot note:** CLK-1 as originally planned (Python middleware in the
> trainingpeaks-mcp fork) is superseded by the 2026-05-27 replacement roadmap.
> The verifier already exists in TypeScript at
> `jarasport-tp-mcp/src/tp-mcp/auth/clerk.ts` (shipped in P0, tested against
> locally signed RS256 tokens). CLK-1 reduces to: point that verifier at the
> values below via env, add the 30s `clockTolerance` (tracked in Linear
> PRO-79), and verify a real token end-to-end once CLK-3 produces one.

## Tenant facts (dev)

- **Clerk application:** "RDH" (single app; Development + Production instances
  replace the drafted two-application split)
- **Instance:** Development — `ins_3Evo3V3KvP5zlnT8IHWp58FtMBs`
- **Frontend API / issuer:** `https://hip-emu-91.clerk.accounts.dev`
- **JWKS URL:** `https://hip-emu-91.clerk.accounts.dev/.well-known/jwks.json`
  (verified 2026-06-10: serves 1 RSA key, `alg=RS256`, `use=sig`)
- **Production instance:** not yet created — requires the prod domain; deferred
  to P4/CLK-6.

## JWT contract

- **Template name:** `jarasport-mcp` (`jtmp_3Evopkj2RMV5rn46qX8mCbCjrFz`)
- **Algorithm:** RS256 (instance default key, no custom signing key)
- **Token lifetime:** 60s; **verifier clock-skew tolerance:** 30s (ADR-0001)
- **Custom claims** (template): `email`, `email_verified`, `org_id`,
  `org_role`, `plan` (defaults `'none'`), `tp_connected` (defaults `false`)
- **Reserved claims** (Clerk adds automatically): `iss`, `sub`, `azp`, `exp`,
  `iat`, `nbf`, `jti`
- **azp values:** `http://localhost:5173` (dev). Prod/staging azp land with the
  production instance.

## Env wiring for jarasport-tp-mcp

```env
TP_MCP_AUTH_IMPL=clerk
CLERK_JWKS_URL=https://hip-emu-91.clerk.accounts.dev/.well-known/jwks.json
CLERK_ISSUER=https://hip-emu-91.clerk.accounts.dev
CLERK_AUTHORIZED_PARTIES=http://localhost:5173
```

## Smoke-test status

- Template persisted with all six custom claims — pass.
- JWKS endpoint serving a usable RS256 signing key — pass.
- Full mint-and-verify round-trip — **pending CLK-3** (requires a frontend
  session calling `getToken({ template: 'jarasport-mcp' })`; the dashboard no
  longer offers a token tester).
