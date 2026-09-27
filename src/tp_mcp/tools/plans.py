"""Training Plan tools — list/read authored multi-week plans + apply to an athlete.

TrainingPeaks training plans (Plan Store / "My Plans") are a separate entity from
workout libraries (exerciselibrary) and the ATP. Endpoints (tpapi):
  GET  /plans/v1/plans                                  → authored plans
  GET  /plans/v1/plans/{id}                             → plan summary
  GET  /plans/v1/plans/{id}/workouts/{start}/{end}      → all plan workouts (w/ structure)

Workouts are anchored at the plan's startDate; ``workoutDay`` gives the relative
day (day 1 = startDate). ``tp_apply_training_plan`` materialises the plan on an
athlete's calendar by COPYING each workout to ``start_date + relative_offset``
via the proven create endpoint (POST /fitness/v6/athletes/{id}/workouts) — there
is no black-box-discoverable native "apply" endpoint, so this is a faithful
client-side copy (structure/description/TSS preserved; TP does not record it as a
linked plan application).
"""

import json
import logging
from datetime import date as date_type
from datetime import timedelta
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from tp_mcp.client import TPClient
from tp_mcp.client.context import athlete_override
from tp_mcp.tools._validation import format_validation_error

logger = logging.getLogger("tp-mcp")

# workoutTypeValueId → sport label (mirrors SPORT_TYPE_MAP in workouts.py; for all
# standard sports the family id equals the value id, so family = value on create).
_SPORT_BY_TYPE: dict[int, str] = {
    1: "Swim", 2: "Bike", 3: "Run", 4: "Brick", 5: "Crosstrain", 6: "Race",
    7: "DayOff", 8: "MtnBike", 9: "Strength", 11: "XCSki", 12: "Rowing", 13: "Walk",
    100: "Other",
}

# workoutTypeValueId 100 ("Other") is used by plans for training-PERIOD annotations
# (e.g. «Период: базовый») — calendar banners, not trainable sessions. They can't
# be replicated as workouts on apply (TP renders them as period bands), so apply
# skips them rather than creating junk calendar entries.
_PERIOD_TYPE_ID = 100


def _err(code: str, msg: str | None) -> dict[str, Any]:
    return {"isError": True, "error_code": code, "message": msg or "error"}


def _api_err(response: Any) -> dict[str, Any]:
    return _err(response.error_code.value if response.error_code else "API_ERROR",
                response.message)


class _PlanIdInput(BaseModel):
    plan_id: int = Field(gt=0)

    @field_validator("plan_id", mode="before")
    @classmethod
    def _coerce(cls, v: object) -> object:
        return int(v) if isinstance(v, str) else v


class _ApplyInput(BaseModel):
    plan_id: int = Field(gt=0)
    start_date: date_type

    @field_validator("plan_id", mode="before")
    @classmethod
    def _coerce_id(cls, v: object) -> object:
        return int(v) if isinstance(v, str) else v

    @field_validator("start_date", mode="before")
    @classmethod
    def _coerce_date(cls, v: object) -> object:
        return date_type.fromisoformat(v) if isinstance(v, str) else v


async def tp_list_training_plans() -> dict[str, Any]:
    """List the coach's authored training plans (slim)."""
    async with TPClient() as client:
        r = await client.get("/plans/v1/plans")
        if r.is_error:
            return _api_err(r)
        out = []
        for p in r.data or []:
            dur = p.get("trainingDurationByWeek") or []
            out.append({
                "plan_id": p.get("planId"),
                "title": (p.get("title") or "").strip(),
                "weeks": p.get("weekCount"),
                "workouts": p.get("workoutCount"),
                "total_hours": round(sum(dur), 1) if dur else None,
                "category": p.get("planCategory"),
                "price": p.get("price"),
                "is_public": p.get("isPublic"),
                "event_date": p.get("eventDate"),
            })
        return {"plans": out, "count": len(out)}


