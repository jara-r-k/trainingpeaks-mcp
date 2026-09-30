"""Self profile IDs must not silently become calendar athlete IDs."""

from unittest.mock import AsyncMock

import pytest

from tp_mcp.client.context import athlete_override
from tp_mcp.client.http import APIResponse, TPClient
from tp_mcp.tools.profile import tp_get_profile, tp_list_athletes

# Identity shape from the A1 brief and captured 1 October roster; dummy emails.
USER = {
    "personId": 1456247,
    "firstName": "Simon",
    "lastName": "Knowles",
    "email": "coach@example.test",
    "athletes": [
        {
            "athleteId": 2594040,
            "firstName": "sime",
            "lastName": "knowles",
            "email": "coach@example.test",
            "coachedBy": 1456247,
        },
        {
            "athleteId": 1653162,
            "firstName": "Simon",
            "lastName": "Knowles",
            "email": "other@example.test",
            "coachedBy": 1456247,
        },
    ],
}


@pytest.fixture
def profile_client(monkeypatch):
    monkeypatch.setattr(TPClient, "_cached_user_data", None)
    monkeypatch.setattr(TPClient, "_cached_athlete_id", None)
    monkeypatch.setattr(TPClient, "_ensure_client", AsyncMock())
    monkeypatch.setattr(
        TPClient,
        "get",
        AsyncMock(return_value=APIResponse(success=True, data={"user": USER})),
    )


@pytest.mark.parametrize("target", ["1456247", "9999999"])
async def test_explicit_profile_identity(profile_client, target):
    token = athlete_override.set(target)
    try:
        result = await tp_get_profile()
    finally:
        athlete_override.reset(token)
    if target == "1456247":
        assert result == {
            "athlete_id": 1456247,
            "name": "Simon Knowles",
            "email": "coach@example.test",
            "account_type": "basic",
        }
    else:
        assert result["error_code"] == "NOT_FOUND"


async def test_calendar_uses_roster_athlete_not_person_id(profile_client):
    roster = (await tp_list_athletes())["athletes"]
    assert [a["athlete_id"] for a in roster if a["is_self"]] == [2594040]
    for target, expected in [
        ("1456247", None),
        ("2594040", 2594040),
        ("1653162", 1653162),
    ]:
        token = athlete_override.set(target)
        try:
            assert await TPClient().ensure_athlete_id() == expected
        finally:
            athlete_override.reset(token)
