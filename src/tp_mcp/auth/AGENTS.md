<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# auth

## Purpose
Handles all credential lifecycle for the TrainingPeaks MCP server: cookie extraction from browsers, secure storage (system keyring with encrypted-file fallback), token exchange and validation. The root of all authentication — a stale or missing cookie here breaks every tool.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | Public surface: re-exports `get_credential`, `store_credential`, `clear_credential`, `validate_auth`, `validate_auth_sync`, `AuthResult`, `AuthStatus`, `CredentialResult` |
| `storage.py` | Unified credential retrieval chain: env var (`TP_AUTH_COOKIE`) → system keyring → encrypted file. `store_credential()` always writes to encrypted file first for reliability, then keyring if available |
| `keyring.py` | System keyring wrapper (`keyring` library). Returns `CredentialResult(success, cookie, message)` |
| `encrypted.py` | AES-256-GCM fallback storage — used when system keyring is unavailable (headless servers, Claude Desktop sandboxing on macOS) |
| `browser.py` | `extract_tp_cookie()` — uses `browser-cookie3` to pull `Production_tpAuth` cookie from Chrome, Firefox, Safari, or Edge. Optional dependency |
| `validator.py` | `validate_auth()` / `validate_auth_sync()` — POSTs cookie to TP token endpoint, returns `AuthResult(is_valid, athlete_id, email, status, message)` |

## For AI Agents

### Working In This Directory
- The credential retrieval priority order is: `TP_AUTH_COOKIE` env var → keyring → encrypted file. Never bypass this chain.
- `store_credential()` writes to encrypted file first, then keyring — this is intentional (macOS Claude Desktop can block keyring access).
- Cookie expiry is the most common failure mode (~2–4 week sessions). When 401s appear, instruct user to run `tp-mcp auth --from-browser auto`.
- Never log or return cookie/token values; `sanitiser.py` provides the last-line defence but auth code must be clean too.
- `AuthStatus` enum values: `VALID`, `EXPIRED`, `INVALID`, `UNKNOWN`.

### Testing Requirements
```bash
python3 -m pytest tests/test_auth/ -v
```
All three storage backends must be tested: env var, keyring (mocked), encrypted file.

### Common Patterns
- All public functions return a result dataclass (`CredentialResult`, `AuthResult`) rather than raising exceptions — callers check `.success` / `.is_valid`.
- `validate_auth_sync` wraps the async validator with `asyncio.run()` for CLI use.

## Dependencies

### Internal
- Used by `server.py` (`get_credential`, `validate_auth`) and `client/http.py` (token refresh)

### External
- `keyring>=25.0.0` — system credential store
- `cryptography>=42.0.0` — AES-256-GCM for encrypted fallback
- `browser-cookie3>=0.19.0` (optional) — browser cookie extraction
- `httpx` (via `validator.py`) — token exchange HTTP call

<!-- MANUAL: -->
