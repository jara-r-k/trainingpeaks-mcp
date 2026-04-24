---
title: jarasport-clerk-integration-CLK-2-credential-store-endpoints
plan: CLK Phase 2 — CredentialStore + /credentials endpoints
status: not-started
owner: jara-r-k
date: 2026-04-25
project: trainingpeaks-mcp
parent: jarasport-clerk-integration-master
phase: CLK-2
actionable: blocked
blocked_on: CLK-1
next_action: (Blocked) Await CLK-1 DoD sign-off
depends_on: CLK-1
---

# CLK-2 — CredentialStore + /credentials Endpoints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL — `superpowers:test-driven-development` + `superpowers:executing-plans`. Security-sensitive phase: run `bandit` + log-safety tests before claiming DoD.

**Before you start:** read the [CLK master](./2026-04-25-jarasport-clerk-integration-master.md) §12 and `HANDOFFS/CLK-1-to-CLK-2.md`. Claim the phase.

**Goal:** Implement a pluggable `CredentialStore` with SQLite dev backend + libsodium encryption, expose `POST/DELETE/GET /credentials/*` HTTP endpoints per ADR-0001, deliver OpenAPI schema, and pass the two non-negotiable security tests (log safety + cross-user isolation).

**Architecture:** `tp_mcp/credentials/` package with `Protocol`-based `CredentialStore` ABC; SQLite backend stores base64-encoded libsodium `secretbox` ciphertext keyed by Clerk `user_id`; master key from env `CREDENTIAL_STORE_KEY` (32-byte, base64). Endpoints mount behind the CLK-1 `ClerkAuthMiddleware`.

**Tech Stack:** `pynacl` ≥1.5 for libsodium, `aiosqlite` ≥0.19, FastAPI (adopted here for routing), `pydantic` ≥2.5, `pytest-asyncio`.

**Estimated effort:** 4 working days.

---

## Prerequisites

- CLK-1 DONE; handoff `CLK-1-to-CLK-2.md` readable.
- FastAPI is assumed as the HTTP framework. If TP MCP P2 has selected a different framework, adapt routing but keep the store layer unchanged.

---

## Tasks

### Task 1 — Dependencies

- [ ] 1.1 Add `pynacl>=1.5,<2` and `aiosqlite>=0.19,<1` and `fastapi>=0.110,<1` to dependencies.
- [ ] 1.2 Regenerate lockfile.
- [ ] 1.3 Commit: `chore(deps): add pynacl + aiosqlite + fastapi for CLK-2`.

### Task 2 — `CredentialStore` Protocol (TDD)

- [ ] 2.1 Write `tests/tp_mcp/test_credentials_store.py` with a parameterised test suite (works against any implementation):
  - Round-trip put/get.
  - `get()` on missing user → `None`.
  - `delete()` on missing user → no-op.
  - `status()` returns correct `connected=False` when absent, `True` with age after put.
  - Concurrent puts for the same user preserve the last-write; no corruption.
- [ ] 2.2 Create `src/tp_mcp/credentials/store.py`:
  ```python
  class CredentialStatus(BaseModel):
      connected: bool
      cookie_age_days: int | None
      last_refresh_at: datetime | None

  class CredentialStore(Protocol):
      async def put(self, user_id: str, cookie: str) -> None: ...
      async def get(self, user_id: str) -> str | None: ...
      async def delete(self, user_id: str) -> None: ...
      async def status(self, user_id: str) -> CredentialStatus: ...
  ```
- [ ] 2.3 Run tests (will fail until Task 4 provides an impl); commit protocol now.
- [ ] 2.4 Commit: `feat(credentials): add CredentialStore protocol + CredentialStatus model`.

### Task 3 — Encryption wrapper (TDD)

- [ ] 3.1 Write `tests/tp_mcp/test_credentials_encryption.py`:
  - Roundtrip encrypt/decrypt.
  - Decrypt with wrong key → `EncryptionError`.
  - Decrypt tampered ciphertext → `EncryptionError`.
  - Key too short → `ValueError` at construction.
  - Empty plaintext → works.
