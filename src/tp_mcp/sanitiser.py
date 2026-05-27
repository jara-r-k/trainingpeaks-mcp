"""Central result sanitiser — strips auth artefacts before any tool result reaches Claude.

Every tool response passes through sanitise_result() at the server dispatch layer,
so individual tools cannot accidentally leak credentials even if a future change
inadvertently includes them.
"""

import re
from typing import Any

# Keys whose values are always replaced, matched case-insensitively.
_SENSITIVE_KEYS: frozenset[str] = frozenset(
    [
        "cookie",
        "cookies",
        "access_token",
        "accesstoken",
        "refresh_token",
        "refreshtoken",
        "authorization",
        "tpauthheader",
        "production_tpauth",
        "password",
        "secret",
        "set-cookie",
        # Broader auth-related keys kept for defence-in-depth.
        "token",
        "auth_token",
        "authtoken",
        "credential",
        "credentials",
    ]
)

# JWT: three base64url segments separated by dots, each ≥8 chars.
_JWT_RE = re.compile(
    r"(?:Bearer\s+)?[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"
)

# TP auth cookie embedded in a larger string (e.g. a Set-Cookie header value).
_TP_COOKIE_RE = re.compile(r"Production_tpAuth=[^;\s]+")

_REDACTED = "<redacted>"


def _redact_string(value: str) -> str:
    """Replace JWT-shaped tokens and TP auth cookies inside a string value."""
    value = _JWT_RE.sub(_REDACTED, value)
    value = _TP_COOKIE_RE.sub(f"Production_tpAuth={_REDACTED}", value)
    return value


def sanitise_result(value: Any, *, _depth: int = 0) -> Any:
    """Recursively walk *value* and replace auth-related keys/token strings.

    Dicts: keys matching _SENSITIVE_KEYS have their values replaced with "<redacted>".
    Strings: JWT-shaped tokens and Production_tpAuth cookie fragments are redacted.
    Lists/tuples: each element is sanitised recursively.
    Scalars (int, float, bool, None): returned unchanged.

    Recursion is capped at depth 16 to prevent stack exhaustion from deeply
    nested or cyclic-like structures.
    """
    if _depth > 16:
        return value

    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for k, v in value.items():
            if isinstance(k, str) and k.lower() in _SENSITIVE_KEYS:
                result[k] = _REDACTED
            else:
                result[k] = sanitise_result(v, _depth=_depth + 1)
        return result

    if isinstance(value, list):
        return [sanitise_result(item, _depth=_depth + 1) for item in value]

    if isinstance(value, tuple):
        return tuple(sanitise_result(item, _depth=_depth + 1) for item in value)

    if isinstance(value, str):
        return _redact_string(value)

    # int, float, bool, None, and other non-container types pass through unchanged.
    return value
