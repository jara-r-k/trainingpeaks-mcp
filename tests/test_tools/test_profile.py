"""Tests for tp_get_profile / tp_list_athletes — including coach athlete targeting."""

from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.context import athlete_override
from tp_mcp.client.http import APIResponse, TPClient
from tp_mcp.tools.profile import tp_get_profile, tp_list_athletes

# Coach account payload as returned (nested) by /users/v3/user.
# The coach's own athlete entry is athleteId 100; two coached athletes follow.
COACH_PAYLOAD = {
    "user": {
        "personId": 900,
        "userId": 950,
        "firstName": "Stevan",
        "lastName": "Coach",
        "fullName": "Stevan Coach",
        "email": "stevan@example.com",
        "settings": {"account": {"isPremium": True}},
        "athletes": [
            {
                "athleteId": 100,
                "firstName": "Stevan",
                "lastName": "Coach",
                "email": "stevan@example.com",
                "coachedBy": 900,
                "userType": 6,
            },
            {
                "athleteId": 201,
                "firstName": "Charlotte",
                "lastName": "Horton",
                "email": "charlotte@example.com",
                "coachedBy": 900,
                "userType": 1,
            },
        ],
    }
}


@pytest.fixture(autouse=True)
def _clear_caches():
    """Reset class-level caches between tests (mirrors test_coach_support)."""
    TPClient._cached_athlete_id = None
    TPClient._cached_user_data = None
    yield
    TPClient._cached_athlete_id = None
    TPClient._cached_user_data = None


def _patch_client():
    """Patch TPClient in profile.py.

    `get` returns the coach payload; `ensure_athlete_id` runs the REAL
    resolution logic against the same payload so the athlete override is
    genuinely threaded through, not stubbed to a fixed answer.
    """
    real_ensure = TPClient.ensure_athlete_id

    patcher = patch("tp_mcp.tools.profile.TPClient")
    mock_client = patcher.start()

    mock_instance = AsyncMock()
    mock_instance.get = AsyncMock(
        return_value=APIResponse(success=True, data=COACH_PAYLOAD)
    )
    # Real resolution, but its user-data source is the mocked payload.
    mock_instance._athlete_id = None
    mock_instance._get_user_data = AsyncMock(return_value=COACH_PAYLOAD["user"])

    async def _ensure():
        return await real_ensure(mock_instance)

    mock_instance.ensure_athlete_id = _ensure
    mock_client.return_value.__aenter__.return_value = mock_instance
    return patcher, mock_instance


class TestGetProfileSelf:
    """No athlete override → coach's own profile (unchanged behaviour)."""

    @pytest.mark.asyncio
    async def test_returns_coach_profile(self):
        patcher, _ = _patch_client()
        try:
            result = await tp_get_profile()
        finally:
            patcher.stop()

        assert result.get("isError") is not True
        # personId is the coach's own identity used for self profile
        assert result["athlete_id"] == 900
        assert result["name"] == "Stevan Coach"
        assert result["email"] == "stevan@example.com"
        assert result["account_type"] == "premium"


class TestGetProfileAthleteOverride:
    """Athlete override set → THAT athlete's profile, not the coach's."""

    @pytest.mark.asyncio
    async def test_honours_athlete_by_name(self):
        patcher, _ = _patch_client()
        token = athlete_override.set("Charlotte Horton")
        try:
            result = await tp_get_profile()
        finally:
            athlete_override.reset(token)
            patcher.stop()

        assert result.get("isError") is not True
        # The bug: this used to return the coach (Stevan / 900). Now it must
        # return Charlotte's athlete entry.
        assert result["athlete_id"] == 201
        assert result["name"] == "Charlotte Horton"
        assert result["email"] == "charlotte@example.com"

    @pytest.mark.asyncio
    async def test_honours_athlete_by_id(self):
        patcher, _ = _patch_client()
        token = athlete_override.set("201")
        try:
            result = await tp_get_profile()
        finally:
            athlete_override.reset(token)
            patcher.stop()

        assert result.get("isError") is not True
        assert result["athlete_id"] == 201
        assert result["name"] == "Charlotte Horton"

    @pytest.mark.asyncio
    async def test_unknown_athlete_returns_not_found(self):
        patcher, _ = _patch_client()
        token = athlete_override.set("Nobody Here")
        try:
            result = await tp_get_profile()
        finally:
            athlete_override.reset(token)
            patcher.stop()

        assert result.get("isError") is True
        assert result["error_code"] == "NOT_FOUND"


class TestListAthletes:
    @pytest.mark.asyncio
    async def test_flags_coach_own_entry(self):
        client = AsyncMock()
        client._get_user_data = AsyncMock(return_value=COACH_PAYLOAD["user"])
        with patch("tp_mcp.tools.profile.TPClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = client
            result = await tp_list_athletes()

        athletes = {a["athlete_id"]: a for a in result["athletes"]}
        assert athletes[100]["is_self"] is True
        assert athletes[201]["is_self"] is False

    @pytest.mark.asyncio
    async def test_includes_user_type(self):
        """user_type is carried through from the /users/v3/user athlete entry
        so the coach roster premium filter (userType in {1, 4}) can run off the
        list without a per-athlete settings call (PRO-155)."""
        client = AsyncMock()
        client._get_user_data = AsyncMock(return_value=COACH_PAYLOAD["user"])
        with patch("tp_mcp.tools.profile.TPClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = client
            result = await tp_list_athletes()

        athletes = {a["athlete_id"]: a for a in result["athletes"]}
        assert athletes[201]["user_type"] == 1  # premium (coach-paid)
        assert athletes[100]["user_type"] == 6  # coach's own basic entry

    @pytest.mark.asyncio
    async def test_user_type_is_none_when_absent(self):
        """A TP tier that omits userType must surface user_type=None, not raise
        or invent a value — the premium filter then excludes it (matches the
        cron's `typeof user_type === 'number'` guard)."""
        payload = {
            "personId": 900,
            "email": "stevan@example.com",
            "athletes": [
                {
                    "athleteId": 300,
                    "firstName": "No",
                    "lastName": "Type",
                    "email": "notype@example.com",
                    "coachedBy": 900,
                    # no userType key
                },
            ],
        }
        client = AsyncMock()
        client._get_user_data = AsyncMock(return_value=payload)
        with patch("tp_mcp.tools.profile.TPClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = client
            result = await tp_list_athletes()

        (entry,) = result["athletes"]
        assert entry["athlete_id"] == 300
        assert entry["user_type"] is None
