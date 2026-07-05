"""TOOL-02: tp_get_profile / tp_list_athletes - Profile and coach tools."""

import logging
from typing import Any

from tp_mcp.client import TPClient

logger = logging.getLogger("tp-mcp")


def _profile_from_athlete_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Build a profile response from a coach roster athlete entry.

    The /users/v3/user payload is always coach-scoped, but its `athletes`
    array carries per-athlete identity. When a coach targets an athlete,
    read that athlete's fields instead of the coach's account fields.
    """
    first = entry.get("firstName", "")
    last = entry.get("lastName", "")
    name = entry.get("fullName") or f"{first} {last}".strip()
    return {
        "athlete_id": entry.get("athleteId"),
        "name": name,
        "email": entry.get("email"),
        # Account type is a coach-account attribute, not carried per athlete.
        "account_type": None,
    }


async def tp_get_profile() -> dict[str, Any]:
    """Get TrainingPeaks athlete profile.

    Without an athlete override, returns the authenticated coach's own
    profile. When a coach targets an athlete (via the injected `athlete`
    parameter), returns that athlete's profile from the coach roster.

    Returns:
        Dict with athlete_id, name, email, and account_type.
    """
    from tp_mcp.client.context import athlete_override

    async with TPClient() as client:
        response = await client.get("/users/v3/user")

        if response.is_error:
            return {
                "isError": True,
                "error_code": (
                    response.error_code.value if response.error_code else "API_ERROR"
                ),
                "message": response.message,
            }

        if not response.data:
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": "Empty response from API",
            }

        try:
            # API returns nested structure: { user: { ... } }
            user_data = response.data.get("user", response.data)

            # Coach targeting an athlete: resolve and return that athlete's
            # profile rather than the coach's own account. ensure_athlete_id
            # reuses the shared name/ID resolution + ambiguity handling.
            if athlete_override.get() is not None:
                target_id = await client.ensure_athlete_id()
                if not target_id:
                    return {
                        "isError": True,
                        "error_code": "NOT_FOUND",
                        "message": "Could not resolve the requested athlete.",
                    }
                for a in user_data.get("athletes", []):
                    if a.get("athleteId") == target_id:
                        return _profile_from_athlete_entry(a)
                return {
                    "isError": True,
                    "error_code": "NOT_FOUND",
                    "message": "Requested athlete not found in coach roster.",
                }

            # Get athlete ID from athletes array or personId
            athlete_id = user_data.get("personId")
            if not athlete_id:
                athletes = user_data.get("athletes", [])
                if athletes:
                    athlete_id = athletes[0].get("athleteId")

            # Check if premium
            is_premium = (
                user_data.get("settings", {}).get("account", {}).get("isPremium", False)
            )
            account_type = "premium" if is_premium else "basic"

            first = user_data.get("firstName", "")
            last = user_data.get("lastName", "")
            name = user_data.get("fullName") or f"{first} {last}".strip()

            return {
                "athlete_id": athlete_id,
                "name": name,
                "email": user_data.get("email"),
                "account_type": account_type,
            }
        except ValueError as e:
            # Ambiguous athlete name (raised by ensure_athlete_id) — surface it.
            return {
                "isError": True,
                "error_code": "VALIDATION_ERROR",
                "message": str(e),
            }
        except Exception:
            logger.exception("Failed to parse profile")
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": "Failed to parse profile.",
            }


async def tp_list_athletes() -> dict[str, Any]:
    """List athletes available to this account (coach accounts).

    Returns:
        Dict with athletes list, each containing athlete_id, name, is_self flag,
        and user_type (TrainingPeaks account-type code from the roster entry;
        premium cohort is user_type 1 or 4; None when absent). Exposing it here
        avoids a per-athlete fanout just to filter by account type.
    """
    async with TPClient() as client:
        user_data = await client._get_user_data()

        if not user_data:
            return {
                "isError": True,
                "error_code": "API_ERROR",
                "message": "Could not retrieve user data.",
            }

        person_id = user_data.get("personId")
        coach_email = (user_data.get("email") or "").lower()
        athletes = user_data.get("athletes", [])

        if not athletes:
            return {
                "athletes": [],
                "message": "No athletes found. This may not be a coach account.",
            }

        result = []
        for a in athletes:
            first = a.get("firstName", "")
            last = a.get("lastName", "")
            athlete_email = (a.get("email") or "").lower()
            is_self = a.get("coachedBy") == person_id and athlete_email == coach_email
            result.append(
                {
                    "athlete_id": a.get("athleteId"),
                    "name": f"{first} {last}".strip(),
                    "is_self": is_self,
                    "user_type": a.get("userType"),
                }
            )

        return {"athletes": result}
