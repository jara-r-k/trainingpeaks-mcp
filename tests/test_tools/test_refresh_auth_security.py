"""Security tests for tp_refresh_auth tool.

These tests verify that cookie values can NEVER leak into tool output.
"""

from tp_mcp.tools.refresh_auth import _sanitize_result


class TestSanitizeResult:
    """Test the result sanitization function."""

    def test_redacts_cookie_key(self):
        """Cookie values must never appear in output — key kept, value replaced."""
        result = {
            "success": True,
            "cookie": "SENSITIVE_VALUE_12345",
            "message": "OK",
        }
        sanitized = _sanitize_result(result)
        assert sanitized["cookie"] == "<redacted>"
        assert "SENSITIVE_VALUE" not in str(sanitized)

    def test_redacts_auth_token_key(self):
        """Auth-related keys must have their values replaced."""
        result = {
            "success": True,
            "auth_token": "secret123",
            "token": "secret456",
            "message": "OK",
        }
        sanitized = _sanitize_result(result)
        assert sanitized["auth_token"] == "<redacted>"
        assert sanitized["token"] == "<redacted>"
        # Original values must not appear.
        assert "secret123" not in str(sanitized)
        assert "secret456" not in str(sanitized)

    def test_redacts_credential_key(self):
        """Credential keys must have their values replaced."""
        result = {
            "success": True,
            "credential": "mycred",
            "user_credential": "othercred",
            "message": "OK",
        }
        sanitized = _sanitize_result(result)
        assert sanitized["credential"] == "<redacted>"
        # user_credential contains "credential" as a substring but the sanitiser
        # matches exact keys (case-folded) — user_credential is not in the key list
        # so its value is preserved.
        assert sanitized["user_credential"] == "othercred"

    def test_preserves_safe_keys(self):
        """Safe keys should be preserved."""
        result = {
            "success": True,
            "message": "Authentication refreshed",
            "athlete_id": 12345,
            "email": "test@example.com",
            "browser": "chrome",
        }
        sanitized = _sanitize_result(result)
        assert sanitized == result

    def test_case_insensitive_filtering(self):
        """Filtering should be case-insensitive — values replaced, keys kept."""
        result = {
            "success": True,
            "COOKIE": "value1",
            "Cookie": "value2",
            "AUTH_TOKEN": "value3",
            "message": "OK",
        }
        sanitized = _sanitize_result(result)
        assert sanitized["COOKIE"] == "<redacted>"
        assert sanitized["Cookie"] == "<redacted>"
        # AUTH_TOKEN folds to "auth_token" which is in _SENSITIVE_KEYS.
        assert sanitized["AUTH_TOKEN"] == "<redacted>"


class TestCredentialResultRepr:
    """Test that CredentialResult doesn't leak cookies in repr."""

    def test_repr_hides_cookie(self):
        """Cookie value must not appear in repr."""
        from tp_mcp.auth.keyring import CredentialResult

        result = CredentialResult(
            success=True,
            message="Credential retrieved",
            cookie="SUPER_SECRET_VALUE_67890",
        )
        repr_str = repr(result)
        assert "SUPER_SECRET" not in repr_str
        assert "67890" not in repr_str
        assert "cookie=<present>" in repr_str

    def test_repr_shows_none_for_missing_cookie(self):
        from tp_mcp.auth.keyring import CredentialResult

        result = CredentialResult(success=False, message="No cred")
        repr_str = repr(result)
        assert "cookie=<None>" in repr_str


class TestBrowserCookieResultRepr:
    """Test that BrowserCookieResult doesn't leak cookies in repr."""

    def test_repr_hides_cookie_value(self):
        """Cookie value must not appear in repr."""
        from tp_mcp.auth.browser import BrowserCookieResult

        result = BrowserCookieResult(
            success=True,
            cookie="SUPER_SECRET_COOKIE_VALUE_12345",
            browser="chrome",
            message="Found cookie",
        )
        repr_str = repr(result)
        assert "SUPER_SECRET" not in repr_str
        assert "12345" not in repr_str
        assert "cookie=<present>" in repr_str

    def test_repr_shows_none_for_missing_cookie(self):
        """Repr should indicate when cookie is None."""
        from tp_mcp.auth.browser import BrowserCookieResult

        result = BrowserCookieResult(success=False, message="Not found")
        repr_str = repr(result)
        assert "cookie=<None>" in repr_str