async def tp_get_training_plan(plan_id: int | str) -> dict[str, Any]:
    """Summary of one plan: weeks, per-week duration/distance, sport breakdown."""
    try:
        v = _PlanIdInput(plan_id=plan_id)  # type: ignore[arg-type]
    except (ValidationError, ValueError) as e:
        return _err("VALIDATION_ERROR",
                    format_validation_error(e) if isinstance(e, ValidationError) else str(e))
    async with TPClient() as client:
        r = await client.get(f"/plans/v1/plans/{v.plan_id}")
        if r.is_error:
            return _api_err(r)
        d = r.data or {}
        dur = d.get("trainingDurationByWeek") or []
        dist = d.get("trainingDistanceByWeek") or []
        by_sport = []
        for t in d.get("plannedWorkoutTypeDurations") or []:
            if (t.get("duration") or 0) or (t.get("distance") or 0):
                by_sport.append({
                    "sport": _SPORT_BY_TYPE.get(t.get("workoutTypeId"), str(t.get("workoutTypeId"))),
                    "hours": round(t.get("duration") or 0, 1),
                    "km": round((t.get("distance") or 0) / 1000, 1),
                })
        return {
            "plan_id": d.get("planId"),
            "title": (d.get("title") or "").strip(),
            "weeks": d.get("weekCount"),
            "day_count": d.get("dayCount"),
            "workouts": d.get("workoutCount"),
            "description": d.get("description"),
            "duration_by_week_h": [round(x, 2) for x in dur],
            "distance_by_week_km": [round(x / 1000, 1) for x in dist],
            "by_sport": by_sport,
            "start_date": (d.get("startDate") or "")[:10] or None,
        }


async def _fetch_plan_workouts(
    client: TPClient, plan_id: int,
) -> tuple[date_type | None, Any]:
    """(plan startDate, [workouts]) or (None, error_dict). The plan-workouts range
    endpoint is NOT 90-day-capped (verified on a 112-day plan)."""
    det = await client.get(f"/plans/v1/plans/{plan_id}")
    if det.is_error:
        return None, _api_err(det)
    d = det.data or {}
    start = (d.get("startDate") or "")[:10]
    days = d.get("dayCount") or (d.get("weekCount") or 0) * 7
    if not start or not days:
        return None, _err("API_ERROR", "Plan has no startDate/dayCount.")
    sd = date_type.fromisoformat(start)
    ed = sd + timedelta(days=int(days) + 1)
    wr = await client.get(f"/plans/v1/plans/{plan_id}/workouts/{sd.isoformat()}/{ed.isoformat()}")
    if wr.is_error:
        return None, _api_err(wr)
    return sd, (wr.data or [])


