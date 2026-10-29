"""Draft-plan write tools, end to end through TPClient and the execution guard.

Every request goes to an in-memory httpx.MockTransport fake of the plan endpoints:
no network, synthetic ids only.
"""

import json
import re
from unittest.mock import AsyncMock

import httpx
import pytest

from tp_mcp.client.context import (
    GuardViolationError,
    guarded_execution,
    intent_scope,
)
from tp_mcp.client.http import APIResponse, ErrorCode, TPClient, _is_forbidden
from tp_mcp.tools.plans import (
    tp_add_plan_workout_from_library,
    tp_create_plan_workout,
    tp_create_training_plan,
    tp_delete_plan_workout,
    tp_delete_training_plan,
)

DRAFT = "2.7 week 6 drafts"
DAY = "2026-11-09"
PLAN = {"planId": 77, "title": DRAFT, "startDate": f"{DAY}T00:00:00", "dayCount": 7}
CARD = {
    "planId": 77,
    "workoutId": 3001,
    "workoutDay": f"{DAY}T00:00:00",
    "title": "Old",
    "workoutTypeValueId": 3,
}
ALLOW = [
    ("GET", r"/plans/v1/plans(/\d+(/workouts/[\d-]+/[\d-]+)?)?"),
    (
        "POST",
        r"/plans/v1/plans(/\d+/workouts|/\d+/commands/addworkoutfromlibraryitem)?",
    ),
    ("DELETE", r"/plans/v1/plans/\d+(/workouts/\d+)?"),
]
WORKOUT = {
    "workoutTypeValueId": 2,
    "title": " CY NFR 60M ",
    "description": "steady",
    "coachComments": "  Keep it easy.\nSpin 90+  ",
    "totalTimePlanned": 1.0,
    "distancePlanned": 30000.0,
    "tssPlanned": 55.0,
    "structure": {"structure": [{"x": 1}], "primaryLengthMetric": "duration"},
}


class FakeTP:
    """In-memory plan endpoints. GETs read the state; ``write`` answers the rest."""

    def __init__(self, plans=(PLAN,), workouts=()):
        self.plans = [dict(p) for p in plans]
        self.workouts = [dict(w) for w in workouts]
        self.requests: list[httpx.Request] = []
        self.reads_fail = False
        self.write = lambda request: httpx.Response(200, json={})

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method != "GET":
            return self.write(request)
        if self.reads_fail:
            return httpx.Response(503)
        path = request.url.path
        if path == "/plans/v1/plans":
            return httpx.Response(200, json=self.plans)
        if m := re.fullmatch(r"/plans/v1/plans/(\d+)", path):
            plan = next((p for p in self.plans if p["planId"] == int(m[1])), None)
            return httpx.Response(200, json=plan) if plan else httpx.Response(404)
        if m := re.fullmatch(r"/plans/v1/plans/(\d+)/workouts/([\d-]+)/([\d-]+)", path):
            return httpx.Response(
                200,
                json=[
                    w
                    for w in self.workouts
                    if w["planId"] == int(m[1]) and m[2] <= w["workoutDay"][:10] <= m[3]
                ],
            )
        return httpx.Response(404)

    def sent(self, method=None):
        return [
            (r.method, r.url.path, json.loads(r.content) if r.content else None)
            for r in self.requests
            if method in (None, r.method)
        ]


def make_client(handler):
    client = TPClient()
    client._ensure_access_token = AsyncMock(return_value=APIResponse(success=True))
    client._throttle = AsyncMock()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.fixture(autouse=True)
def _fresh_client_caches(monkeypatch):
    monkeypatch.setattr(TPClient, "_response_cache", None)
    monkeypatch.setattr(TPClient, "_shared_token_cache", None)


@pytest.fixture
def tp(monkeypatch):
    fake = FakeTP()
    monkeypatch.setattr("tp_mcp.tools.plans.TPClient", lambda: make_client(fake))
    return fake


@pytest.fixture
def journal(tmp_path):
    return tmp_path / "journal"


