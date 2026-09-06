"""TOOL-02: tp_get_profile / tp_list_athletes - Profile and coach tools."""

import logging
from datetime import datetime, timezone
from typing import Any

from tp_mcp.client import TPClient

logger = logging.getLogger("tp-mcp")


def _derive_tier(
    *, expired: bool | None, user_type: int | None, trial_days: int | None
) -> str | None:
    """Map raw account fields → TP-UI label («Account Type»). Verified against
    the live UI on a real coach roster spanning all four states (coach-paid,
    basic, self-paid and trial athletes). Order matters — trial first, then
    active subscription, then lapsed-but-tier-1 = coach-paid, default basic.

    Returns one of: ``premium_trial`` / ``premium_self`` / ``premium_coach`` /
    ``basic`` / ``None`` (when ``expired`` couldn't be parsed).
    """
    if isinstance(trial_days, int) and trial_days > 0:
        return "premium_trial"
    if expired is False:
        return "premium_self"  # active personal subscription
    if expired is True and user_type == 1:
        return "premium_coach"  # lapsed personal premium, coach pays
    if expired is True:
        return "basic"  # no premium tier
    return None  # expireOn unparseable / missing


def _account_fields(entry: dict[str, Any]) -> dict[str, Any]:
    """Premium / account fields from a coach-roster ``athletes[]`` entry, plus
    a derived ``tier`` («Account Type» in the TP UI).

    /users/v3/user does NOT expose a clean ``isPremium`` for a coached athlete
    — that belongs to the logged-in user. The roster entry, though, carries
    several account-related fields whose exact semantics aren't documented by
    TP. We surface them raw AND derive a four-state tier label that matches the
    TP UI (verified live on athletes from each state; see ``_derive_tier``).

    Known fields per entry (live-verified on a coach account):
      • ``expireOn`` — ISO timestamp; expiration of the athlete's PERSONAL
        subscription. A past date does NOT mean «no premium»: on a coach-paid
        athlete the coach's plan grants premium externally, the personal date
        stays frozen on whenever the athlete last paid (observed live: an
        expireOn years in the past on an athlete with coach-granted premium).
      • ``athleteType`` (int) — varies (0/2/4/5), not used by the derivation.
      • ``userType`` (int) — 1 = was-ever-premium (paid tier code, persists
        even after personal expiry); 4 = active personal premium; 6 = basic.
        The derivation uses this to separate «coach-paid» from «basic».
      • ``premiumTrial`` (bool) / ``premiumTrialDaysRemaining`` (int) — when
        days>0 the athlete is on the free trial (premium-equivalent access).
      • ``downgradeAllowed`` / ``downgradeAllowedOn`` / ``lastUpgradeOn`` —
        billing-action hints, not part of the derivation.
    """
    exp_raw = entry.get("expireOn")
    expired: bool | None = None
    if isinstance(exp_raw, str) and exp_raw:
        try:
            dt = datetime.fromisoformat(exp_raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            expired = dt < datetime.now(timezone.utc)
        except ValueError:
            expired = None
    user_type = entry.get("userType")
    trial_days = entry.get("premiumTrialDaysRemaining")
    return {
        "tier": _derive_tier(
            expired=expired, user_type=user_type, trial_days=trial_days
        ),
        "expire_on": exp_raw,
        "expired": expired,
        "athlete_type": entry.get("athleteType"),
        "user_type": user_type,
        "premium_trial": entry.get("premiumTrial"),
        "premium_trial_days_remaining": trial_days,
        "downgrade_allowed": entry.get("downgradeAllowed"),
        "downgrade_allowed_on": entry.get("downgradeAllowedOn"),
        "last_upgrade_on": entry.get("lastUpgradeOn"),
    }


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
        # A clean «premium / basic» label isn't exposed for a coached athlete by
        # /users/v3/user. Raw account-related fields ARE present on the roster
        # entry, surfaced under `account` for caller-side analysis (see
        # _account_fields docstring for the known shape and caveats).
        "account_type": None,
        "account": _account_fields(entry),
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
        user_type, and an account sub-dict. `user_type` is TP's userType for
        the athlete (1 = premium coach-paid, 4 = premium self-paid, 6 = basic);
        it is carried straight from the /users/v3/user athlete entry so a
        coach roster premium filter (userType in {1, 4}) can run off the list
        without a per-athlete settings call. It is None when the TP tier omits
        userType. `account` carries the fuller raw premium/account fields plus
        a derived `tier` — one of `premium_self` / `premium_coach` /
        `premium_trial` / `basic` — matching the «Account Type» label in the
        TP UI (see `_account_fields` / `_derive_tier`).
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
                    "account": _account_fields(a),
                }
            )

        return {"athletes": result}
