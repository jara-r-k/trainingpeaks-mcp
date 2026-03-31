"""TOOL-06: tp_get_fitness - Get CTL/ATL/TSB fitness data.

Follows the prepare/compute pattern:
  - prepare_fitness_data() — fetches raw API data
  - compute_fitness_metrics() — rounding, status mapping, formatting
"""

import logging
from datetime import date, timedelta
from typing import Any

from pydantic import ValidationError

from tp_mcp.client import TPClient
from tp_mcp.tools._validation import FitnessInput, format_validation_error

logger = logging.getLogger("tp-mcp")


def _get_fitness_status(tsb: float) -> str:
    """Get human-readable fitness status from TSB."""
    if tsb > 25:
        return "Very Fresh (detraining risk)"
    elif tsb > 10:
        return "Fresh (race ready)"
    elif tsb > 0:
        return "Neutral (normal training)"
    elif tsb > -10:
        return "Tired (absorbing training)"
    elif tsb > -25:
        return "Very Tired (high fatigue)"
    else:
        return "Exhausted (overreaching risk)"


async def prepare_fitness_data(
    query_start: date,
    query_end: date,
    atl_constant: int = 7,
    ctl_constant: int = 42,
) -> dict[str, Any]:
    """Fetch raw fitness data from the TrainingPeaks API.

    This is the 'prepare' phase — handles auth, endpoint construction,
    and API communication. Returns raw data or an error dict.

    Args:
        query_start: Start date for the query.
        query_end: End date for the query.
        atl_constant: ATL decay constant in days.
        ctl_constant: CTL decay constant in days.

    Returns:
        Dict with either 'raw_data' (list) or error fields.
    """
    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return {
                "isError": True,
                "error_code": "AUTH_INVALID",
                "message": "Could not get athlete ID. Re-authenticate.",
            }

        base = f"/fitness/v1/athletes/{athlete_id}/reporting/performancedata"
        endpoint = f"{base}/{query_start}/{query_end}"
        body = {
            "atlConstant": atl_constant,
            "atlStart": 0,
            "ctlConstant": ctl_constant,
            "ctlStart": 0,
            "workoutTypes": [],
        }

        response = await client.post(endpoint, json=body)

        if response.is_error:
            return {
                "isError": True,
                "error_code": response.error_code.value if response.error_code else "API_ERROR",
                "message": response.message,
            }

        return {"raw_data": response.data or []}


def compute_fitness_metrics(
    raw_data: list[dict[str, Any]],
    query_start: date,
    query_end: date,
    query_days: int,
) -> dict[str, Any]:
    """Transform raw fitness data into formatted output.

    This is the 'compute' phase — pure data transformation with no
    network calls. Handles rounding, status mapping, and formatting.

    Args:
        raw_data: Raw API response entries.
        query_start: Start date for the query.
        query_end: End date for the query.
        query_days: Number of days in the query range.

    Returns:
        Dict with daily_data, current fitness summary, and metadata.
    """
    if not raw_data:
        return {
            "start_date": str(query_start),
            "end_date": str(query_end),
            "days": query_days,
            "data": [],
            "current": None,
        }

    daily_data = []
    for entry in raw_data:
        daily_data.append(
            {
                "date": entry.get("workoutDay", "").split("T")[0],
                "tss": entry.get("tssActual", 0),
                "ctl": round(entry.get("ctl", 0), 1),
                "atl": round(entry.get("atl", 0), 1),
                "tsb": round(entry.get("tsb", 0), 1),
            }
        )

    current = None
    if daily_data:
        latest = daily_data[-1]
        current = {
            "ctl": latest["ctl"],
            "atl": latest["atl"],
            "tsb": latest["tsb"],
            "fitness_status": _get_fitness_status(latest["tsb"]),
        }

    return {
        "start_date": str(query_start),
        "end_date": str(query_end),
        "days": query_days,
        "current": current,
        "daily_data": daily_data,
    }


async def tp_get_fitness(
    days: int = 90,
    start_date: str | None = None,
    end_date: str | None = None,
    atl_constant: int = 7,
    ctl_constant: int = 42,
) -> dict[str, Any]:
    """Get fitness/fatigue/form data (CTL/ATL/TSB).

    Args:
        days: Days of history (default 90). Ignored if start_date/end_date provided.
        start_date: Optional start date (YYYY-MM-DD) for historical queries.
        end_date: Optional end date (YYYY-MM-DD) for historical queries.
        atl_constant: ATL decay constant in days (default 7)
        ctl_constant: CTL decay constant in days (default 42)

    Returns:
        Dict with daily CTL, ATL, TSB values and current fitness summary.
    """
    try:
        params = FitnessInput(days=days, start_date=start_date, end_date=end_date)
    except (ValidationError, ValueError) as e:
        msg = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        return {
            "isError": True,
            "error_code": "VALIDATION_ERROR",
            "message": msg,
        }

    if params.start_date and params.end_date:
        query_start = params.start_date
        query_end = params.end_date
        query_days = (query_end - query_start).days
    else:
        query_end = date.today()
        query_start = query_end - timedelta(days=params.days)
        query_days = params.days

    # Prepare: fetch raw data
    prepared = await prepare_fitness_data(
        query_start, query_end, atl_constant, ctl_constant
    )

    if prepared.get("isError"):
        return prepared

    # Compute: transform raw data
    try:
        return compute_fitness_metrics(
            raw_data=prepared["raw_data"],
            query_start=query_start,
            query_end=query_end,
            query_days=query_days,
        )
    except Exception:
        logger.exception("Failed to parse fitness data")
        return {
            "isError": True,
            "error_code": "API_ERROR",
            "message": "Failed to parse fitness data.",
        }
