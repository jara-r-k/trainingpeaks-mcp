"""Tests for the central result sanitiser."""

import pytest

from tp_mcp.sanitiser import sanitise_result, _REDACTED


# ---------------------------------------------------------------------------
# Key-name matching
# ---------------------------------------------------------------------------


class TestSensitiveKeyRedaction:
    def test_cookie_lowercase(self):
        assert sanitise_result({"cookie": "abc123"})["cookie"] == _REDACTED

    def test_cookie_titlecase(self):
        assert sanitise_result({"Cookie": "abc123"})["Cookie"] == _REDACTED

    def test_cookie_uppercase(self):
        assert sanitise_result({"COOKIE": "abc123"})["COOKIE"] == _REDACTED

    def test_cookies_plural(self):
        assert sanitise_result({"cookies": "x=y"})["cookies"] == _REDACTED

    def test_access_token(self):
        assert sanitise_result({"access_token": "tok"})["access_token"] == _REDACTED

    def test_accessToken_camelcase(self):
        assert sanitise_result({"accessToken": "tok"})["accessToken"] == _REDACTED

    def test_refresh_token(self):
        assert sanitise_result({"refresh_token": "tok"})["refresh_token"] == _REDACTED

    def test_refreshToken_camelcase(self):
        assert sanitise_result({"refreshToken": "tok"})["refreshToken"] == _REDACTED

    def test_authorization(self):
        assert (
            sanitise_result({"authorization": "Bearer x"})["authorization"] == _REDACTED
        )

    def test_Authorization_titlecase(self):
        assert (
            sanitise_result({"Authorization": "Bearer x"})["Authorization"] == _REDACTED
        )

    def test_tpauthheader(self):
        assert sanitise_result({"tpAuthHeader": "x"})["tpAuthHeader"] == _REDACTED

    def test_production_tpauth(self):
        assert (
            sanitise_result({"Production_tpAuth": "x"})["Production_tpAuth"]
            == _REDACTED
        )

    def test_password(self):
        assert sanitise_result({"password": "secret"})["password"] == _REDACTED

    def test_secret(self):
        assert sanitise_result({"secret": "shh"})["secret"] == _REDACTED

    def test_set_cookie(self):
        assert (
            sanitise_result({"set-cookie": "Production_tpAuth=abc"})["set-cookie"]
            == _REDACTED
        )

    def test_benign_key_unchanged(self):
        result = sanitise_result({"athlete_id": 42, "name": "Jane"})
        assert result == {"athlete_id": 42, "name": "Jane"}


# ---------------------------------------------------------------------------
# Nested structures
# ---------------------------------------------------------------------------


class TestNestedStructures:
    def test_nested_dict(self):
        data = {"outer": {"cookie": "secret", "safe": "ok"}}
        result = sanitise_result(data)
        assert result["outer"]["cookie"] == _REDACTED
        assert result["outer"]["safe"] == "ok"

    def test_deeply_nested_dict(self):
        data = {"a": {"b": {"c": {"cookie": "deep_secret"}}}}
        result = sanitise_result(data)
        assert result["a"]["b"]["c"]["cookie"] == _REDACTED

    def test_list_of_dicts(self):
        data = [{"cookie": "s1"}, {"safe": "value"}]
        result = sanitise_result(data)
        assert result[0]["cookie"] == _REDACTED
        assert result[1]["safe"] == "value"

    def test_dict_with_list_value(self):
        data = {"tokens": [{"access_token": "tok1"}, {"access_token": "tok2"}]}
        result = sanitise_result(data)
        assert result["tokens"][0]["access_token"] == _REDACTED
        assert result["tokens"][1]["access_token"] == _REDACTED

    def test_mixed_structure(self):
        # "credentials" is itself a sensitive key so its value is replaced wholesale.
        data = {
            "success": True,
            "athlete_id": 123,
            "credentials": {"cookie": "sensitive", "access_token": "tok"},
            "tags": ["running", "cycling"],
        }
        result = sanitise_result(data)
        assert result["success"] is True
        assert result["athlete_id"] == 123
        assert result["credentials"] == _REDACTED
        assert result["tags"] == ["running", "cycling"]

    def test_mixed_structure_nested_sensitive_keys(self):
        # When the outer key is benign, inner sensitive keys are still redacted.
        data = {
            "success": True,
            "athlete_id": 123,
            "auth_data": {"cookie": "sensitive", "access_token": "tok"},
            "tags": ["running", "cycling"],
        }
        result = sanitise_result(data)
        assert result["success"] is True
        assert result["athlete_id"] == 123
        assert result["auth_data"]["cookie"] == _REDACTED
        assert result["auth_data"]["access_token"] == _REDACTED
        assert result["tags"] == ["running", "cycling"]

    def test_tuple_elements_sanitised(self):
        data = ({"cookie": "s"}, "plain")
        result = sanitise_result(data)
        assert result[0]["cookie"] == _REDACTED
        assert result[1] == "plain"