- [ ] 3.2 Create `src/tp_mcp/credentials/encryption.py`:
  - `class CredentialCipher(master_key: bytes)` using `nacl.secret.SecretBox`.
  - `encrypt(plaintext: str) -> str` returning base64(nonce || ciphertext).
  - `decrypt(blob: str) -> str` inverse.
  - `from_env(env_var: str = "CREDENTIAL_STORE_KEY")` factory that base64-decodes.
- [ ] 3.3 Run tests; green.
- [ ] 3.4 Commit: `feat(credentials): add libsodium encryption wrapper`.

### Task 4 — SQLite backend (TDD)

- [ ] 4.1 Write `tests/tp_mcp/test_credentials_sqlite.py`:
  - Reuse parameterised suite from Task 2.1.
  - Schema migration: fresh DB auto-creates `credentials` table.
  - Encrypted blob is not visible as plaintext in the SQLite file (scan `.db` file bytes).
- [ ] 4.2 Create `src/tp_mcp/credentials/sqlite.py`:
  - `SQLiteCredentialStore(path: Path, cipher: CredentialCipher)`.
  - Table `credentials(user_id TEXT PRIMARY KEY, ciphertext BLOB, created_at TEXT, updated_at TEXT)`.
  - All ops async via `aiosqlite`.
  - `status()` computes age from `updated_at`.
- [ ] 4.3 Run tests; green. Coverage ≥90%.
- [ ] 4.4 Commit: `feat(credentials): SQLite backend with encryption + audit timestamps`.

### Task 5 — Audit log

- [ ] 5.1 Extend `SQLiteCredentialStore` with a `credential_audit(user_id_hash TEXT, action TEXT, timestamp TEXT)` table.
- [ ] 5.2 Every `put`, `get`, `delete` writes an audit row with `sha256(user_id)[:16]`.
- [ ] 5.3 Test: perform put then get then delete; assert three audit rows with correct action values and identical hashes.
- [ ] 5.4 Commit: `feat(credentials): add audit log to SQLite backend`.

### Task 6 — `/credentials` endpoints (TDD)

- [ ] 6.1 Write `tests/tp_mcp/test_routes_credentials.py`:
  - `POST /credentials` with valid JWT and body → 204; store contains encrypted cookie.
  - `POST /credentials` without JWT → 401.
  - `POST /credentials` with malformed body → 400 (Pydantic error).
  - `DELETE /credentials` → 204 idempotent.
  - `GET /credentials/status` → correct `connected`, `cookie_age_days`, `last_refresh_at`.
- [ ] 6.2 Create `src/tp_mcp/routes/__init__.py` and `src/tp_mcp/routes/credentials.py`:
  - FastAPI `APIRouter`.
  - Depends on `UserContext` (pulled from `request.scope`).
  - Body model `CredentialUploadIn(tp_cookie: str)` with non-empty validator.
  - Writes go through injected `CredentialStore`.
- [ ] 6.3 Create `src/tp_mcp/server.py` (minimal FastAPI app composition root). Mounts `ClerkAuthMiddleware`, wires `CredentialStore` via dependency injection.
- [ ] 6.4 Run tests; green.
- [ ] 6.5 Commit: `feat(routes): /credentials endpoints with auth + store DI`.

### Task 7 — Cross-user isolation test (NON-NEGOTIABLE)

- [ ] 7.1 Write `tests/tp_mcp/test_security_isolation.py`:
  - Seed store with two users (u_A, u_B), distinct cookies.
  - Mint JWT for u_A, attempt to `GET /credentials/status`; assert u_A's result.
  - Mint JWT for u_A with tampered `sub=u_B`; signature becomes invalid, reject.
  - Attempt direct DB path injection on a constructed request → Pydantic rejects.
  - Attempt to `GET /credentials/status` after deleting u_A's cookie → `connected=False`; u_B unaffected.
- [ ] 7.2 Commit: `test(security): cross-user isolation suite for /credentials`.

### Task 8 — Log-safety test (NON-NEGOTIABLE)

- [ ] 8.1 Write `tests/tp_mcp/test_security_log_safety.py`:
  - Plant a known-secret cookie via `POST /credentials`.
  - Capture all `structlog` output from every endpoint call (POST, DELETE, GET) using `caplog` + structlog capture.
  - Capture all response bodies.
  - Assert the plant secret string is absent from every captured log line and every response body.
  - Also scan for `ciphertext` / `authorization` / `token` / `cookie` substrings in response bodies — must be absent.
