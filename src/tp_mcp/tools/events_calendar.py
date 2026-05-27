"""Calendar event tools: races, focus event, next event."""

import logging
from datetime import date as dt_date
from datetime import timedelta
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from tp_mcp.client import TPClient
from tp_mcp.tools._validation import (
    WorkoutIdInput,
    format_validation_error,
)

logger = logging.getLogger("tp-mcp")

DEFAULT_EVENT_RESULTS: list[dict[str, str]] = [
    {"resultType": "Division"},
    {"resultType": "Gender"},
    {"resultType": "Overall"},
]


def _default_create_event_payload(
    *,
    athlete_id: int,
    name: str,
    event_date_yyyy_mm_dd: str,
    event_type: str,
    atp_priority: str,
    distance_km: float | None,
    ctl_target: float | None,
    description: str | None,
) -> dict[str, Any]:
    """Build JSON body for POST .../event (v6 singular) per TrainingPeaks web app contract."""
    payload: dict[str, Any] = {
        "goals": {},
        "atpPriority": atp_priority,
        "legs": [],
        "eventDate": event_date_yyyy_mm_dd,
        "name": name,
        "personId": athlete_id,
        "eventType": event_type,
        "workouts": [],
        "results": [dict(r) for r in DEFAULT_EVENT_RESULTS],
    }
    if distance_km is not None:
        payload["distance"] = float(distance_km)
        payload["distanceUnits"] = "Kilometers"
    else:
        payload["distance"] = None
        payload["distanceUnits"] = None
    if ctl_target is not None:
        payload["ctlTarget"] = ctl_target
    if description:
        payload["description"] = description
    return payload


class CreateEventInput(BaseModel):
    """Validates input for event creation."""

    name: str = Field(min_length=1, max_length=200)
    date: str
    event_type: str | None = None
    priority: str | None = None
    distance_km: float | None = Field(default=None, ge=0)
    ctl_target: float | None = Field(default=None, ge=0)
    description: str | None = None

    @field_validator("date")
    @classmethod
    def check_date(cls, v: str) -> str:
        dt_date.fromisoformat(v)
        return v

    @field_validator("priority")
    @classmethod
    def check_priority(cls, v: str | None) -> str | None:
        if v is not None and v not in ("A", "B", "C"):
            raise ValueError("priority must be 'A', 'B', or 'C'")
        return v

    @field_validator("event_type")
    @classmethod
    def check_event_type(cls, v: str | None) -> str | None:
        return v


async def tp_get_focus_event() -> dict[str, Any]:
    """Get the A-priority focus event with goals and results."""
    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = f"/fitness/v6/athletes/{athlete_id}/events/focusevent"
        response = await client.get(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": (
                    response.error_code.value if response.error_code else "API_ERROR"
                ),
                "message": response.message,
            }

        if not response.data:
            return {"event": None, "message": "No focus event set."}

        return {"event": response.data}


async def tp_get_next_event() -> dict[str, Any]:
    """Get the nearest future planned event."""
    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = f"/fitness/v6/athletes/{athlete_id}/events/nextplannedevent"
        response = await client.get(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": (
                    response.error_code.value if response.error_code else "API_ERROR"
                ),
                "message": response.message,
            }

        if not response.data:
            return {"event": None, "message": "No upcoming events."}

        return {"event": response.data}


async def tp_get_events(start_date: str, end_date: str) -> dict[str, Any]:
    """List events in a date range.

    Args:
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD). Max 730 days span (±1 year typical).

    Returns:
        Dict with events list.
    """
    try:
        start = dt_date.fromisoformat(start_date)
        end = dt_date.fromisoformat(end_date)
    except ValueError as e:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": f"Invalid date: {e}",
        }
    if start > end:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "start_date must be before or equal to end_date",
        }
    if (end - start).days > 730:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "Date range too large. Maximum 730 days.",
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        start_str = start.isoformat()
        end_str = end.isoformat()
        endpoint = f"/fitness/v6/athletes/{athlete_id}/events/{start_str}/{end_str}"
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
            "events": data,
            "count": len(data),
            "date_range": {"start": start_date, "end": end_date},
        }


