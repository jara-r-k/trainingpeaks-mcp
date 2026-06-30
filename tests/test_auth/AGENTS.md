<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-30 | Updated: 2026-06-30 -->

# test_auth

## Purpose
Tests for the three credential storage backends and the auth validator. Covers keyring storage, AES-256-GCM encrypted-file fallback, and token validation logic. No real TP API calls are made — validator is tested against mocked HTTP responses.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | Package marker |
| `test_encrypted.py` | Tests for `EncryptedCredentialStore` — store/retrieve/clear with AES-256-GCM |
| `test_keyring.py` | Tests for keyring backend using `mock_keyring` fixture from `conftest.py` |
| `test_validator.py` | Tests for `validate_auth()` — mocked token endpoint responses, expired/invalid cookie handling |

## For AI Agents

### Working In This Directory
- Use `mock_keyring` fixture from root `conftest.py` for all keyring tests.
- Encrypted store tests should use a temporary directory — do not write to the real credential path.
- Test all three `AuthStatus` values: `VALID`, `EXPIRED`, `INVALID`.

### Testing Requirements
```bash
python3 -m pytest tests/test_auth/ -v
```

## Dependencies

### Internal
- `src/tp_mcp/auth/` — modules under test

<!-- MANUAL: -->