- [ ] 8.2 Commit: `test(security): log-safety + response sanitisation for /credentials`.

### Task 9 — OpenAPI schema

- [ ] 9.1 Confirm FastAPI auto-generates OpenAPI at `/openapi.json`.
- [ ] 9.2 Export to `docs/api/openapi.yaml` via a script `scripts/export-openapi.py`.
- [ ] 9.3 Commit `docs/api/openapi.yaml` (track in git for reviewability).
- [ ] 9.4 Test: `pytest tests/test_openapi_snapshot.py` — exported YAML has routes `/credentials`, `/credentials/status`; schemas match Pydantic models.

### Task 10 — Observability hooks

- [ ] 10.1 Add `structlog` events for each endpoint:
  - `credential.put` / `credential.delete` / `credential.status_check`.
  - Fields: `user_id_hash`, `request_id`, `duration_ms`.
  - NEVER the cookie value.
- [ ] 10.2 Add Prometheus metrics (scaffolded, actual exporter in TP MCP P4):
  - Counter `credential_operations_total{action}`.
  - Histogram `credential_operation_duration_seconds{action}`.
- [ ] 10.3 Commit: `feat(credentials): structlog events + metrics counters`.

### Task 11 — `bandit` + `pip-audit`

- [ ] 11.1 Run `bandit -ll -r src/tp_mcp/credentials src/tp_mcp/routes` — zero medium+ findings.
- [ ] 11.2 Run `pip-audit --strict` — zero vulnerabilities in the new deps.
- [ ] 11.3 Fix or document every finding before DoD.
- [ ] 11.4 Commit: `chore(security): bandit + pip-audit green for CLK-2`.

### Task 12 — Documentation

- [ ] 12.1 Update `docs/auth.md` with a "Credentials" section:
  - Endpoint reference (cross-linked to OpenAPI).
  - Master key generation: `python -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())"`.
  - Rotation procedure (deferred runbook detail to CLK-5).
- [ ] 12.2 Commit: `docs(credentials): endpoints + master-key generation reference`.

### Task 13 — Handoffs

- [ ] 13.1 Create `HANDOFFS/CLK-2-to-CLK-4.md`:
  - Endpoint paths + contracts (copy from ADR-0001).
  - Error body format.
  - Rate-limit expectations (inherited from TP MCP P4 token bucket).
- [ ] 13.2 Create `HANDOFFS/CLK-2-to-CLK-5.md`:
  - CredentialStore Protocol signature.
  - Audit row schema.
  - How webhooks will call `store.delete(user_id)`.

### Task 14 — Master plan + open-question resolution

- [ ] 14.1 CLK master §1: CLK-2 → DONE.
- [ ] 14.2 CLK master §6: check off `credentials/store.py`, `credentials/sqlite.py`, `credentials/encryption.py`, `routes/credentials.py`, `docs/api/openapi.yaml`.
- [ ] 14.3 §8 CQ-005 resolution: "Push `tp_connected` from webhook (CLK-5); poll-fallback is a client behaviour, not a server one." Mark resolved.
- [ ] 14.4 §11 ledger row.
- [ ] 14.5 TP MCP master §4: mark `CredentialStore` API a documented input for P3 tool handlers.

---

## DoD (extends master §5)

- [ ] Universal DoD green.
- [ ] Cross-user isolation test passes.
- [ ] Log-safety test passes with plant secret absent everywhere.
- [ ] `bandit -ll` zero findings.
- [ ] `pip-audit --strict` zero findings.
- [ ] OpenAPI exported and committed.
- [ ] SQLite file does not contain plaintext when inspected byte-wise.
- [ ] p95 roundtrip on `GET /credentials/status` < 20ms local (in-process SQLite).

---

## Handoff Outputs

1. `HANDOFFS/CLK-2-to-CLK-4.md`
2. `HANDOFFS/CLK-2-to-CLK-5.md`
3. `docs/api/openapi.yaml` (new)
4. Updated `docs/auth.md`

---

## Exit Criteria

- All 14 tasks complete.
- DoD green.
- Master §9 sign-off row added.
- CLK-4 and CLK-5 unblock.
