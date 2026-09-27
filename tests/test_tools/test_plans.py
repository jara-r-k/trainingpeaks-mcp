"""Tests for training-plan tools (list/get/workouts/apply)."""

from unittest.mock import AsyncMock, patch

import pytest

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


def _card_router(saved_day=None):
    def route(ep, **k):
        if ep.startswith("/plans/v1/plans/") and "/workouts/" in ep:
            return APIResponse(success=True, data=_CARDS)
        if ep.startswith("/plans/"):
            return APIResponse(success=True, data=_DETAIL)
        return APIResponse(success=True, data=saved_day if saved_day is not None else [])
    return route


@pytest.mark.asyncio
async def test_copy_plan_workout_hidden_by_default_and_verified():
    post = APIResponse(success=True, data={"workoutId": 999})
    inst = _client_with(_card_router([{"workoutId": 999, "isHidden": True}]), post=post)
    p = _patch(inst)
    try:
        r = await tp_copy_plan_workout(163992, 12, "2026-10-07")
    finally:
        p.stop()
    assert r["success"] is True and r["verified"] is True and r["workout_id"] == 999
    payload = inst.post.call_args.kwargs["json"]
    assert payload["isHidden"] is True
    assert payload["workoutDay"] == "2026-10-07T00:00:00"
    assert payload["title"] == "CY NFR 60M" and payload["workoutSubTypeId"] == 6
    assert payload["coachComments"] == "spin" and payload["structure"] == '{"structure": [{"x": 1}]}'
    # Stick check re-reads the target day without the cache.
    assert inst.get.call_args_list[-1].kwargs.get("cache") is False
    assert inst.get.call_args_list[-1].args[0].endswith("/workouts/2026-10-07/2026-10-07")


@pytest.mark.asyncio
async def test_copy_plan_workout_not_verified_when_missing_or_visible():
    for saved in ([], [{"workoutId": 999, "isHidden": False}]):
        inst = _client_with(_card_router(saved), post=APIResponse(success=True, data={"workoutId": 999}))
        p = _patch(inst)
        try:
            r = await tp_copy_plan_workout(163992, 12, "2026-10-07")
        finally:
            p.stop()
        assert r["success"] is False and r["verified"] is False and "not confirmed" in r["message"]


@pytest.mark.asyncio
async def test_copy_plan_workout_rejects_unknown_and_period_cards():
    for wid, code in ((404, "NOT_FOUND"), (11, "VALIDATION_ERROR")):
        inst = _client_with(_card_router())
        p = _patch(inst)
        try:
            r = await tp_copy_plan_workout(163992, wid, "2026-10-07")
        finally:
            p.stop()
        assert r["isError"] is True and r["error_code"] == code
        inst.post.assert_not_called()


@pytest.mark.asyncio
async def test_copy_plan_workout_validates_date():
    r = await tp_copy_plan_workout(163992, 12, "not-a-date")
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
