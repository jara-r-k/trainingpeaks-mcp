"""Calendar note tools."""

import logging
from datetime import date as dt_date
from typing import Any

from pydantic import ValidationError

from tp_mcp.client import TPClient
from tp_mcp.tools._validation import (
    WorkoutIdInput,
    format_validation_error,
)

logger = logging.getLogger("tp-mcp")


async def tp_create_note(
    date: str,
    title: str,
    description: str | None = None,
) -> dict[str, Any]:
    """Create a calendar note.

    Args:
        date: Note date (YYYY-MM-DD).
        title: Note title.
        description: Optional note description.

    Returns:
        Dict with confirmation or error.
    """
    try:
        dt_date.fromisoformat(date)
    except ValueError:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": f"Invalid date: {date}",
        }

    if not title or not title.strip():
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "Title must not be empty.",
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
            "noteDate": f"{date}T00:00:00",
            "title": title.strip(),
        }
        if description:
            payload["description"] = description

        endpoint = f"/fitness/v1/athletes/{athlete_id}/calendarNote"
        response = await client.post(endpoint, json=payload)

        if response.is_error:
            return {
                "isError": True,
                "error_code": (
                    response.error_code.value if response.error_code else "API_ERROR"
                ),
                "message": response.message,
            }

        note_id = None
        if isinstance(response.data, dict):
            note_id = response.data.get("calendarNoteId", response.data.get("id"))

        return {
            "success": True,
            "note_id": note_id,
            "title": title,
            "date": date,
        }


async def tp_delete_note(note_id: str) -> dict[str, Any]:
    """Delete a calendar note.

    Args:
        note_id: Note ID.

    Returns:
        Dict with confirmation or error.
    """
    try:
        validated = WorkoutIdInput(workout_id=note_id)
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
            f"/fitness/v1/athletes/{athlete_id}/calendarNote/{validated.workout_id}"
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
            "message": f"Note {validated.workout_id} deleted.",
        }


async def tp_get_note(note_id: str) -> dict[str, Any]:
    """Get a calendar note by ID.

    Args:
        note_id: Note ID.

    Returns:
        Dict with note fields or error.
    """
    try:
        validated = WorkoutIdInput(workout_id=note_id)
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {"isError": True, "error_code": "VALIDATION_ERROR", "message": msg}

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = (
            f"/fitness/v1/athletes/{athlete_id}/calendarNote/{validated.workout_id}"
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

        d = response.data or {}
        note_date_str = d.get("noteDate", "")
        if note_date_str and "T" in note_date_str:
            note_date_str = note_date_str.split("T")[0]

        return {
            "note": {
                "id": d.get("id"),
                "title": d.get("title"),
                "description": d.get("description"),
                "date": note_date_str,
                "is_hidden": d.get("isHidden", False),
                "created_date": d.get("createdDate"),
                "modified_date": d.get("modifiedDate"),
            }
        }


async def tp_update_note(
    note_id: str,
    title: str | None = None,
    description: str | None = None,
    date: str | None = None,
    is_hidden: bool | None = None,
) -> dict[str, Any]:
    """Update a calendar note.

    Args:
        note_id: Note ID.
        title: New title (optional).
        description: New description (optional).
        date: New note date YYYY-MM-DD (optional).
        is_hidden: Set visibility (optional).

    Returns:
        Dict with updated note or error.
    """
    if title is None and description is None and date is None and is_hidden is None:
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "Provide at least one field to update (title, description, date, is_hidden).",
        }

    if title is not None and not title.strip():
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "Title must not be empty.",
        }

    try:
        validated = WorkoutIdInput(workout_id=note_id)
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {"isError": True, "error_code": "VALIDATION_ERROR", "message": msg}

    if date is not None:
        try:
            dt_date.fromisoformat(date)
        except ValueError:
            return {
                "isError": True,
                "error_code": "VALIDATION_ERROR",
                "message": f"Invalid date: {date}",
            }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        get_endpoint = (
            f"/fitness/v1/athletes/{athlete_id}/calendarNote/{validated.workout_id}"
        )
        get_response = await client.get(get_endpoint)
        if get_response.is_error:
            return {
                "isError": True,
                "error_code": (
                    get_response.error_code.value
                    if get_response.error_code
                    else "API_ERROR"
                ),
                "message": get_response.message,
            }

        payload: dict[str, Any] = dict(get_response.data or {})
        if title is not None:
            payload["title"] = title.strip()
        if description is not None:
            payload["description"] = description
        if date is not None:
            payload["noteDate"] = f"{date}T00:00:00"
        if is_hidden is not None:
            payload["isHidden"] = is_hidden

        put_response = await client.put(get_endpoint, json=payload)
        if put_response.is_error:
            return {
                "isError": True,
                "error_code": (
                    put_response.error_code.value
                    if put_response.error_code
                    else "API_ERROR"
                ),
                "message": put_response.message,
            }

        d = put_response.data or {}
        note_date_str = d.get("noteDate", "")
        if note_date_str and "T" in note_date_str:
            note_date_str = note_date_str.split("T")[0]

        return {
            "success": True,
            "note": {
                "id": d.get("id"),
                "title": d.get("title"),
                "description": d.get("description"),
                "date": note_date_str,
                "is_hidden": d.get("isHidden", False),
                "modified_date": d.get("modifiedDate"),
            },
        }