async def run(journal, tool, *args, allow=ALLOW, intent="one"):
    with (
        guarded_execution(
            allowlist=allow,
            body_predicate=lambda method, path, body: True,
            journal_path=journal,
        ),
        intent_scope(intent),
    ):
        return await tool(*args)


def creates_plan(fake, status=200, return_id=True, save=True):
    def write(request):
        if save:
            fake.plans.append(
                {"planId": 901, "title": json.loads(request.content)["title"]}
            )
        return httpx.Response(status, json={"planId": 901} if return_id else {})

    return write


def creates_card(fake, status=200, return_id=True, save=True, **changes):
    def write(request):
        if save:
            body = json.loads(request.content)
            card = {
                "workoutTypeValueId": 3,
                "title": "From library",
            }  # an added library item
            if (
                "structure" in body
            ):  # a direct create: TP returns the structure as an object
                card = {**body, "structure": json.loads(body["structure"])}
            fake.workouts.append(
                {
                    **card,
                    "planId": 77,
                    "workoutId": 3002,
                    "workoutDay": f"{DAY}T00:00:00",
                    **changes,
                }
            )
        return httpx.Response(status, json={"workoutId": 3002} if return_id else {})

    return write


# --- tp_create_training_plan ---------------------------------------------------


async def test_create_plan_exact_wire_body_and_created_true(tp, journal):
    tp.plans = [{"planId": 12, "title": "Kona 2027"}]
    tp.write = creates_plan(tp)
    r = await run(journal, tp_create_training_plan, DRAFT)
    assert r == {"success": True, "created": True, "plan_id": 901, "title": DRAFT}
    assert tp.sent() == [
        ("GET", "/plans/v1/plans", None),
        ("POST", "/plans/v1/plans", {"title": DRAFT, "isDynamic": False}),
        ("GET", "/plans/v1/plans", None),
    ]
    post_response = next(
        e
        for e in records(journal)
        if e["event"] == "response" and e["method"] == "POST"
    )
    assert post_response["raw_ids"] == [901]  # the journal records planId


async def test_create_plan_without_returned_id_adopts_the_only_new_plan(tp, journal):
    tp.plans = []
    tp.write = creates_plan(tp, return_id=False)
    r = await run(journal, tp_create_training_plan, "HC scratch probe 2026-10-30")
    assert r["created"] is True and r["plan_id"] == 901


async def test_create_plan_failed_and_absent_is_not_created(tp, journal):
    tp.plans = []
    tp.write = creates_plan(tp, status=400, save=False)
    r = await run(journal, tp_create_training_plan, DRAFT)
    assert (
        r["isError"] is True
        and r["created"] is False
        and "nothing was created" in r["message"]
    )
    assert len(tp.sent("POST")) == 1


@pytest.mark.parametrize(
    "write",
    [
        lambda fake: creates_plan(fake, save=False),  # id returned, not listed yet
        lambda fake: creates_plan(
            fake, return_id=False, save=False
        ),  # success, nothing listed
        lambda fake: creates_plan(
            fake, status=401, save=False
        ),  # may have reached the server
        lambda fake: creates_plan(
            fake, status=500, save=True
        ),  # server error, then listed: True below
    ],
)
async def test_create_plan_unknown_outcomes_are_null(tp, journal, write):
    tp.plans = []
    tp.write = write(tp)
    r = await run(journal, tp_create_training_plan, DRAFT)
    if any(p["title"] == DRAFT for p in tp.plans):
        assert (
            r["created"] is True and r["plan_id"] == 901
        )  # an error, but the re-read proves it
    else:
        assert r["created"] is None and "do NOT re-send" in r["message"]
    assert len(tp.sent("POST")) == 1


async def test_create_plan_two_matches_or_another_id_are_null(tp, journal):
    def write(request):
        tp.plans += [{"planId": 901, "title": DRAFT}, {"planId": 902, "title": DRAFT}]
        return httpx.Response(200, json={"planId": 901})

    tp.plans, tp.write = [], write
    r = await run(journal, tp_create_training_plan, DRAFT)
    assert r["created"] is None and "uniquely matched" in r["message"]

    def other(request):
        tp.plans = [{"planId": 902, "title": DRAFT}]
        return httpx.Response(200, json={"planId": 901})

    tp.plans, tp.write = [], other
    r = await run(journal, tp_create_training_plan, DRAFT, intent="two")
    assert r["created"] is None and r["plan_id"] == 901


