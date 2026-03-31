"""Tests for prepare/compute splits in fitness and workout analysis tools."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.http import APIResponse
from tp_mcp.tools.fitness import (
    _get_fitness_status,
    compute_fitness_metrics,
    prepare_fitness_data,
)


class TestComputeFitnessMetrics:
    """Tests for the compute phase of fitness data processing."""

    def test_empty_data(self):
        result = compute_fitness_metrics(
            raw_data=[],
            query_start=date(2025, 1, 1),
            query_end=date(2025, 1, 31),
            query_days=30,
        )
        assert result["data"] == []
        assert result["current"] is None
        assert result["days"] == 30

    def test_single_entry(self):
        raw = [
            {"workoutDay": "2025-01-08T00:00:00", "tssActual": 80, "ctl": 46.123, "atl": 60.345, "tsb": -14.222}
        ]
        result = compute_fitness_metrics(
            raw_data=raw,
            query_start=date(2025, 1, 1),
            query_end=date(2025, 1, 8),
            query_days=7,
        )
        assert len(result["daily_data"]) == 1
        assert result["daily_data"][0]["ctl"] == 46.1
        assert result["daily_data"][0]["atl"] == 60.3
        assert result["daily_data"][0]["tsb"] == -14.2
        assert result["daily_data"][0]["date"] == "2025-01-08"
        assert result["current"]["fitness_status"] == "Very Tired (high fatigue)"

    def test_multiple_entries_latest_is_current(self):
        raw = [
            {"workoutDay": "2025-01-07T00:00:00", "tssActual": 50, "ctl": 45.0, "atl": 55.0, "tsb": -10.0},
            {"workoutDay": "2025-01-08T00:00:00", "tssActual": 0, "ctl": 44.0, "atl": 48.0, "tsb": 15.0},
        ]
        result = compute_fitness_metrics(
            raw_data=raw,
            query_start=date(2025, 1, 7),
            query_end=date(2025, 1, 8),
            query_days=1,
        )
        assert result["current"]["tsb"] == 15.0
        assert "Fresh" in result["current"]["fitness_status"]

    def test_rounding(self):
        raw = [
            {"workoutDay": "2025-01-01T00:00:00", "tssActual": 0, "ctl": 45.6789, "atl": 60.1234, "tsb": -14.4456}
        ]
        result = compute_fitness_metrics(
            raw_data=raw,
            query_start=date(2025, 1, 1),
            query_end=date(2025, 1, 1),
            query_days=0,
        )
        assert result["daily_data"][0]["ctl"] == 45.7
        assert result["daily_data"][0]["atl"] == 60.1
        assert result["daily_data"][0]["tsb"] == -14.4


class TestPrepareFitnessData:
    """Tests for the prepare phase of fitness data fetching."""

    @pytest.mark.asyncio
    async def test_auth_failure(self):
        with patch("tp_mcp.tools.fitness.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=None)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await prepare_fitness_data(date(2025, 1, 1), date(2025, 1, 31))

        assert result["isError"] is True
        assert result["error_code"] == "AUTH_INVALID"

    @pytest.mark.asyncio
    async def test_success(self):
        raw = [{"workoutDay": "2025-01-01T00:00:00", "ctl": 45, "atl": 50, "tsb": -5}]
        with patch("tp_mcp.tools.fitness.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=APIResponse(success=True, data=raw))
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await prepare_fitness_data(date(2025, 1, 1), date(2025, 1, 31))

        assert "isError" not in result
        assert result["raw_data"] == raw

    @pytest.mark.asyncio
    async def test_api_error(self):
        from tp_mcp.client.http import ErrorCode

        with patch("tp_mcp.tools.fitness.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(
                return_value=APIResponse(success=False, error_code=ErrorCode.NETWORK_ERROR, message="Timeout")
            )
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await prepare_fitness_data(date(2025, 1, 1), date(2025, 1, 31))

        assert result["isError"] is True
        assert result["error_code"] == "NETWORK_ERROR"


class TestAnalyseWorkoutSplit:
    """Tests for the prepare/compute split in workout analysis."""

    def test_analyse_workout_compute(self):
        """Test the compute phase with mock analysis data."""
        from tp_mcp.tools.analyze import analyse_workout

        raw_data = {
            "workoutId": 1001,
            "startTimestamp": "2025-01-08T06:00:00",
            "stopTimestamp": "2025-01-08T07:00:00",
            "totals": [{"name": "Duration", "value": 3600, "unit": "s"}],
            "dataElements": [
                {
                    "identifier": "power",
                    "name": "Power",
                    "unit": "W",
                    "min": 50.0,
                    "max": 400.0,
                    "average": 200.0,
                }
            ],
            "data": [{"power": 200, "hr": 145}],
            "lapData": [],
            "lapColumns": [],
        }

        result = analyse_workout(raw_data, 1001)

        assert result["workoutId"] == 1001
        assert "Duration" in result["totals"]
        assert len(result["dataChannels"]) == 1
        assert result["dataChannels"][0]["name"] == "Power"
        assert result["time_series_points"] == 1
        assert "data_file" in result

    @pytest.mark.asyncio
    async def test_prepare_workout_auth_failure(self):
        """Test prepare phase returns error on auth failure."""
        from tp_mcp.tools.analyze import prepare_workout

        with patch("tp_mcp.tools.analyze.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=None)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await prepare_workout(1001)

        assert result["isError"] is True
        assert result["error_code"] == "AUTH_INVALID"
