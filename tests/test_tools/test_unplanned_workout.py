"""Offline contract tests for opt-in figureless cards."""

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from tp_mcp.client.http import APIResponse
from tp_mcp.tools._validation import CreateWorkoutInput
from tp_mcp.tools.workouts import tp_create_workout


@pytest.mark.asyncio
async def test_unplanned_opt_in_posts_exact_note_body():
    with patch("tp_mcp.tools.workouts.TPClient") as client:
        instance = AsyncMock()
        instance.ensure_athlete_id.return_value = 900001
        instance.post.return_value = APIResponse(success=True, data={"workoutId": 800001})
        client.return_value.__aenter__.return_value = instance
        result = await tp_create_workout(
            date_str="2026-11-02", sport="Crosstrain", title="Synthetic note",
            description="Synthetic instructions.", is_hidden=True, allow_unplanned=True,
        )
    assert result["success"] is True
    instance.post.assert_awaited_once_with("/fitness/v6/athletes/900001/workouts", json={
        "athleteId": 900001, "workoutDay": "2026-11-02T00:00:00",
        "workoutTypeFamilyId": 5, "workoutTypeValueId": 5,
        "title": "Synthetic note", "description": "Synthetic instructions.", "isHidden": True,
    })


@pytest.mark.asyncio
@pytest.mark.parametrize("extra", [{}, {"allow_unplanned": False}, {"allow_unplanned": True, "sport": "Bike"},
                                   {"allow_unplanned": True, "is_hidden": False}])
async def test_default_or_wrong_shape_refused_before_client(extra):
    with patch("tp_mcp.tools.workouts.TPClient") as client:
        result = await tp_create_workout(**{
            "date_str": "2026-11-02", "sport": "Crosstrain", "title": "Synthetic note",
            "description": "Synthetic instructions.", "is_hidden": True, **extra,
        })
        client.assert_not_called()
    assert result["error_code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("extra", [
    {"duration_minutes": 30}, {"distance_km": 1}, {"tss_planned": 10},
    {"structure": {}}, {"structured_workout": {}}, {"subtype_id": 1},
    {"tags": "tag"}, {"feeling": 2}, {"rpe": 2}, {"allow_unplanned": "true"},
])
def test_unplanned_is_a_narrow_opt_in(extra):
    with pytest.raises(ValidationError):
        CreateWorkoutInput(**{
            "date": "2026-11-02", "sport": "Crosstrain", "title": "Synthetic note",
            "is_hidden": True, "allow_unplanned": True, **extra,
        })
