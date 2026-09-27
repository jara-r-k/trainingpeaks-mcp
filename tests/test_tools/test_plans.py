"""Tests for training-plan tools (list/get/workouts/apply)."""

from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.context import athlete_override
from tp_mcp.client.http import APIResponse
from tp_mcp.tools.plans import (
    tp_apply_training_plan,
    tp_copy_plan_workout,
    tp_get_training_plan,
    tp_get_training_plan_workouts,
    tp_list_training_plans,
)

_DETAIL = {
    "planId": 163992, "title": "Plan 10k  ", "weekCount": 2, "dayCount": 14,
    "workoutCount": 3, "description": "desc", "startDate": "2018-12-17T00:00:00",
    "trainingDurationByWeek": [2.0, 3.0], "trainingDistanceByWeek": [10000.0, 20000.0],
    "plannedWorkoutTypeDurations": [
        {"workoutTypeId": 3, "duration": 5.0, "distance": 40000.0},
        {"workoutTypeId": 7, "duration": 0.0, "distance": 0.0},
    ],
}
# day 1 = period annotation (type 100, skipped on apply), day 2 = structured run,
# day 3 = day off.
_WORKOUTS = [
    {"workoutDay": "2018-12-17T00:00:00", "workoutTypeValueId": 100, "title": "Период: базовый"},
    {"workoutDay": "2018-12-18T00:00:00", "workoutTypeValueId": 3, "title": "Run",
     "description": "easy", "totalTimePlanned": 0.5, "tssPlanned": 26.0,
     "structure": {"structure": [{"x": 1}], "primaryLengthMetric": "duration"}},
    {"workoutDay": "2018-12-19T00:00:00", "workoutTypeValueId": 7, "title": "Выходной"},
]


def _client_with(get_side_effect, post=None, post_side_effect=None, athlete_id=123):
    inst = AsyncMock()
    inst.ensure_athlete_id = AsyncMock(return_value=athlete_id)
    inst.get = AsyncMock(side_effect=get_side_effect)
    if post_side_effect is not None:
        inst.post = AsyncMock(side_effect=post_side_effect)
    else:
        inst.post = AsyncMock(return_value=post or APIResponse(success=True, data={"workoutId": 1}))
    return inst


def _patch(inst):
    p = patch("tp_mcp.tools.plans.TPClient")
    m = p.start()
    m.return_value.__aenter__.return_value = inst
    return p


@pytest.mark.asyncio
async def test_list_slims_records():
    resp = APIResponse(success=True, data=[{
        "planId": 163992, "title": "Plan 10k", "weekCount": 16, "workoutCount": 139,
        "planCategory": 2, "price": 10.0, "isPublic": True, "eventDate": None,
        "trainingDurationByWeek": [2.0, 3.0],
    }])
    inst = _client_with(lambda ep, **k: resp)
    p = _patch(inst)
    try:
        r = await tp_list_training_plans()
    finally:
        p.stop()
    assert r["count"] == 1
    plan = r["plans"][0]
    assert plan["plan_id"] == 163992 and plan["weeks"] == 16 and plan["workouts"] == 139
    assert plan["total_hours"] == 5.0 and plan["price"] == 10.0


@pytest.mark.asyncio
async def test_get_summary_maps_sport_and_weeks():
    inst = _client_with(lambda ep, **k: APIResponse(success=True, data=_DETAIL))
    p = _patch(inst)
    try:
        r = await tp_get_training_plan(163992)
    finally:
        p.stop()
    assert r["title"] == "Plan 10k" and r["weeks"] == 2 and r["day_count"] == 14
    assert r["duration_by_week_h"] == [2.0, 3.0]
    assert r["distance_by_week_km"] == [10.0, 20.0]
    assert {"sport": "Run", "hours": 5.0, "km": 40.0} in r["by_sport"]
    # zero-duration sport (DayOff) is dropped from the breakdown
    assert all(s["sport"] != "DayOff" for s in r["by_sport"])


def _get_router(ep, **k):
    if ep.endswith("/workouts/2018-12-17/2018-12-31"):
        return APIResponse(success=True, data=_WORKOUTS)
    if "/workouts/" in ep:
        return APIResponse(success=True, data=_WORKOUTS)
    return APIResponse(success=True, data=_DETAIL)