async def tp_get_notes(start_date: str, end_date: str) -> dict[str, Any]:
    """List calendar notes in a date range.

    Args:
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD). Max 730 days span (±1 year typical).

    Returns:
        Dict with notes list (hidden notes filtered out), count, and date range.
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
        endpoint = (
            f"/fitness/v1/athletes/{athlete_id}/calendarNotes/{start_str}/{end_str}"
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

        raw_notes: list[dict[str, Any]] = (
            response.data if isinstance(response.data, list) else []
        )
        notes: list[dict[str, Any]] = []
        for n in raw_notes:
            if n.get("isHidden"):
                continue
            note_date_str = n.get("noteDate", "")
            if note_date_str and "T" in note_date_str:
                note_date_str = note_date_str.split("T")[0]
            notes.append(
                {
                    "id": n.get("id"),
                    "title": n.get("title"),
                    "description": n.get("description"),
                    "date": note_date_str,
                    "is_hidden": n.get("isHidden", False),
                    "created_date": n.get("createdDate"),
                    "modified_date": n.get("modifiedDate"),
                }
            )
        return {
            "notes": notes,
            "count": len(notes),
            "date_range": {"start": start_date, "end": end_date},
        }


async def tp_get_note_comments(note_id: str) -> dict[str, Any]:
    """Get comments for a calendar note.

    Args:
        note_id: Note ID.

    Returns:
        Dict with comments list and count, or error.
    """
    try:
        validated = WorkoutIdInput(workout_id=note_id)
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {"isError": True, "error_code": "VALIDATION_ERROR", "message": msg}

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = f"/fitness/v1/athletes/{athlete_id}/calendarNote/{validated.workout_id}/comments"
        response = await client.get(endpoint)

        if response.is_error:
            return {
                "isError": True,
                "error_code": (
                    response.error_code.value if response.error_code else "API_ERROR"
                ),
                "message": response.message,
            }

        raw_comments: list[dict[str, Any]] = (
            response.data if isinstance(response.data, list) else []
        )
        comments = [
            {
                "id": c.get("calendarNoteCommentStreamId"),
                "comment": c.get("comment"),
                "commenter": f"{c.get('firstName', '')} {c.get('lastName', '')}".strip(),
                "created_at": c.get("createdDateTimeUtc"),
            }
            for c in raw_comments
        ]
        return {"comments": comments, "count": len(comments)}


async def tp_add_note_comment(note_id: str, comment: str) -> dict[str, Any]:
    """Add a comment to a calendar note.

    Args:
        note_id: Note ID.
        comment: Comment text.

    Returns:
        Dict with success confirmation or error.
    """
    try:
        validated = WorkoutIdInput(workout_id=note_id)
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {"isError": True, "error_code": "VALIDATION_ERROR", "message": msg}

    if not comment or not comment.strip():
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": "Comment must not be empty.",
        }

    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        endpoint = f"/fitness/v1/athletes/{athlete_id}/calendarNote/{validated.workout_id}/comment"
        response = await client.put(endpoint, json={"Comment": comment.strip()})

        if response.is_error:
            return {
                "isError": True,
                "error_code": (
                    response.error_code.value if response.error_code else "API_ERROR"
                ),
                "message": response.message,
            }

        return {"success": True, "note_id": validated.workout_id}