async def test_create_plan_unreadable_after_is_null(tp, journal):
    def write(request):
        tp.reads_fail = True
        return httpx.Response(200, json={"planId": 901})

    tp.plans, tp.write = [], write
    r = await run(journal, tp_create_training_plan, DRAFT)
    assert r["created"] is None


@pytest.mark.parametrize("existing", [DRAFT, f" {DRAFT} "])
async def test_create_plan_duplicate_title_refused_before_any_write(
    tp, journal, existing
):
    tp.plans = [{"planId": 77, "title": existing}]
    r = await run(journal, tp_create_training_plan, DRAFT)
    assert r["error_code"] == "VALIDATION_ERROR" and "already exists" in r["message"]
    assert tp.sent("POST") == []


@pytest.mark.parametrize(
    "title",
    [
        "",
        "Week 6",
        "2.7 week 100 drafts",
        "2.7 week 6 drafts\n",
        " 2.7 week 6 drafts",
        "2.7 week ٦ drafts",  # a non-ASCII digit
        "2x7 week 6 drafts",
        "HC scratch probe 2026-1-30",
        "hc scratch probe 2026-10-30",
        42,
        None,
    ],
)
async def test_create_plan_bad_title_refused_before_any_request(tp, journal, title):
    r = await run(journal, tp_create_training_plan, title)
    assert r["error_code"] == "VALIDATION_ERROR"
    assert tp.requests == []


# --- tp_add_plan_workout_from_library --------------------------------------------


async def test_add_from_library_exact_wire_body_and_created_true(tp, journal):
    tp.workouts = [CARD]
    tp.write = creates_card(tp)
    r = await run(journal, tp_add_plan_workout_from_library, 77, 555, DAY)
    assert r == {
        "success": True,
        "created": True,
        "workout_id": 3002,
        "plan_id": 77,
        "date": DAY,
        "library_item_id": 555,
    }
    day_path = f"/plans/v1/plans/77/workouts/{DAY}/{DAY}"
    assert tp.sent() == [
        ("GET", day_path, None),
        (
            "POST",
            "/plans/v1/plans/77/commands/addworkoutfromlibraryitem",
            {
                "planId": 77,
                "exerciseLibraryItemId": 555,
                "workoutDateTime": f"{DAY}T00:00:00",
            },
        ),
        ("GET", day_path, None),
    ]


async def test_add_from_library_outcomes(tp, journal):
    # No id back and a new card: it cannot be matched to the item, so unknown.
    tp.write = creates_card(tp, return_id=False)
    r = await run(journal, tp_add_plan_workout_from_library, 77, 555, DAY)
    assert r["created"] is None and "uniquely matched" in r["message"]
    # An id back but not on the day yet: unknown.
    tp.workouts, tp.write = [], creates_card(tp, save=False)
    r = await run(journal, tp_add_plan_workout_from_library, 77, 555, DAY, intent="two")
    assert r["created"] is None and r["workout_id"] == 3002
    # A server error and nothing new on the day: not created.
    tp.workouts, tp.write = [], creates_card(tp, status=500, save=False)
    r = await run(
        journal, tp_add_plan_workout_from_library, 77, 555, DAY, intent="three"
    )
    assert r["isError"] is True and r["created"] is False
    # A server error after saving: the returned-id-less card is unknown, never False.
    tp.workouts, tp.write = [], creates_card(tp, status=500, return_id=False)
    r = await run(
        journal, tp_add_plan_workout_from_library, 77, 555, DAY, intent="four"
    )
    assert r["created"] is None