@pytest.mark.asyncio
async def test_get_workouts_lays_out_by_week_day():
    inst = _client_with(_get_router)
    p = _patch(inst)
    try:
        r = await tp_get_training_plan_workouts(163992)
    finally:
        p.stop()
    assert r["count"] == 3
    run = next(w for w in r["workouts"] if w["sport"] == "Run")
    assert run["week"] == 1 and run["day"] == 2 and run["has_structure"] is True
    assert run["duration_min"] == 30 and run["tss"] == 26.0
    # period marker surfaces as "Other"
    assert any(w["sport"] == "Other" for w in r["workouts"])


@pytest.mark.asyncio
async def test_apply_copies_workouts_skips_period_markers():
    """Synthetic apply: each plan workout is recreated at start_date + relative
    day (structure preserved as a JSON string); type-100 period markers skipped."""
    post = APIResponse(success=True, data={"workoutId": 999})
    inst = _client_with(_get_router, post=post)
    p = _patch(inst)
    try:
        r = await tp_apply_training_plan(163992, "2027-09-01")
    finally:
        p.stop()
    assert r["success"] is True and r["method"] == "synthetic"
    assert r["created"] == 2          # run + day-off
    assert r["skipped_periods"] == 1  # the type-100 annotation
    assert r["failed"] == 0
    creates = [c.kwargs["json"] for c in inst.post.call_args_list
               if "/fitness/v6/" in c.args[0]]
    run_post = next(b for b in creates if b["workoutTypeValueId"] == 3)
    assert run_post["workoutDay"] == "2027-09-02T00:00:00"  # start_date + rel day 1
    assert run_post["workoutTypeFamilyId"] == 3
    assert isinstance(run_post["structure"], str) and "primaryLengthMetric" in run_post["structure"]


@pytest.mark.asyncio
async def test_invalid_plan_id_validation():
    r = await tp_get_training_plan(0)
    assert r["isError"] is True and r["error_code"] == "VALIDATION_ERROR"


# --- single-card copy (Head Coach Copy -> Paste equivalent) -------------------

_CARDS = [
    {"workoutId": 11, "workoutDay": "2018-12-17T00:00:00", "workoutTypeValueId": 100, "title": "Period"},
    {"workoutId": 12, "workoutDay": "2018-12-18T00:00:00", "workoutTypeValueId": 2, "title": "CY NFR 60M",
     "totalTimePlanned": 1.0, "tssPlanned": 55.0, "workoutSubTypeId": 6, "coachComments": "spin",
     "structure": {"structure": [{"x": 1}]}, "orderOnDay": 2},
    {"workoutId": 13, "workoutDay": "2018-12-25T00:00:00", "workoutTypeValueId": 1, "title": "SW TPK 3p0K",
     "distancePlanned": 3000.0, "orderOnDay": 1},
]


def _card_router(before=(), after=(), fail_reads=False):
    """Plan reads, then the target day: ``before`` on the first read, ``after`` on the next."""
    reads = {"n": 0}

    def route(ep, **k):
        if ep.startswith("/plans/v1/plans/") and "/workouts/" in ep:
            return APIResponse(success=True, data=_CARDS)
        if ep.startswith("/plans/"):
            return APIResponse(success=True, data=_DETAIL)
        reads["n"] += 1
        if fail_reads and reads["n"] > 1:
            return APIResponse(success=False, message="timeout")
        return APIResponse(success=True, data=list(before if reads["n"] == 1 else after))

    return route


@pytest.fixture
def as_athlete():
    token = athlete_override.set("1472902")
    yield
    athlete_override.reset(token)


async def _copy(inst, *args, **kwargs):
    p = _patch(inst)
    try:
        return await tp_copy_plan_workout(*args, **kwargs)
    finally:
        p.stop()


EXISTING = {"workoutId": 5, "title": "REST", "isHidden": None}


@pytest.mark.asyncio
async def test_copy_plan_workout_hidden_by_default_and_verified(as_athlete):
    after = [EXISTING, {"workoutId": 999, "title": "CY NFR 60M", "isHidden": True}]
    inst = _client_with(_card_router([EXISTING], after), post=APIResponse(success=True, data={"workoutId": 999}))
    r = await _copy(inst, 163992, 12, "2026-10-07")
    assert r["success"] is True and r["created"] is True and r["verified"] is True and r["workout_id"] == 999
    payload = inst.post.call_args.kwargs["json"]
    assert payload["isHidden"] is True
    assert payload["workoutDay"] == "2026-10-07T00:00:00"
    assert payload["title"] == "CY NFR 60M" and payload["workoutSubTypeId"] == 6
    assert payload["coachComments"] == "spin" and payload["structure"] == '{"structure": [{"x": 1}]}'
    day_reads = [c for c in inst.get.call_args_list if c.args[0].endswith("/workouts/2026-10-07/2026-10-07")]
    assert len(day_reads) == 2 and all(c.kwargs.get("cache") is False for c in day_reads)


