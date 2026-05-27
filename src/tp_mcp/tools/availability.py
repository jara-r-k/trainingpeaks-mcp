"""Availability tools."""

from typing import Any

from pydantic import ValidationError

from tp_mcp.client import TPClient
from tp_mcp.tools._validation import (
    DateRangeInput,
    WorkoutIdInput,
    format_validation_error,
)


async def tp_get_availability(start_date: str, end_date: str) -> dict[str, Any]:
    """Get availability entries for a date range.

    Args:
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).

    Returns:
        Dict with availability entries.
    """
    try:
        params = DateRangeInput(start_date=start_date, end_date=end_date)
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": msg,
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        start_str = params.start_date.isoformat()
        end_str = params.end_date.isoformat()
        endpoint = (
            f"/fitness/v1/athletes/{athlete_id}/availability/{start_str}/{end_str}"
        )
        response = await client.get(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": (
                    response.error_code.value if response.error_code else "API_ERROR"
                ),
                "message": response.message,
            }

        data = response.data if isinstance(response.data, list) else []
        return {
            "availability": data,
            "count": len(data),
        }


async def tp_create_availability(
    start_date: str,
    end_date: str,
    limited: bool = False,
    sport_types: list[str] | None = None,
) -> dict[str, Any]:
    """Mark dates as unavailable or limited.

    Args:
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).
        limited: If True, mark as limited (not fully unavailable).
        sport_types: If limited, list of available sport types.

    Returns:
        Dict with confirmation or error.
    """
    try:
        params = DateRangeInput(start_date=start_date, end_date=end_date)
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": msg,
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        payload: dict[str, Any] = {
            "athleteId": athlete_id,
            "startDate": f"{params.start_date.isoformat()}T00:00:00",
            "endDate": f"{params.end_date.isoformat()}T00:00:00",
            "limited": limited,
        }
        if limited and sport_types:
            payload["sportTypes"] = sport_types

        endpoint = f"/fitness/v1/athletes/{athlete_id}/availability"
        response = await client.post(endpoint, json=payload)

        if response.is_error:
            return {
                "isError": True,
                "error_code": (
                    response.error_code.value if response.error_code else "API_ERROR"
                ),
                "message": response.message,
            }

        avail_id = None
        if isinstance(response.data, dict):
            avail_id = response.data.get("availabilityId", response.data.get("id"))

        return {
            "success": True,
            "availability_id": avail_id,
            "start_date": start_date,
            "end_date": end_date,
            "limited": limited,
        }


async def tp_delete_availability(availability_id: str) -> dict[str, Any]:
    """Remove an availability entry.

    Args:
        availability_id: Availability entry ID.

    Returns:
        Dict with confirmation or error.
    """
    try:
        validated = WorkoutIdInput(workout_id=availability_id)
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": msg,
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = (
            f"/fitness/v1/athletes/{athlete_id}/availability/{validated.workout_id}"
        )
        response = await client.delete(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": (
                    response.error_code.value if response.error_code else "API_ERROR"
                ),
                "message": response.message,
            }

        return {
            "success": True,
            "message": f"Availability {validated.workout_id} deleted.",
        }