async def test_add_from_library_validates_before_any_request(tp, journal):
    for args in ((0, 555, DAY), (77, -1, DAY), (77, 555, "next monday")):
        r = await run(journal, tp_add_plan_workout_from_library, *args)
        assert r["error_code"] == "VALIDATION_ERROR"
    assert tp.requests == []


# --- tp_create_plan_workout ------------------------------------------------------


async def test_create_plan_workout_exact_wire_body(tp, journal):
    tp.write = creates_card(tp)
    r = await run(journal, tp_create_plan_workout, 77, DAY, WORKOUT)
    assert (
        r["created"] is True and r["workout_id"] == 3002 and r["title"] == "CY NFR 60M"
    )
    [(method, path, body)] = tp.sent("POST")
    assert (method, path) == ("POST", "/plans/v1/plans/77/workouts")
    assert body == {
        "workoutId": 0,
        "workoutDay": f"{DAY}T00:00:00",
        "workoutTypeFamilyId": 2,
        "workoutTypeValueId": 2,
        "title": "CY NFR 60M",
        "description": "steady",
        "coachComments": "  Keep it easy.\nSpin 90+  ",  # verbatim
        "totalTimePlanned": 1.0,
        "distancePlanned": 30000.0,
        "tssPlanned": 55.0,
        "structure": json.dumps(
            WORKOUT["structure"]
        ),  # a JSON string, as on the calendar
    }
    assert "athleteId" not in body


async def test_create_plan_workout_without_id_matches_title_sport_and_time(tp, journal):
    tp.write = creates_card(tp, return_id=False)
    r = await run(journal, tp_create_plan_workout, 77, DAY, WORKOUT)
    assert r["created"] is True and r["workout_id"] == 3002
    tp.workouts, tp.write = [], creates_card(tp, return_id=False, totalTimePlanned=2.0)
    r = await run(journal, tp_create_plan_workout, 77, DAY, WORKOUT, intent="two")
    assert r["created"] is None and r["workout_id"] is None


async def test_create_plan_workout_failed_and_absent_is_not_created(tp, journal):
    tp.write = creates_card(tp, status=400, save=False)
    r = await run(journal, tp_create_plan_workout, 77, DAY, WORKOUT)
    assert r["isError"] is True and r["created"] is False


async def test_create_plan_workout_timeout_after_saving_is_created(tp, journal):
    saved = creates_card(tp, return_id=False)

    def write(request):
        saved(request)
        raise httpx.ReadTimeout("no answer")

    tp.write = write
    r = await run(journal, tp_create_plan_workout, 77, DAY, WORKOUT)
    assert r["created"] is True and r["workout_id"] == 3002
    assert len(tp.sent("POST")) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"isHidden": True},  # unknown key
        {"workoutTypeValueId": 99},
        {"title": "   "},
        {"totalTimePlanned": -1},
        {"tssPlanned": float("inf")},
        {"structure": "[1, 2]"},
        {"structure": "not json"},
    ],
)
async def test_create_plan_workout_validates_before_any_request(tp, journal, change):
    r = await run(journal, tp_create_plan_workout, 77, DAY, {**WORKOUT, **change})
    assert r["error_code"] == "VALIDATION_ERROR"
    assert tp.requests == []


# A card already on the day that matches the create in every field.
SAME_CARD = {
    "planId": 77,
    "workoutId": 3001,
    "workoutDay": f"{DAY}T00:00:00",
    "workoutTypeFamilyId": 2,
    "workoutTypeValueId": 2,
    "title": "CY NFR 60M",
    "totalTimePlanned": 1.0,
    "distancePlanned": 30000.0,
    "tssPlanned": 55.0,
    "structure": WORKOUT["structure"],
}


@pytest.mark.parametrize(
    "tool,args",
    [
        (tp_create_plan_workout, (77, DAY, WORKOUT)),
        (tp_add_plan_workout_from_library, (77, 555, DAY)),
    ],
)
@pytest.mark.parametrize("answer", [{"workoutId": 3001}, {}])  # echoes its id, or none
async def test_a_card_already_on_the_day_is_never_claimed(
    tp, journal, tool, args, answer
):
    tp.workouts = [SAME_CARD]
    tp.write = lambda request: httpx.Response(200, json=answer)
    r = await run(journal, tool, *args)
    assert r["created"] is not True and r["success"] is not True
    assert r["created"] is None
    assert len(tp.sent("POST")) == 1