@pytest.mark.asyncio
async def test_copy_plan_workout_refuses_without_athlete():
    inst = _client_with(_card_router())
    r = await _copy(inst, 163992, 12, "2026-10-07")
    assert r["error_code"] == "VALIDATION_ERROR" and "athlete" in r["message"]
    inst.post.assert_not_called()


@pytest.mark.asyncio
async def test_copy_plan_workout_created_but_visible_is_not_verified(as_athlete):
    after = [{"workoutId": 999, "title": "CY NFR 60M", "isHidden": False}]
    inst = _client_with(_card_router([], after), post=APIResponse(success=True, data={"workoutId": 999}))
    r = await _copy(inst, 163992, 12, "2026-10-07")
    assert r["created"] is True and r["verified"] is False and "do NOT re-copy" in r["message"]


@pytest.mark.asyncio
async def test_copy_plan_workout_missing_after_post(as_athlete):
    # TP returned an id but the day doesn't show it yet: unknown, never "not created".
    inst = _client_with(_card_router([], []), post=APIResponse(success=True, data={"workoutId": 999}))
    r = await _copy(inst, 163992, 12, "2026-10-07")
    assert r["created"] is None and r["verified"] is False and "Do NOT re-copy" in r["message"]
    # No id and nothing new on the day: genuinely not created.
    inst = _client_with(_card_router([], []), post=APIResponse(success=True, data={}))
    r = await _copy(inst, 163992, 12, "2026-10-07")
    assert r["created"] is False


@pytest.mark.asyncio
async def test_copy_plan_workout_post_error_not_found_is_unknown(as_athlete):
    inst = _client_with(_card_router([], []), post=APIResponse(success=False, message="timeout"))
    r = await _copy(inst, 163992, 12, "2026-10-07")
    assert r["isError"] is True and r["created"] is None


@pytest.mark.asyncio
async def test_copy_plan_workout_post_error_but_created_is_reported_created(as_athlete):
    # e.g. a timeout after the server saved it: no id in the response, but the diff finds it.
    after = [{"workoutId": 1000, "title": "CY NFR 60M", "isHidden": True}]
    inst = _client_with(_card_router([], after), post=APIResponse(success=False, message="timeout"))
    r = await _copy(inst, 163992, 12, "2026-10-07")
    assert r["created"] is True and r["verified"] is True and r["workout_id"] == 1000


@pytest.mark.asyncio
async def test_copy_plan_workout_unreadable_after_is_unknown_not_missing(as_athlete):
    inst = _client_with(_card_router([], [], fail_reads=True), post=APIResponse(success=True, data={"workoutId": 9}))
    r = await _copy(inst, 163992, 12, "2026-10-07")
    assert r["created"] is None and "Do NOT re-copy" in r["message"]


@pytest.mark.asyncio
async def test_copy_plan_workout_rejects_unknown_and_period_cards(as_athlete):
    for wid, code in ((404, "NOT_FOUND"), (11, "VALIDATION_ERROR")):
        inst = _client_with(_card_router())
        r = await _copy(inst, 163992, wid, "2026-10-07")
        assert r["isError"] is True and r["error_code"] == code
        inst.post.assert_not_called()


@pytest.mark.asyncio
async def test_copy_plan_workout_validates_date():
    r = await tp_copy_plan_workout(163992, 12, "not-a-date")  # validated before the athlete check
    assert r["error_code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_plan_workouts_week_filter_exposes_ids():
    inst = _client_with(_card_router())
    p = _patch(inst)
    try:
        r = await tp_get_training_plan_workouts(163992, week=2)
    finally:
        p.stop()
    assert r["week"] == 2 and r["count"] == 1
    card = r["workouts"][0]
    assert card["id"] == 13 and card["weekday"] == "Tue" and card["order_on_day"] == 1
