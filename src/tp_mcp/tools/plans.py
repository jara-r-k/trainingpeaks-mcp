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

Draft-plan writes (HC guarded execution only; one write each, never retried):
  POST   /plans/v1/plans                                          → create a plan
  POST   /plans/v1/plans/{id}/commands/addworkoutfromlibraryitem  → library item onto a day
  POST   /plans/v1/plans/{id}/workouts                            → create a plan workout
  DELETE /plans/v1/plans/{id}/workouts/{workoutId}                → delete a plan workout
  DELETE /plans/v1/plans/{id}                                     → delete a plan
"""

import json
import logging
import re
from datetime import date as date_type
from datetime import timedelta
from math import isclose
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from tp_mcp.client import TPClient
from tp_mcp.client.context import GuardViolationError, athlete_override, require_guard
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


def _plan_workout_payload(w: dict[str, Any], athlete_id: int | None, day: date_type) -> dict[str, Any]:
    """Create-endpoint payload that copies one plan workout's planned fields to ``day``
    (without ``athleteId`` when ``athlete_id`` is None: a plan's own workout)."""
    tid = w.get("workoutTypeValueId")
    payload: dict[str, Any] = {
        "workoutDay": f"{day.isoformat()}T00:00:00",
        "workoutTypeFamilyId": tid,   # family == value for standard sports
        "workoutTypeValueId": tid,
        "title": (w.get("title") or "Workout").strip(),
    }
    if athlete_id is not None:
        payload["athleteId"] = athlete_id
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


def _matches_plan_workout(w: dict[str, Any], payload: dict[str, Any]) -> bool:
    """Match a new calendar card to the intended copy when the POST returned no id."""
    if (w.get("workoutTypeValueId") != payload["workoutTypeValueId"]
            or (w.get("workoutDay") or "")[:10] != payload["workoutDay"][:10]
            or (w.get("title") or "").strip() != payload["title"]):
        return False
    try:
        for field in ("totalTimePlanned", "distancePlanned"):
            actual, expected = w.get(field), payload.get(field)
            if actual is None or expected is None:
                if actual is not expected:
                    return False
            elif not isclose(float(actual), float(expected), rel_tol=0, abs_tol=1e-6):
                return False
        if "structure" in payload:
            actual, expected = w.get("structure"), payload["structure"]
            if isinstance(actual, str):
                actual = json.loads(actual)
            if isinstance(expected, str):
                expected = json.loads(expected)
            if json.dumps(actual, sort_keys=True) != json.dumps(expected, sort_keys=True):
                return False
    except (TypeError, ValueError, OverflowError):
        return False
    return True


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
        # After a successful re-read without an id or POST error, created=False
        # requires no added cards; new cards without a unique full match are ambiguous.
        after = await day_workouts()
        added = [w for w in (after or []) if w.get("workoutId") not in before_ids]
        ambiguous = False
        if new_id:
            # A known id is authoritative: never adopt some other same-titled card.
            saved = next((w for w in added if w.get("workoutId") == new_id), None)
        else:
            matches = [w for w in added if _matches_plan_workout(w, payload)]
            ambiguous = bool(added) and len(matches) != 1
            saved = matches[0] if len(matches) == 1 else None
        if post_error and saved is None:
            # The request may have saved server-side before failing: unknown, check first.
            note = "unknown whether it was created; do NOT re-copy, check first"
            return {**post_error, "created": None, "message": f"{post_error.get('message')} ({note})"}
        created: bool | None
        if saved is not None:
            created = True
        elif after is None or new_id or ambiguous:
            created = None  # The re-read cannot establish which card, if any, was created.
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
        if ambiguous:
            result["message"] = "New cards could not be uniquely matched to this copy; do NOT re-copy, check first."
        elif created is None:
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
    # Not registered as an MCP tool in this fork (bulk, visible writes). Kept for
    # upstream parity; guarded so a direct caller can't default to the coach's calendar.
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
    if not athlete_override.get():
        return _err("VALIDATION_ERROR", "Pass athlete=<id>: plans are only applied to a named athlete.")
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


# --- Draft-plan writes (HC guarded execution only) ----------------------------
# Each tool calls require_guard() first and sends exactly one write, never retried
# (the client never resends a plan write, even on 401). The guard's allowlist names
# the exact method and path; reads before and after the write give created/deleted
# as True, False or None, and the caller never re-sends on True or None.

# The only plans these tools create or delete: the coach's weekly drafts and probes.
_DRAFT_TITLE = re.compile(r"(?:2\.7 week \d{1,2} drafts|HC scratch probe \d{4}-\d{2}-\d{2})", re.ASCII)
# A write that failed like this may have reached the server with no usable answer
# (a 401, or a timeout), so an empty re-read cannot prove nothing was created.
_MAYBE_SENT = ("AUTH_EXPIRED", "NETWORK_ERROR")


def _is_draft_title(title: object) -> bool:
    return isinstance(title, str) and 1 <= len(title) <= 100 and _DRAFT_TITLE.fullmatch(title) is not None


def _guard_error() -> dict[str, Any] | None:
    """Refuse to run outside an HC guarded execution."""
    try:
        require_guard()
    except GuardViolationError as e:
        return _err("GUARD_REQUIRED", str(e))
    return None


def _validation_err(e: Exception) -> dict[str, Any]:
    return _err("VALIDATION_ERROR", format_validation_error(e) if isinstance(e, ValidationError) else str(e))


async def _list_plans(client: TPClient) -> list[dict[str, Any]] | None:
    r = await client.get("/plans/v1/plans", cache=False)
    return r.data if not r.is_error and isinstance(r.data, list) else None


def _plan_title(p: dict[str, Any]) -> str:
    return (p.get("title") or "").strip()


def _created_result(
    created: bool | None, post_error: dict[str, Any] | None, fields: dict[str, Any], ambiguous: bool = False,
) -> dict[str, Any]:
    if post_error and created is not True:
        note = (
            "nothing was created" if created is False
            else "unknown whether it was created; do NOT re-send, check first"
        )
        return {**post_error, "created": created, **fields, "message": f"{post_error.get('message')} ({note})"}
    result: dict[str, Any] = {"success": created is True, "created": created, **fields}
    if created is None:
        result["message"] = (
            "New items could not be uniquely matched to this write" if ambiguous else "Not visible on re-read yet"
        ) + "; do NOT re-send, check first."
    return result


async def tp_create_training_plan(title: str) -> dict[str, Any]:
    """Create ONE empty, non-dynamic draft training plan titled ``title``.

    Only '2.7 week N drafts' and 'HC scratch probe YYYY-MM-DD' titles, and never one
    that already exists. Sends ``{"title", "isDynamic": false}`` only: no folder, no
    Product API. Lists the plans before and after the single POST: ``created`` is True
    when exactly one plan with the title now exists and it is the POST's id (or the
    only new one), False only when the POST failed and no such plan exists, else None.
    """
    if not _is_draft_title(title):
        return _err("VALIDATION_ERROR", "Title must be '2.7 week N drafts' or 'HC scratch probe YYYY-MM-DD'.")
    if refused := _guard_error():
        return refused
    async with TPClient() as client:
        before = await _list_plans(client)
        if before is None:
            return _err("API_ERROR", "Could not list plans before creating; nothing was created.")
        if any(_plan_title(p) == title for p in before):
            return _err("VALIDATION_ERROR", f"A plan titled {title!r} already exists; nothing was created.")
        before_ids = {p.get("planId") for p in before}

        resp = await client.post("/plans/v1/plans", json={"title": title, "isDynamic": False})
        post_error = _api_err(resp) if resp.is_error else None
        new_id = resp.data.get("planId") if isinstance(resp.data, dict) else None

        after = await _list_plans(client)
        same = [p for p in after or [] if _plan_title(p) == title]
        saved = same[0] if (
            len(same) == 1 and same[0].get("planId") not in before_ids
            and (not new_id or same[0].get("planId") == new_id)
        ) else None
        created: bool | None
        if saved is not None:
            created = True
        elif after is not None and not same and post_error and post_error["error_code"] not in _MAYBE_SENT:
            created = False
        else:
            created = None
        fields = {"plan_id": saved.get("planId") if saved else new_id, "title": title}
        return _created_result(created, post_error, fields, ambiguous=bool(same) and saved is None)


async def _write_plan_day(
    client: TPClient, plan_id: int, day: date_type, endpoint: str, body: dict[str, Any], match: Any,
) -> dict[str, Any]:
    """POST once between two uncached reads of the plan day, diffed as tp_copy_plan_workout
    diffs an athlete day. ``match`` picks the new card when the POST returns no id; with
    None, no card is adopted without an id. False only when the POST failed and nothing
    new is on the day."""
    day_endpoint = f"/plans/v1/plans/{plan_id}/workouts/{day.isoformat()}/{day.isoformat()}"

    async def day_workouts() -> list[dict[str, Any]] | None:
        r = await client.get(day_endpoint, cache=False)
        return r.data if not r.is_error and isinstance(r.data, list) else None

    before = await day_workouts()
    if before is None:
        return _err("API_ERROR", "Could not read the plan day before writing; nothing was created.")
    before_ids = {w.get("workoutId") for w in before}

    resp = await client.post(endpoint, json=body)
    post_error = _api_err(resp) if resp.is_error else None
    new_id = resp.data.get("workoutId") if isinstance(resp.data, dict) else None

    after = await day_workouts()
    added = [w for w in (after or []) if w.get("workoutId") not in before_ids]
    if new_id:
        # A known id is authoritative: never adopt some other same-titled card.
        saved = next((w for w in added if w.get("workoutId") == new_id), None)
    else:
        matches = [w for w in added if match is not None and match(w)]
        saved = matches[0] if len(matches) == 1 else None
    created: bool | None
    if saved is not None:
        created = True
    elif after is not None and not added and post_error and post_error["error_code"] not in _MAYBE_SENT:
        created = False
    else:
        created = None
    fields = {"workout_id": saved.get("workoutId") if saved else new_id, "plan_id": plan_id, "date": day.isoformat()}
    return _created_result(created, post_error, fields, ambiguous=bool(added) and saved is None)


class _AddFromLibraryInput(BaseModel):
    plan_id: int = Field(gt=0)
    library_item_id: int = Field(gt=0)
    target_date: date_type


async def tp_add_plan_workout_from_library(
    plan_id: int | str, library_item_id: int | str, target_date: str,
) -> dict[str, Any]:
    """Drop ONE library item onto a draft plan's ``target_date`` (the web app's drag).

    Snapshots the plan day before the single POST and diffs it after. The item's own
    title, sport and time are not read, so a new card is only adopted by the workoutId
    the POST returns; without one, ``created`` is None whenever a card appears.
    """
    try:
        v = _AddFromLibraryInput(
            plan_id=plan_id, library_item_id=library_item_id, target_date=target_date,  # type: ignore[arg-type]
        )
    except (ValidationError, ValueError) as e:
        return _validation_err(e)
    if refused := _guard_error():
        return refused
    body = {
        "planId": v.plan_id,
        "exerciseLibraryItemId": v.library_item_id,
        "workoutDateTime": f"{v.target_date.isoformat()}T00:00:00",
    }
    async with TPClient() as client:
        endpoint = f"/plans/v1/plans/{v.plan_id}/commands/addworkoutfromlibraryitem"
        result = await _write_plan_day(client, v.plan_id, v.target_date, endpoint, body, None)
    return {**result, "library_item_id": v.library_item_id}


class _PlanWorkoutFields(BaseModel):
    """A new plan workout's planned fields, keyed by TP's names; unknown keys are refused."""

    model_config = ConfigDict(extra="forbid")
    type_id: int = Field(alias="workoutTypeValueId")
    title: str
    description: str | None = None
    coach_comments: str | None = Field(default=None, alias="coachComments")
    time_h: float | None = Field(default=None, alias="totalTimePlanned", ge=0, allow_inf_nan=False)
    distance_m: float | None = Field(default=None, alias="distancePlanned", ge=0, allow_inf_nan=False)
    tss: float | None = Field(default=None, alias="tssPlanned", ge=0, allow_inf_nan=False)
    intensity: float | None = Field(default=None, alias="ifPlanned", ge=0, allow_inf_nan=False)
    sub_type_id: int | None = Field(default=None, alias="workoutSubTypeId")
    structure: dict[str, Any] | str | None = None

    @field_validator("type_id")
    @classmethod
    def _known_sport(cls, v: int) -> int:
        if v not in _SPORT_BY_TYPE:
            raise ValueError(f"unknown workoutTypeValueId {v}")
        return v

    @field_validator("title")
    @classmethod
    def _has_title(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("title must not be blank")
        return v

    @field_validator("structure")
    @classmethod
    def _json_object(cls, v: Any) -> Any:
        if isinstance(v, str) and not isinstance(json.loads(v), dict):
            raise ValueError("structure must be a JSON object")
        return v


class _CreatePlanWorkoutInput(BaseModel):
    plan_id: int = Field(gt=0)
    target_date: date_type
    workout: _PlanWorkoutFields


async def tp_create_plan_workout(
    plan_id: int | str, target_date: str, workout: dict[str, Any],
) -> dict[str, Any]:
    """Create ONE workout directly in a draft plan on ``target_date``.

    ``workout`` uses TP's field names (workoutTypeValueId, title, description,
    coachComments, totalTimePlanned, distancePlanned, tssPlanned, ifPlanned,
    workoutSubTypeId, structure) and is sent as a calendar create sends it (workoutId 0,
    coach comments verbatim, structure as a JSON string). Snapshots the plan day before
    the single POST and diffs it after; without a returned id a new card must match
    title, sport, planned time, distance and structure.
    """
    try:
        v = _CreatePlanWorkoutInput(plan_id=plan_id, target_date=target_date, workout=workout)  # type: ignore[arg-type]
    except (ValidationError, ValueError) as e:
        return _validation_err(e)
    if refused := _guard_error():
        return refused
    fields = v.workout.model_dump(by_alias=True, exclude_none=True)
    body = {"workoutId": 0, **_plan_workout_payload(fields, None, v.target_date)}
    async with TPClient() as client:
        endpoint = f"/plans/v1/plans/{v.plan_id}/workouts"
        result = await _write_plan_day(
            client, v.plan_id, v.target_date, endpoint, body, lambda w: _matches_plan_workout(w, body),
        )
    return {**result, "title": body["title"]}


def _not_draft(plans: list[dict[str, Any]], plan_id: int) -> dict[str, Any] | None:
    """Refuse a delete unless the plan is listed with a draft or scratch title."""
    plan = next((p for p in plans if p.get("planId") == plan_id), None)
    if plan is None:
        return _err("NOT_FOUND", f"Plan {plan_id} is not in your plans; nothing was deleted.")
    if not _is_draft_title(plan.get("title")):
        return _err("VALIDATION_ERROR", f"Plan {plan_id} is not a draft or scratch plan; nothing was deleted.")
    return None


def _deleted_result(deleted: bool | None, resp: Any, fields: dict[str, Any]) -> dict[str, Any]:
    if resp.is_error and deleted is not True:
        error = _api_err(resp)
        if error["error_code"] in _MAYBE_SENT:
            deleted = None  # The DELETE may still land: never report a retryable False.
        note = "still there" if deleted is False else "unknown whether it was deleted; do NOT re-send, check first"
        return {**error, "deleted": deleted, **fields, "message": f"{error.get('message')} ({note})"}
    result: dict[str, Any] = {"success": deleted is True, "deleted": deleted, **fields}
    if deleted is None:
        result["message"] = "Could not re-read to confirm the delete; do NOT re-send, check first."
    elif not deleted:
        result["message"] = "Still there after the delete."
    return result


class _DeletePlanWorkoutInput(BaseModel):
    plan_id: int = Field(gt=0)
    workout_id: int = Field(gt=0)


async def tp_delete_plan_workout(plan_id: int | str, workout_id: int | str) -> dict[str, Any]:
    """Delete ONE workout from a draft or scratch plan, then re-read the plan:
    ``deleted`` is True (gone), False (still there) or None (unreadable)."""
    try:
        v = _DeletePlanWorkoutInput(plan_id=plan_id, workout_id=workout_id)  # type: ignore[arg-type]
    except (ValidationError, ValueError) as e:
        return _validation_err(e)
    if refused := _guard_error():
        return refused
    async with TPClient() as client:
        plans = await _list_plans(client)
        if plans is None:
            return _err("API_ERROR", "Could not list plans; nothing was deleted.")
        if refused := _not_draft(plans, v.plan_id):
            return refused
        sd, before = await _fetch_plan_workouts(client, v.plan_id)
        if sd is None:
            return {**before, "message": f"{before.get('message')} Nothing was deleted."}
        if not any(w.get("workoutId") == v.workout_id for w in before):
            return _err("NOT_FOUND", f"Workout {v.workout_id} is not in plan {v.plan_id}; nothing was deleted.")
        resp = await client.delete(f"/plans/v1/plans/{v.plan_id}/workouts/{v.workout_id}")
        sd, after = await _fetch_plan_workouts(client, v.plan_id)
        deleted = None if sd is None else all(w.get("workoutId") != v.workout_id for w in after)
        return _deleted_result(deleted, resp, {"plan_id": v.plan_id, "workout_id": v.workout_id})


async def tp_delete_training_plan(plan_id: int | str) -> dict[str, Any]:
    """Delete ONE draft or scratch plan, then re-list the plans: ``deleted`` is True
    (gone), False (still listed) or None (unreadable)."""
    try:
        v = _PlanIdInput(plan_id=plan_id)  # type: ignore[arg-type]
    except (ValidationError, ValueError) as e:
        return _validation_err(e)
    if refused := _guard_error():
        return refused
    async with TPClient() as client:
        plans = await _list_plans(client)
        if plans is None:
            return _err("API_ERROR", "Could not list plans; nothing was deleted.")
        if refused := _not_draft(plans, v.plan_id):
            return refused
        resp = await client.delete(f"/plans/v1/plans/{v.plan_id}")
        after = await _list_plans(client)
        deleted = None if after is None else all(p.get("planId") != v.plan_id for p in after)
        return _deleted_result(deleted, resp, {"plan_id": v.plan_id})
