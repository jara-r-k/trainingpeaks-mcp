"""Create sends a TP-captured card unchanged: a native structure without
primaryIntensityTargetOrRange, and a planned time that is not whole minutes.

Fixture ``tp_captured_structure.json`` holds real TrainingPeaks GET data: the native
structure of a coach's card exactly as TP returned it, and the stored decimal hours of
four cards whose planned time is derived from their structure (72.4, 81.25, 46.37 and
47.62 minutes).
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.http import APIResponse
from tp_mcp.tools.workouts import tp_create_workout

CAPTURED = json.loads(
    (Path(__file__).parent / "tp_captured_structure.json").read_text()
)
STRUCTURE = CAPTURED["structure"]


async def create(**kwargs) -> tuple[dict, dict | None]:
    """Run tp_create_workout against a mocked client; return (result, POST body)."""
    response = APIResponse(
        success=True,
        data={"workoutId": 9001, "title": "x", "workoutDay": "2026-10-14T00:00:00"},
    )
    with patch("tp_mcp.tools.workouts.TPClient") as client:
        instance = AsyncMock()
        instance.ensure_athlete_id = AsyncMock(return_value=2594040)
        instance.post = AsyncMock(return_value=response)
        client.return_value.__aenter__.return_value = instance
        result = await tp_create_workout(
            date_str="2026-10-14", sport="Run", title="Track", **kwargs
        )
    body = instance.post.call_args[1]["json"] if instance.post.call_args else None
    return result, body


def test_captured_structure_lacks_the_key():
    assert "primaryIntensityTargetOrRange" not in STRUCTURE
    assert {
        "structure",
        "polyline",
        "primaryLengthMetric",
        "primaryIntensityMetric",
    } <= STRUCTURE.keys()


@pytest.mark.asyncio
async def test_structure_without_target_or_range_is_sent_verbatim():
    result, body = await create(structured_workout=STRUCTURE)
    assert result["success"] is True
    assert body["structure"] == json.dumps(
        STRUCTURE
    )  # nothing added, dropped or reordered
    assert "primaryIntensityTargetOrRange" not in json.loads(body["structure"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "missing",
    ["structure", "polyline", "primaryLengthMetric", "primaryIntensityMetric"],
)
async def test_the_other_four_keys_stay_required(missing):
    broken = {k: v for k, v in STRUCTURE.items() if k != missing}
    result, body = await create(structured_workout=broken)
    assert result["isError"] is True and body is None
    assert missing in result["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize("card, hours", sorted(CAPTURED["totalTimePlanned"].items()))
async def test_fractional_minutes_send_tps_stored_hours(card, hours):
    minutes = hours * 60
    assert not float(minutes).is_integer(), card
    result, body = await create(duration_minutes=minutes, structured_workout=STRUCTURE)
    assert result["success"] is True
    assert (
        body["totalTimePlanned"] == minutes / 60.0 == hours
    )  # exactly TP's stored value


@pytest.mark.asyncio
@pytest.mark.parametrize("minutes", [0, -5, 1440.5])
async def test_duration_bounds_still_hold(minutes):
    result, body = await create(duration_minutes=minutes)
    assert result["isError"] is True and body is None
    assert result["error_code"] == "VALIDATION_ERROR"