# --- one dispatch: 401 and timeouts on the three POSTs -------------------------------

POST_TOOLS = [
    (tp_create_training_plan, (DRAFT,)),
    (tp_add_plan_workout_from_library, (77, 555, DAY)),
    (tp_create_plan_workout, (77, DAY, WORKOUT)),
]


@pytest.mark.parametrize("tool,args", POST_TOOLS)
@pytest.mark.parametrize("failure", ["401", "timeout"])
async def test_post_tools_never_retry_and_report_null(tp, journal, tool, args, failure):
    tp.plans = [] if tool is tp_create_training_plan else [PLAN]

    def write(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("no answer")
        return httpx.Response(401)

    tp.write = write
    r = await run(journal, tool, *args)
    expected = ErrorCode.AUTH_EXPIRED if failure == "401" else ErrorCode.NETWORK_ERROR
    assert r["isError"] is True and r["error_code"] == expected.value
    assert r["created"] is None and "do NOT re-send" in r["message"]
    assert len(tp.sent("POST")) == 1
    assert [e["event"] for e in records(journal) if e.get("method") == "POST"] == (
        ["attempt", "dispatched", "response"]
        if failure == "401"
        else ["attempt", "dispatched"]
    )


# --- deletes -------------------------------------------------------------------------


def deletes(fake, status=200, remove=True):
    def write(request):
        if remove:
            if m := re.fullmatch(
                r"/plans/v1/plans/\d+/workouts/(\d+)", request.url.path
            ):
                fake.workouts = [
                    w for w in fake.workouts if w["workoutId"] != int(m[1])
                ]
            else:
                fake.plans = [
                    p for p in fake.plans if f"/{p['planId']}" not in request.url.path
                ]
        return httpx.Response(status)

    return write


async def test_delete_plan_workout_path_and_deleted_true(tp, journal):
    tp.workouts, tp.write = [CARD], deletes(tp)
    r = await run(journal, tp_delete_plan_workout, 77, 3001)
    assert r == {"success": True, "deleted": True, "plan_id": 77, "workout_id": 3001}
    assert tp.sent("DELETE") == [("DELETE", "/plans/v1/plans/77/workouts/3001", None)]


async def test_delete_plan_workout_false_and_null(tp, journal):
    tp.workouts, tp.write = [CARD], deletes(tp, remove=False)
    r = await run(journal, tp_delete_plan_workout, 77, 3001)
    assert r["deleted"] is False and r["success"] is False

    tp.write = deletes(tp, status=500, remove=False)
    r = await run(journal, tp_delete_plan_workout, 77, 3001, intent="two")
    assert r["isError"] is True and r["deleted"] is False

    def unreadable(request):
        tp.reads_fail = True
        return httpx.Response(200)

    tp.write = unreadable
    r = await run(journal, tp_delete_plan_workout, 77, 3001, intent="three")
    assert r["deleted"] is None and "check first" in r["message"]


async def test_delete_plan_workout_failed_but_gone_is_deleted(tp, journal):
    tp.workouts, tp.write = [CARD], deletes(tp, status=500)
    r = await run(journal, tp_delete_plan_workout, 77, 3001)
    assert r["deleted"] is True and r["success"] is True


DELETE_TOOLS = [(tp_delete_plan_workout, (77, 3001)), (tp_delete_training_plan, (77,))]


def unanswered(failure, fake=None, remove=False):
    """A DELETE that gets a 401, or no answer at all; ``remove`` applies it first."""

    def write(request):
        if remove:
            deletes(fake)(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("no answer")
        if failure == "reset":
            raise httpx.RemoteProtocolError("connection reset")
        return httpx.Response(401)

    return write


@pytest.mark.parametrize("tool,args", DELETE_TOOLS)
@pytest.mark.parametrize("failure", ["401", "timeout", "reset"])
async def test_deletes_without_an_answer_and_still_there_are_null(
    tp, journal, tool, args, failure
):
    tp.workouts, tp.write = [CARD], unanswered(failure)
    r = await run(journal, tool, *args)
    expected = ErrorCode.AUTH_EXPIRED if failure == "401" else ErrorCode.NETWORK_ERROR
    assert r["isError"] is True and r["error_code"] == expected.value
    assert r["deleted"] is None and "do NOT re-send, check first" in r["message"]
    assert len(tp.sent("DELETE")) == 1


@pytest.mark.parametrize("tool,args", DELETE_TOOLS)
async def test_deletes_after_a_401_but_gone_are_deleted(tp, journal, tool, args):
    tp.workouts = [CARD]
    tp.write = unanswered("401", tp, remove=True)
    r = await run(journal, tool, *args)
    assert r["deleted"] is True and r["success"] is True
    assert len(tp.sent("DELETE")) == 1


async def test_delete_training_plan_path_and_outcomes(tp, journal):
    tp.write = deletes(tp)
    r = await run(journal, tp_delete_training_plan, 77)
    assert r == {"success": True, "deleted": True, "plan_id": 77}
    assert tp.sent("DELETE") == [("DELETE", "/plans/v1/plans/77", None)]

    tp.plans, tp.write = [PLAN], deletes(tp, status=500, remove=False)
    r = await run(journal, tp_delete_training_plan, 77, intent="two")
    assert r["isError"] is True and r["deleted"] is False

    def unreadable(request):
        tp.reads_fail = True
        return httpx.Response(204)

    tp.write = unreadable
    r = await run(journal, tp_delete_training_plan, 77, intent="three")
    assert r["deleted"] is None


@pytest.mark.parametrize(
    "title", ["Kona 2027", f"{DRAFT} ", "2.7 week 6 drafts (copy)", None]
)
@pytest.mark.parametrize(
    "tool,args",
    [(tp_delete_plan_workout, (77, 3001)), (tp_delete_training_plan, (77,))],
)
async def test_deletes_refuse_plans_without_a_draft_title(
    tp, journal, tool, args, title
):
    tp.plans, tp.workouts = [{**PLAN, "title": title}], [CARD]
    r = await run(journal, tool, *args)
    assert (
        r["error_code"] == "VALIDATION_ERROR" and "nothing was deleted" in r["message"]
    )
    assert tp.sent("DELETE") == []


async def test_deletes_refuse_unlisted_plans_and_missing_cards(tp, journal):
    r = await run(journal, tp_delete_training_plan, 78)
    assert r["error_code"] == "NOT_FOUND"
    r = await run(
        journal, tp_delete_plan_workout, 77, 3001
    )  # the plan has no such card
    assert r["error_code"] == "NOT_FOUND"
    assert tp.sent("DELETE") == []


async def test_delete_needs_the_guard_to_name_the_exact_path(tp, journal):
    allow = [ALLOW[0], ("DELETE", r"/plans/v1/plans/78")]
    with pytest.raises(GuardViolationError, match="allowlist"):
        await run(journal, tp_delete_training_plan, 77, allow=allow)
    assert tp.sent("DELETE") == []


# --- every tool: the guard, and no calendar requests -------------------------------

ALL_TOOLS = [
    *POST_TOOLS,
    (tp_delete_plan_workout, (77, 3001)),
    (tp_delete_training_plan, (77,)),
]


@pytest.mark.parametrize("tool,args", ALL_TOOLS)
async def test_every_tool_refuses_without_a_guard(tp, tool, args):
    r = await tool(*args)
    assert r["error_code"] == "GUARD_REQUIRED"
    assert tp.requests == []


@pytest.mark.parametrize("tool,args", ALL_TOOLS)
async def test_no_tool_touches_the_calendar(tp, journal, tool, args):
    if tool is tp_create_training_plan:
        tp.plans, tp.write = [], creates_plan(tp)
    elif tool in (tp_delete_plan_workout, tp_delete_training_plan):
        tp.workouts, tp.write = [CARD], deletes(tp)
    else:
        tp.write = creates_card(tp)
    r = await run(journal, tool, *args)
    assert r["success"] is True
    assert tp.requests and all(
        r.url.path.startswith("/plans/v1/plans") for r in tp.requests
    )
    assert not any("/fitness/" in r.url.path for r in tp.requests)


async def test_server_handlers_are_wired(tp):
    from tp_mcp.server import _TOOL_HANDLERS

    calls = {
        "tp_create_training_plan": {"title": DRAFT},
        "tp_add_plan_workout_from_library": {
            "plan_id": 77,
            "library_item_id": 555,
            "target_date": DAY,
        },
        "tp_create_plan_workout": {
            "plan_id": 77,
            "target_date": DAY,
            "workout": WORKOUT,
        },
        "tp_delete_plan_workout": {"plan_id": 77, "workout_id": 3001},
        "tp_delete_training_plan": {"plan_id": 77},
    }
    for name, args in calls.items():
        assert (await _TOOL_HANDLERS[name](args))[
            "error_code"
        ] == "GUARD_REQUIRED", name
    assert "tp_apply_training_plan" not in _TOOL_HANDLERS
    assert tp.requests == []


# --- client: one dispatch, forbidden paths, journal ids -------------------------------


@pytest.mark.parametrize(
    "method,sends", [("POST", 1), ("PUT", 1), ("DELETE", 1), ("GET", 2)]
)
async def test_unguarded_plan_writes_are_never_retried_on_401(method, sends):
    sent = []
    client = make_client(lambda request: sent.append(request) or httpx.Response(401))
    async with client:
        r = await client._request(method, "/plans/v1/plans/77/workouts/3001")
    assert r.error_code == ErrorCode.AUTH_EXPIRED and len(sent) == sends


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
@pytest.mark.parametrize(
    "path,raw_path,sends",
    [
        ("/foo/../plans/v1/plans", b"/plans/v1/plans", 1),
        ("/%70lans/v1/plans", b"/%70lans/v1/plans", 1),
        ("/plans/v1/plans", b"/plans/v1/plans", 1),
        ("/fitness/v6/athletes/1/workouts", b"/fitness/v6/athletes/1/workouts", 2),
        ("/foo%2fbar/../plans/v1/plans", b"/plans/v1/plans", 1),
    ],
)
async def test_retry_uses_the_normalised_request_path(method, path, raw_path, sends):
    sent = []
    client = make_client(lambda request: sent.append(request) or httpx.Response(401))
    assert client._client.build_request(method, client.base_url + path).url.raw_path == raw_path
    async with client:
        result = await client._request(method, path)
    assert result.error_code == ErrorCode.AUTH_EXPIRED
    assert [request.url.raw_path for request in sent] == [raw_path] * sends


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
async def test_guard_one_dispatch_covers_plan_put_and_delete(journal, method):
    path = "/plans/v1/plans/77/workouts/3001"
    sent = []
    client = make_client(lambda request: sent.append(request) or httpx.Response(200))
    async with client:
        with (
            guarded_execution(
                allowlist=[(method, path)],
                body_predicate=lambda *a: True,
                journal_path=journal,
            ),
            intent_scope("one"),
        ):
            assert (await client._request(method, path)).success
            with pytest.raises(GuardViolationError, match="dispatched"):
                await client._request(method, path)
    assert len(sent) == 1
    assert [e["event"] for e in records(journal)] == [
        "attempt",
        "dispatched",
        "response",
    ]


async def test_guard_one_dispatch_leaves_other_deletes_alone(journal):
    path = "/fitness/v6/athletes/1000001/workouts/2001"
    sent = []
    client = make_client(lambda request: sent.append(request) or httpx.Response(200))
    async with client:
        with (
            guarded_execution(
                allowlist=[("DELETE", path)],
                body_predicate=lambda *a: True,
                journal_path=journal,
            ),
            intent_scope("one"),
        ):
            for _ in range(2):
                assert (await client.delete(path)).success
    assert len(sent) == 2


@pytest.mark.parametrize(
    "path",
    [
        "/plans/v1/commands/applyplan",
        "/plans/v1/commands/ApplyPlan",
        "/plans/v1/commands/copyplan",
        "/plans/v1/commands/CopyPlan",
        "/product/v2/Product",
        "/Product/v2/product/9001",
        # The wire can retain percent escapes; servers may decode them.
        "/plans/v1/commands/apply%70lan",
        "/plans/v1/commands/%41pply%50lan",
        "/plans/v1/commands/%63opyplan",
        "/product%2Fv2/Product",
        "/plans/v1/commands/copyplan/?x=1",
        "/product/v2/Product?x=1",
        # Decoded until stable, whatever the server does.
        "/plans/v1/commands/%2561pplyplan",
        "/plans/v1/commands/%252563opyplan",
        "/plans/v1/plans/%252525252541",  # still changing after 5 decodes: fail closed
        "/plans/v1/plans/../commands/applyplan",
        "/plans/v1/commands/./applyplan",
        "/plans/v1/plans/../commands/copyplan",
        "/plans/v1/commands/./copyplan",
        "/plans/v1/commands/%2e/applyplan",
        "/plans/v1/plans/%252e%252e/commands/copyplan",
        "/foo%2fbar/../plans/v1/commands/applyplan",
    ],
)
async def test_forbidden_paths_are_never_sent(path):
    sent = []
    client = make_client(lambda request: sent.append(request) or httpx.Response(200))
    async with client:
        for method in ("GET", "POST", "PUT", "DELETE"):
            r = await client._request(method, path, json={"planId": 77})
            assert r.error_code == ErrorCode.FORBIDDEN_ENDPOINT
        assert (await client.get_raw(path)).error_code == ErrorCode.FORBIDDEN_ENDPOINT
    assert sent == []


@pytest.mark.parametrize(
    "path",
    [
        "/plans/v1/plans",
        f"/plans/v1/plans/77/workouts/{DAY}/{DAY}",
        "/fitness/v6/athletes/1000001/workouts",
        "/plans/v1/plans/%2525252541",  # stable after exactly 5 decodes
        "/plans/v1/plans?title=my%20product%2Fplan",
        "/plans/v1/plans#product/v2/Product",
        "/plans/v1/plans?title=%252525252541#product/",
        "/plans/v1/appliedplans/applyPlanStatus",
    ],
)
async def test_allowed_paths_still_send(path):
    sent = []
    client = make_client(lambda request: sent.append(request) or httpx.Response(200))
    async with client:
        assert (await client._request("POST", path, json={})).success
    assert len(sent) == 1


async def test_guarded_encoded_forbidden_path_is_refused_before_send(journal):
    path = "/plans/v1/commands/apply%70lan"
    sent = []
    client = make_client(lambda request: sent.append(request) or httpx.Response(200))
    async with client:
        with (
            guarded_execution(
                allowlist=[("POST", r".*")],
                body_predicate=lambda *a: True,
                journal_path=journal,
            ),
            intent_scope("one"),
            pytest.raises(GuardViolationError, match="Non-canonical"),
        ):
            await client.post(path, json=[{"planId": 77}])
    assert sent == []


@pytest.mark.parametrize(
    "path",
    [
        "/plans/v1/plans",
        "/plans/v1/plans/77",
        "/plans/v1/plans/77/workouts",
        "/plans/v1/plans/77/workouts/3001",
        "/plans/v1/plans/77/commands/addworkoutfromlibraryitem",
    ],
)
def test_draft_plan_paths_are_not_forbidden(path):
    assert not _is_forbidden(path)


def test_journal_records_plan_ids(journal):
    with (
        guarded_execution(
            allowlist=[], body_predicate=lambda *a: True, journal_path=journal
        ) as guard,
        intent_scope("one"),
    ):
        guard.response(
            {"intent_id": "one"},
            200,
            {"planId": 77, "workouts": [{"workoutId": 3001, "planId": 77}]},
        )
    assert records(journal)[-1]["raw_ids"] == [77, 3001]
