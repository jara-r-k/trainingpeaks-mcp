"""Tests for tp_get_notes — list calendar notes in a date range."""

from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.http import APIResponse, ErrorCode
from tp_mcp.tools.events import tp_get_notes


def _client_patch(response: APIResponse, athlete_id: int = 123):
    """Helper: build a patched TPClient context manager returning `response` on GET."""
    mock_instance = AsyncMock()
    mock_instance.ensure_athlete_id = AsyncMock(return_value=athlete_id)
    mock_instance.get = AsyncMock(return_value=response)
    return mock_instance


class TestGetNotes:
    @pytest.mark.asyncio
    async def test_happy_path_returns_notes(self):
        raw = [
            {
                "id": 1,
                "title": "Goal: sub-10 IM",
                "description": "Working towards sub-10 at IM Cairns",
                "noteDate": "2026-06-01T00:00:00",
                "isHidden": False,
                "createdDate": "2026-05-01T10:00:00",
                "modifiedDate": "2026-05-10T10:00:00",
            },
            {
                "id": 2,
                "title": "B-race: Gold Coast 70.3",
                "description": "Tune-up race for IM Cairns",
                "noteDate": "2026-04-15T00:00:00",
                "isHidden": False,
            },
        ]
        response = APIResponse(success=True, data=raw)
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = _client_patch(response)
            result = await tp_get_notes("2026-01-01", "2026-12-31")

        assert result["count"] == 2
        assert result["notes"][0]["id"] == 1
        assert result["notes"][0]["title"] == "Goal: sub-10 IM"
        assert result["notes"][0]["date"] == "2026-06-01"
        assert result["notes"][1]["date"] == "2026-04-15"
        assert result["date_range"] == {"start": "2026-01-01", "end": "2026-12-31"}

    @pytest.mark.asyncio
    async def test_hidden_notes_filtered(self):
        raw = [
            {
                "id": 1,
                "title": "Visible",
                "noteDate": "2026-06-01T00:00:00",
                "isHidden": False,
            },
            {
                "id": 2,
                "title": "Hidden",
                "noteDate": "2026-06-02T00:00:00",
                "isHidden": True,
            },
            {
                "id": 3,
                "title": "Visible 2",
                "noteDate": "2026-06-03T00:00:00",
                "isHidden": False,
            },
        ]
        response = APIResponse(success=True, data=raw)
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = _client_patch(response)
            result = await tp_get_notes("2026-06-01", "2026-06-30")

        assert result["count"] == 2
        ids = [n["id"] for n in result["notes"]]
        assert 2 not in ids

    @pytest.mark.asyncio
    async def test_empty_range(self):
        response = APIResponse(success=True, data=[])
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = _client_patch(response)
            result = await tp_get_notes("2026-06-01", "2026-06-30")

        assert result["count"] == 0
        assert result["notes"] == []

    @pytest.mark.asyncio
    async def test_api_error_propagates(self):
        response = APIResponse(
            success=False, error_code=ErrorCode.API_ERROR, message="upstream 500"
        )
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = _client_patch(response)
            result = await tp_get_notes("2026-06-01", "2026-06-30")

        assert result["isError"] is True
        assert result["message"] == "upstream 500"

    @pytest.mark.asyncio
    async def test_invalid_date_returns_validation_error(self):
        result = await tp_get_notes("not-a-date", "2026-06-30")
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_end_before_start_returns_validation_error(self):
        result = await tp_get_notes("2026-12-31", "2026-01-01")
        assert result["isError"] is True
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_no_athlete_id_returns_auth_error(self):
        mock_instance = AsyncMock()
        mock_instance.ensure_athlete_id = AsyncMock(return_value=None)
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_instance
            result = await tp_get_notes("2026-01-01", "2026-12-31")

        assert result["isError"] is True
        assert result["error_code"] == "AUTH_INVALID"

    @pytest.mark.asyncio
    async def test_date_without_time_component(self):
        raw = [{"id": 1, "title": "No T", "noteDate": "2026-06-01", "isHidden": False}]
        response = APIResponse(success=True, data=raw)
        with patch("tp_mcp.tools.events.TPClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = _client_patch(response)
            result = await tp_get_notes("2026-06-01", "2026-06-30")

        assert result["notes"][0]["date"] == "2026-06-01"