# ---------------------------------------------------------------------------
# JWT-shaped string value redaction
# ---------------------------------------------------------------------------

_SAMPLE_JWT = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTYiLCJuYW1lIjoiSmFuZSJ9.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"


class TestJwtRedaction:
    def test_bare_jwt_in_string_value(self):
        result = sanitise_result({"message": _SAMPLE_JWT})
        assert _REDACTED in result["message"]
        assert "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9" not in result["message"]

    def test_bearer_jwt_in_string_value(self):
        result = sanitise_result({"message": f"Bearer {_SAMPLE_JWT}"})
        assert _REDACTED in result["message"]

    def test_jwt_embedded_in_longer_string(self):
        result = sanitise_result({"msg": f"token={_SAMPLE_JWT} extra"})
        assert _REDACTED in result["msg"]

    def test_short_dotted_string_not_redacted(self):
        # Three-segment but segments too short — should NOT match.
        result = sanitise_result({"msg": "a.b.c"})
        assert result["msg"] == "a.b.c"


# ---------------------------------------------------------------------------
# Production_tpAuth cookie redaction
# ---------------------------------------------------------------------------


class TestTpAuthCookieRedaction:
    def test_tp_auth_cookie_in_string(self):
        result = sanitise_result({"body": "Production_tpAuth=ABCDEF123456; Path=/"})
        assert "ABCDEF123456" not in result["body"]
        assert "Production_tpAuth" in result["body"]
        assert _REDACTED in result["body"]

    def test_tp_auth_standalone_string(self):
        # Top-level string (not inside a dict)
        result = sanitise_result("Production_tpAuth=supersecret123")
        assert "supersecret123" not in result
        assert _REDACTED in result


# ---------------------------------------------------------------------------
# Scalar pass-through
# ---------------------------------------------------------------------------


class TestScalarPassthrough:
    def test_int(self):
        assert sanitise_result(42) == 42

    def test_float(self):
        assert sanitise_result(3.14) == 3.14

    def test_bool_true(self):
        assert sanitise_result(True) is True

    def test_bool_false(self):
        assert sanitise_result(False) is False

    def test_none(self):
        assert sanitise_result(None) is None


# ---------------------------------------------------------------------------
# Recursion depth cap
# ---------------------------------------------------------------------------


class TestRecursionDepthCap:
    def test_depth_cap_does_not_crash(self):
        # Build a 20-level deep dict — exceeds cap of 16, should not raise.
        data: dict = {}
        node = data
        for i in range(20):
            node["child"] = {}
            node = node["child"]
        node["cookie"] = "deep_secret"

        # Should not raise RecursionError; deep cookie may not be redacted (beyond cap).
        result = sanitise_result(data)
        assert result is not None

    def test_large_list_does_not_crash(self):
        data = [{"athlete_id": i} for i in range(500)]
        result = sanitise_result(data)
        assert len(result) == 500
        assert result[0]["athlete_id"] == 0