async def tp_get_training_plan_workouts(plan_id: int | str, week: int | None = None) -> dict[str, Any]:
    """All workouts of a plan, laid out by week/day (slim — title/description/
    duration/TSS/has_structure; full structure is omitted to keep the payload
    small, but is used internally by tp_apply_training_plan). ``week`` limits
    the result to one plan week (1-based)."""
    try:
        v = _PlanIdInput(plan_id=plan_id)  # type: ignore[arg-type]
    except (ValidationError, ValueError) as e:
        return _err("VALIDATION_ERROR",
                    format_validation_error(e) if isinstance(e, ValidationError) else str(e))
    async with TPClient() as client:
        sd, ws = await _fetch_plan_workouts(client, v.plan_id)
        if sd is None:
            return ws  # error dict
        out = []
        for w in ws:
            wd = (w.get("workoutDay") or "")[:10]
            try:
                rel = (date_type.fromisoformat(wd) - sd).days + 1 if wd else None
            except ValueError:
                rel = None
            wk = ((rel - 1) // 7 + 1) if rel else None
            if week is not None and wk != week:
                continue
            out.append({
                "id": w.get("workoutId"),
                "week": wk,
                "day": rel,
                "weekday": date_type.fromisoformat(wd).strftime("%a") if rel else None,
                "order_on_day": w.get("orderOnDay"),
                "sport": _SPORT_BY_TYPE.get(w.get("workoutTypeValueId"), str(w.get("workoutTypeValueId"))),
                "title": (w.get("title") or "").strip(),
                "description": w.get("description"),
                "duration_min": round((w.get("totalTimePlanned") or 0) * 60) or None,
                "distance_km": round((w.get("distancePlanned") or 0) / 1000, 2) or None,
                "tss": w.get("tssPlanned"),
                "has_structure": w.get("structure") is not None,
            })
        out.sort(key=lambda x: (x["day"] or 0, x["order_on_day"] or 0))
        return {"plan_id": v.plan_id, "week": week, "workouts": out, "count": len(out)}


def _plan_workout_payload(w: dict[str, Any], athlete_id: int, day: date_type) -> dict[str, Any]:
    """Create-endpoint payload that copies one plan workout's planned fields to ``day``."""
    tid = w.get("workoutTypeValueId")
    payload: dict[str, Any] = {
        "athleteId": athlete_id,
        "workoutDay": f"{day.isoformat()}T00:00:00",
        "workoutTypeFamilyId": tid,   # family == value for standard sports
        "workoutTypeValueId": tid,
        "title": (w.get("title") or "Workout").strip(),
    }
    for field in ("totalTimePlanned", "distancePlanned", "tssPlanned", "ifPlanned", "workoutSubTypeId"):
        if w.get(field) is not None:
            payload[field] = w[field]
    for field in ("description", "coachComments"):
        if w.get(field):
            payload[field] = w[field]
    st = w.get("structure")
    if isinstance(st, dict):
        payload["structure"] = json.dumps(st)
    elif isinstance(st, str) and st:
        payload["structure"] = st
    return payload


class _CopyPlanWorkoutInput(BaseModel):
    plan_id: int = Field(gt=0)
    plan_workout_id: int = Field(gt=0)
    target_date: date_type


async def tp_copy_plan_workout(
    plan_id: int | str,
    plan_workout_id: int | str,
    target_date: str,
    is_hidden: bool = True,
) -> dict[str, Any]:
    """Copy ONE plan workout (a single card) onto the athlete's calendar on ``target_date``.

    The MCP equivalent of the Dual Calendar Copy -> Paste. Hidden from the athlete by
    default. Requires an explicit athlete target (never falls back to the caller's own
    calendar). Snapshots the day's workouts before creating and diffs them after, so
    ``created`` (a new workout exists) is reported separately from ``verified`` (it is
    there with the requested visibility). Never retries: the caller decides whether
    to try again, and must not re-copy when ``created`` is true. Never writes to the
    plan itself.
    """
    try:
        v = _CopyPlanWorkoutInput(
            plan_id=plan_id, plan_workout_id=plan_workout_id, target_date=target_date,  # type: ignore[arg-type]
        )
    except (ValidationError, ValueError) as e:
        return _err("VALIDATION_ERROR",
                    format_validation_error(e) if isinstance(e, ValidationError) else str(e))
    if not athlete_override.get():
        return _err("VALIDATION_ERROR", "Pass athlete=<id>: plan cards are only copied to a named athlete.")
    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return _err("AUTH_INVALID", "Could not get athlete ID. Re-authenticate.")

        sd, ws = await _fetch_plan_workouts(client, v.plan_id)
        if sd is None:
            return ws  # error dict
        source = next((w for w in ws if w.get("workoutId") == v.plan_workout_id), None)
        if source is None:
            return _err("NOT_FOUND", f"Workout {v.plan_workout_id} is not in plan {v.plan_id}.")
        if source.get("workoutTypeValueId") == _PERIOD_TYPE_ID:
            return _err("VALIDATION_ERROR", "That card is a training-period annotation, not a session.")

        day = v.target_date.isoformat()
        day_endpoint = f"/fitness/v6/athletes/{athlete_id}/workouts/{day}/{day}"

        async def day_workouts() -> list[dict[str, Any]] | None:
            r = await client.get(day_endpoint, cache=False)
            return r.data if not r.is_error and isinstance(r.data, list) else None

        before = await day_workouts()
        if before is None:
            return _err("API_ERROR", "Could not read the target day before copying; nothing was created.")
        before_ids = {w.get("workoutId") for w in before}

        payload = _plan_workout_payload(source, athlete_id, v.target_date)
        payload["isHidden"] = is_hidden
        resp = await client.post(f"/fitness/v6/athletes/{athlete_id}/workouts", json=payload)
        post_error = _api_err(resp) if resp.is_error else None
        new_id = resp.data.get("workoutId") if isinstance(resp.data, dict) else None

        # Stick check: uncached re-read, diffed against the snapshot. A POST that
        # errored or returned no id may still have created the workout.
        after = await day_workouts()
        added = [w for w in (after or []) if w.get("workoutId") not in before_ids]
        saved = next((w for w in added if new_id and w.get("workoutId") == new_id), None) or next(
            (w for w in added if (w.get("title") or "").strip() == payload["title"]), None
        )
        if post_error and saved is None:
            # The request may have saved server-side before failing: unknown, check first.
            return {**post_error, "created": None}
        created: bool | None
        if saved is not None:
            created = True
        elif after is None or new_id:
            created = None  # TP returned an id (or the re-read failed) but the day doesn't show it yet
        else:
            created = False
        verified = saved is not None and bool(saved.get("isHidden")) == is_hidden
        result: dict[str, Any] = {
            "success": verified,
            "created": created,
            "verified": verified,
            "workout_id": saved.get("workoutId") if saved else new_id,
            "athlete_id": athlete_id,
            "date": day,
            "title": payload["title"],
            "is_hidden": saved.get("isHidden") if saved else None,
            "copied_from": {"plan_id": v.plan_id, "plan_workout_id": v.plan_workout_id},
        }
        if created is None:
            result["message"] = (
                "Unknown whether it was created (not visible on re-read yet). Do NOT re-copy; check first."
            )
        elif not created:
            result["message"] = "Not found on the calendar after copying."
        elif not verified:
            result["message"] = "Created, but not with the requested visibility. Fix visibility; do NOT re-copy."
        return result


# NB on the NATIVE apply command — fully reverse-engineered (Claude-in-Chrome HAR +
# live probes) but NOT used, because every server-side replication produced a
# DEGENERATE apply (an applied-plan record with endDate == startDate-ish and ZERO
# workouts materialised), and the body that makes the web's apply actually populate
# the calendar could not be reproduced:
#   1. POST /plans/v1/commands/applyplan  body=[{athleteId(str), planId, planTitle,
#      startType, targetDate}] → [{appliedPlanId, startDate, endDate, ...}].
#   2. Async job; drive it by polling POST /plans/v1/appliedplans/applyPlanStatus
#      with a BARE array body [appliedPlanId] (NOT {"AppliedPlanIds":[...]} — that
#      400s), response {"batchStatus": N}, 2 = complete.
# Live result: with startType 1 AND 2 the command returns batchStatus 2 (="done")
# yet creates NO workouts on the calendar (verified across several far-date applies
# on two athletes); startType 0 is rejected. The only captured web payload was a
# startType:1 apply that was itself degenerate, so the working-apply body is unknown.
# → We use the SYNTHETIC copy below: deterministic, one-shot, fully verified live.
# (Revisit native only with a HAR of a CONFIRMED-WORKING web apply's request body.)


async def tp_apply_training_plan(plan_id: int | str, start_date: str) -> dict[str, Any]:
    """Apply a plan to the athlete's calendar from ``start_date`` by copying each
    plan workout to ``start_date + relative_day`` (structure/description/TSS
    preserved); training-period annotation markers are skipped. Athlete is resolved
    from the coach's athlete_override context (the ``athlete`` arg, handled by the
    server dispatch)."""
    try:
        v = _ApplyInput(plan_id=plan_id, start_date=start_date)  # type: ignore[arg-type]
    except (ValidationError, ValueError) as e:
        return _err("VALIDATION_ERROR",
                    format_validation_error(e) if isinstance(e, ValidationError) else str(e))
    async with TPClient() as client:
        athlete_id = await client.ensure_athlete_id()
        if not athlete_id:
            return _err("AUTH_INVALID", "Could not get athlete ID. Re-authenticate.")

        sd, ws = await _fetch_plan_workouts(client, v.plan_id)
        if sd is None:
            return ws  # error dict

        created = failed = skipped = 0
        first_error: str | None = None
        for w in ws:
            tid = w.get("workoutTypeValueId")
            if tid == _PERIOD_TYPE_ID:
                skipped += 1   # training-period annotation, not a session
                continue
            wd = (w.get("workoutDay") or "")[:10]
            try:
                rel = (date_type.fromisoformat(wd) - sd).days if wd else None
            except ValueError:
                rel = None
            if rel is None:
                failed += 1
                continue
            day = v.start_date + timedelta(days=rel)
            payload = _plan_workout_payload(w, athlete_id, day)

            resp = await client.post(f"/fitness/v6/athletes/{athlete_id}/workouts", json=payload)
            if resp.is_error:
                failed += 1
                if first_error is None:
                    first_error = resp.message
            else:
                created += 1

        result: dict[str, Any] = {
            "success": failed == 0 and created > 0,
            "method": "synthetic",
            "plan_id": v.plan_id,
            "athlete_id": athlete_id,
            "start_date": v.start_date.isoformat(),
            "created": created,
            "failed": failed,
            "skipped_periods": skipped,
            "total": len(ws),
        }
        if first_error:
            result["first_error"] = first_error[:160]
        return result
