"""Tests for cookie validation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tp_mcp.auth.validator import AuthStatus, _resolve_self_athlete_id, validate_auth


class TestResolveSelfAthleteId:
    """The account holder's OWN athlete ID, not an arbitrary first roster entry."""

    def test_picks_coach_own_entry_over_first(self):
        # athletes[0] is a DIFFERENT athlete; the coach's own entry is later.
        user_data = {
            "personId": 900,
            "email": "Coach@Example.com",
            "athletes": [
                {"athleteId": 111, "email": "athlete-a@example.com", "coachedBy": 900},
                {"athleteId": 999, "email": "coach@example.com", "coachedBy": 900},
                {"athleteId": 222, "email": "athlete-b@example.com", "coachedBy": 900},
            ],
        }
        # Must return the coach's own entry (999), not athletes[0] (111).
        assert _resolve_self_athlete_id(user_data) == 999

    def test_falls_back_to_first_when_no_self_match(self):
        # No entry matches on email → keep prior behaviour (first roster entry).
        user_data = {
            "personId": 900,
            "email": "coach@example.com",
            "athletes": [{"athleteId": 111}, {"athleteId": 222}],
        }
        assert _resolve_self_athlete_id(user_data) == 111

    def test_falls_back_to_person_id_when_no_athletes(self):
        user_data = {"personId": 500, "email": "solo@example.com", "athletes": []}
        assert _resolve_self_athlete_id(user_data) == 500

    def test_email_match_is_case_insensitive(self):
        user_data = {
            "personId": 900,
            "email": "Coach@Example.com",
            "athletes": [
                {"athleteId": 111, "email": "other@example.com", "coachedBy": 900},
                {"athleteId": 999, "email": "COACH@example.com", "coachedBy": 900},
            ],
        }
        assert _resolve_self_athlete_id(user_data) == 999


class TestValidateAuth:
    """Tests for validate_auth function."""

    @pytest.mark.asyncio
    async def test_valid_auth(self):
        """Test validation with valid cookie."""
        # Token endpoint returns only token data
        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = {
            "success": True,
            "token": {"access_token": "test_token", "expires_in": 3600},
        }

        # User endpoint returns profile info
        user_response = MagicMock()
        user_response.status_code = 200
        user_response.json.return_value = {
            "user": {
                "email": "test@example.com",
                "userId": 456,
                "personId": 789,
                "athletes": [{"athleteId": 123}],
            }
        }

        with patch("tp_mcp.auth.validator.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.side_effect = [token_response, user_response]
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await validate_auth("valid_cookie")

            assert result.is_valid is True
            assert result.status == AuthStatus.VALID
            assert result.athlete_id == 123
            assert result.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_valid_auth_coach_reports_own_athlete_id(self):
        """For a coach roster, report the coach's own athlete ID, not athletes[0]."""
        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = {
            "success": True,
            "token": {"access_token": "test_token", "expires_in": 3600},
        }

        user_response = MagicMock()
        user_response.status_code = 200
        user_response.json.return_value = {
            "user": {
                "email": "coach@example.com",
                "userId": 456,
                "personId": 789,
                "athletes": [
                    # First entry is a coached athlete, NOT the coach.
                    {
                        "athleteId": 111,
                        "email": "athlete@example.com",
                        "coachedBy": 789,
                    },
                    {"athleteId": 999, "email": "coach@example.com", "coachedBy": 789},
                ],
            }
        }

        with patch("tp_mcp.auth.validator.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.side_effect = [token_response, user_response]
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await validate_auth("valid_cookie")

            assert result.is_valid is True
            # Was 111 (athletes[0]) before the fix; now the coach's own 999.
            assert result.athlete_id == 999

    @pytest.mark.asyncio
    async def test_expired_auth(self):
        """Test validation with expired cookie."""
        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch("tp_mcp.auth.validator.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await validate_auth("expired_cookie")

            assert result.is_valid is False
            assert result.status == AuthStatus.EXPIRED

    @pytest.mark.asyncio
    async def test_invalid_auth(self):
        """Test validation with invalid cookie."""
        mock_response = MagicMock()
        mock_response.status_code = 403

        with patch("tp_mcp.auth.validator.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await validate_auth("invalid_cookie")

            assert result.is_valid is False
            assert result.status == AuthStatus.INVALID

    @pytest.mark.asyncio
    async def test_empty_cookie(self):
        """Test validation with empty cookie."""
        result = await validate_auth("")
        assert result.is_valid is False
        assert result.status == AuthStatus.NO_CREDENTIAL

    @pytest.mark.asyncio
    async def test_network_error(self):
        """Test validation with network error."""
        import httpx

        with patch("tp_mcp.auth.validator.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.side_effect = httpx.RequestError("Network error")
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await validate_auth("some_cookie")

            assert result.is_valid is False
            assert result.status == AuthStatus.NETWORK_ERROR