async def tp_create_event(
    name: str,
    date: str,
    event_type: str | None = None,
    priority: str | None = None,
    distance_km: float | None = None,
    ctl_target: float | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Create a race/event.

    Args:
        name: Event name.
        date: Event date (YYYY-MM-DD).
        event_type: Event type (e.g. 'RoadRunning', 'RunningTrack', 'Triathlon'); defaults to 'Other'.
        priority: Priority level ('A', 'B', or 'C'); defaults to 'C' if omitted.
        distance_km: Event distance in km (sent as distance + distanceUnits=Kilometers).
        ctl_target: Target CTL for the event.
        description: Optional description.

    Returns:
        Dict with created event details or error.
    """
    try:
        params = CreateEventInput(
            name=name,
            date=date,
            event_type=event_type,
            priority=priority,
            distance_km=distance_km,
            ctl_target=ctl_target,
            description=description,
        )
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

        event_type = params.event_type or "Other"
        atp_priority = params.priority or "C"
        payload = _default_create_event_payload(
            athlete_id=int(athlete_id),
            name=params.name,
            event_date_yyyy_mm_dd=params.date,
            event_type=event_type,
            atp_priority=atp_priority,
            distance_km=params.distance_km,
            ctl_target=params.ctl_target,
            description=params.description,
        )

        endpoint = f"/fitness/v6/athletes/{athlete_id}/event"
        response = await client.post(endpoint, json=payload)

        if response.is_error:
            return {
                "isError": True,
                "error_code": (
                    response.error_code.value if response.error_code else "API_ERROR"
                ),
                "message": response.message,
            }

        event_id = None
        if isinstance(response.data, dict):
            event_id = response.data.get("eventId", response.data.get("id"))

        return {
            "success": True,
            "event_id": event_id,
            "name": params.name,
            "date": params.date,
        }


async def tp_update_event(
    event_id: str,
    name: str | None = None,
    date: str | None = None,
    event_type: str | None = None,
    priority: str | None = None,
    distance_km: float | None = None,
    ctl_target: float | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Update an event (GET then PUT merge).

    Args:
        event_id: Event ID.
        name: Optional new name.
        date: Optional new date (YYYY-MM-DD).
        event_type: Optional event type.
        priority: Optional priority ('A', 'B', 'C').
        distance_km: Optional distance in km.
        ctl_target: Optional CTL target.
        description: Optional description.

    Returns:
        Dict with confirmation or error.
    """
    try:
        validated = WorkoutIdInput(workout_id=event_id)
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": msg,
        }

    if priority is not None and priority not in ("A", "B", "C"):
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "priority must be 'A', 'B', or 'C'.",
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        today = dt_date.today()
        search_start = (today - timedelta(days=730)).isoformat()
        search_end = (today + timedelta(days=730)).isoformat()
        search_endpoint = (
            f"/fitness/v6/athletes/{athlete_id}/events/{search_start}/{search_end}"
        )
        search_response = await client.get(search_endpoint)

        existing = None
        if search_response.success and isinstance(search_response.data, list):
            for evt in search_response.data:
                if evt.get("id") == validated.workout_id:
                    existing = evt
                    break

        if existing is None:
            return {
                "isError": True,
                "error_code": "NOT_FOUND",
                "message": f"Event {validated.workout_id} not found.",
            }

        existing["personId"] = athlete_id
        if name is not None:
            existing["name"] = name
        if date is not None:
            dt_date.fromisoformat(date)
            existing["eventDate"] = date
        if event_type is not None:
            existing["eventType"] = event_type
        if priority is not None:
            existing["atpPriority"] = priority
        if distance_km is not None:
            existing["distance"] = float(distance_km)
            existing["distanceUnits"] = "Kilometers"
        if ctl_target is not None:
            existing["ctlTarget"] = ctl_target
        if description is not None:
            existing["description"] = description

        endpoint = f"/fitness/v6/athletes/{athlete_id}/event"
        response = await client.put(endpoint, json=existing)

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
            "message": f"Event {validated.workout_id} updated.",
        }


async def tp_delete_event(event_id: str) -> dict[str, Any]:
    """Delete an event.

    Args:
        event_id: Event ID.

    Returns:
        Dict with confirmation or error.
    """
    try:
        validated = WorkoutIdInput(workout_id=event_id)
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

        endpoint = f"/fitness/v6/athletes/{athlete_id}/event/{validated.workout_id}"
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
            "message": f"Event {validated.workout_id} deleted.",
        }
