"""Offline HTTP-boundary checks for the Head Coach execution guard."""

import asyncio
import hashlib
import json
import os
from unittest.mock import AsyncMock

import httpx
import pytest

from tp_mcp.client.context import (
    GuardViolationError,
    athlete_override,
    current_intent,
    execution_guard,
    guarded_execution,
    intent_scope,
    require_guard,
)
from tp_mcp.client.http import APIResponse, ErrorCode, TPClient
from tp_mcp.tools.workouts import tp_create_workout

PATH = "/fitness/v6/athletes/2594040/workouts"
BODY = {"athleteId": 2594040, "workoutDay": "2026-10-12", "isHidden": True}


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def guard(path, allowlist=None):
    return guarded_execution(
        journal_path=path,
        allowlist=allowlist
        if allowlist is not None
        else [("POST", PATH), ("GET", PATH)],
        body_predicate=lambda method, path, body: method == "GET" or body == BODY,
    )


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(TPClient, "_response_cache", None)
    monkeypatch.setattr(TPClient, "_shared_token_cache", None)
    client = TPClient()
    monkeypatch.setattr(
        client,
        "_ensure_access_token",
        AsyncMock(return_value=APIResponse(success=True)),
    )
    monkeypatch.setattr(client, "_throttle", AsyncMock())
    return client


def transport(client, handler):
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("POST", PATH + "/extra", BODY),
        ("POST", PATH.replace("2594040", "1653162"), BODY),
        ("POST", PATH, {**BODY, "isHidden": False}),
        ("POST", PATH, {**BODY, "workoutDay": "2026-10-13"}),
        ("PUT", PATH, BODY),
        ("DELETE", PATH, None),
    ],
)
async def test_refused_before_auth_or_send(client, tmp_path, method, path, body):
    with (
        guard(tmp_path / "journal"),
        intent_scope("one"),
        pytest.raises(GuardViolationError),
    ):
        await client._request(method, path, json=body)
    client._ensure_access_token.assert_not_awaited()
    assert client._client is None


async def test_fsynced_dispatch_before_send_and_response_before_handler(
    client, tmp_path, monkeypatch
):
    journal = tmp_path / "journal"
    synced = []
    real_fsync = os.fsync

    def fsync(fd):
        real_fsync(fd)
        synced.append(records(journal)[-1]["event"])

    monkeypatch.setattr(os, "fsync", fsync)

    def send(request):
        entry = records(journal)[-1]
        assert entry["event"] == "dispatched"
        assert entry["intent_id"] == "one"
        assert entry["method"] == "POST" and entry["path"] == PATH
        assert (
            entry["body_sha256"]
            == hashlib.sha256(
                json.dumps(BODY, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
        )
        assert json.loads(request.content) == BODY
        assert synced == ["attempt", "dispatched"]
        return httpx.Response(201, json={"workoutId": 42})

    transport(client, send)
    original = client._handle_response

    def handle(response):
        assert records(journal)[-1]["raw_ids"] == [42]
        assert records(journal)[-1]["status"] == 201
        assert synced[-1] == "response"
        return original(response)

    monkeypatch.setattr(client, "_handle_response", handle)
    async with client:
        with guard(journal), intent_scope("one"):
            assert (await client.post(PATH, json=BODY)).success


@pytest.mark.parametrize("failure_event", ["attempt", "dispatched", "response"])
async def test_journal_failure_blocks_send_or_return(
    client, tmp_path, monkeypatch, failure_event
):
    journal = tmp_path / "journal"
    sent = []

    def fsync(fd):
        if records(journal)[-1]["event"] == failure_event:
            raise OSError("disk failure")

    monkeypatch.setattr(os, "fsync", fsync)
    transport(
        client,
        lambda request: (
            sent.append(request) or httpx.Response(201, json={"workoutId": 42})
        ),
    )
    async with client:
        with (
            guard(journal),
            intent_scope("one"),
            pytest.raises(OSError, match="disk failure"),
        ):
            await client.post(PATH, json=BODY)
    assert len(sent) == (1 if failure_event == "response" else 0)


@pytest.mark.parametrize(
    "method,expected_sends", [("POST", 1), ("GET", 2), ("DELETE", 1)]
)
async def test_auth_retry_only_get_when_guarded(
    client, tmp_path, method, expected_sends
):
    sent = []
    transport(
        client,
        lambda request: (
            sent.append(request) or httpx.Response(401, json={"workoutId": 42})
        ),
    )
    journal = tmp_path / "journal"
    async with client:
        with guard(journal, [(method, PATH)]), intent_scope("one"):
            response = await client._request(method, PATH, json=BODY)
    assert response.error_code == ErrorCode.AUTH_EXPIRED
    assert len(sent) == expected_sends
    assert [r["raw_ids"] for r in records(journal) if r["event"] == "response"] == [
        [42]
    ] * expected_sends


async def test_attempt_ceiling_restored_and_gets_do_not_count(client, tmp_path):
    journal = tmp_path / "journal"
    transport(client, lambda request: httpx.Response(200, json=[]))
    async with client:
        for _ in range(2):
            with guard(journal), intent_scope("one"):
                assert (await client.get(PATH, cache=False)).success
                with pytest.raises(GuardViolationError, match="allowlist"):
                    await client.post(PATH, json={})
        with (
            guard(journal),
            intent_scope("one"),
            pytest.raises(GuardViolationError, match="ceiling"),
        ):
            await client.post(PATH, json=BODY)
    assert len([r for r in records(journal) if r["event"] == "attempt"]) == 2
    assert all(
        r["method"] == "GET" for r in records(journal) if r["event"] == "dispatched"
    )


async def test_pre_auth_failure_can_retry_once(client, tmp_path):
    client._ensure_access_token.side_effect = [
        APIResponse(success=False),
        APIResponse(success=True),
    ]
    sent = []
    transport(
        client,
        lambda request: (
            sent.append(request) or httpx.Response(201, json={"workoutId": 42})
        ),
    )
    journal = tmp_path / "journal"
    async with client:
        with guard(journal), intent_scope("one"):
            assert not (await client.post(PATH, json=BODY)).success
        with guard(journal), intent_scope("one"):
            assert (await client.post(PATH, json=BODY)).success
    assert len(sent) == 1
    assert [r["attempt"] for r in records(journal) if r["event"] == "attempt"] == [1, 2]


@pytest.mark.parametrize("timeout", [False, True])
async def test_dispatch_blocks_replay_across_contexts(client, tmp_path, timeout):
    sent = []

    def send(request):
        sent.append(request)
        if timeout:
            raise httpx.ReadTimeout("unknown result")
        return httpx.Response(201, json={"workoutId": 42})

    transport(client, send)
    journal = tmp_path / "journal"
    async with client:
        with guard(journal), intent_scope("one"):
            await client.post(PATH, json=BODY)
        with (
            guard(journal),
            intent_scope("one"),
            pytest.raises(GuardViolationError, match="dispatched"),
        ):
            await client.post(PATH, json=BODY)
    assert len(sent) == 1


@pytest.mark.parametrize("error", [RuntimeError, asyncio.CancelledError])
async def test_scopes_reset_on_exception_and_cancellation(tmp_path, error):
    with guard(tmp_path / "outer"), intent_scope("outer"):
        outer = require_guard()
        with pytest.raises(error), guard(tmp_path / "inner"), intent_scope("inner"):
            assert current_intent.get() == "inner"
            raise error()
        assert current_intent.get() == "outer" and require_guard() is outer
    assert current_intent.get() is None and execution_guard.get() is None


async def test_placer_requires_guard_before_mutation(client):
    sent = []
    transport(client, lambda request: sent.append(request) or httpx.Response(201))

    async def place():
        require_guard()
        return await client.post(PATH, json=BODY)

    async with client:
        with pytest.raises(GuardViolationError, match="required"):
            await place()
    assert sent == []


async def test_inactive_post_retains_retry_and_body(client):
    sent = []
    transport(client, lambda request: sent.append(request) or httpx.Response(401))
    async with client:
        assert (await client.post(PATH, json=BODY)).error_code == ErrorCode.AUTH_EXPIRED
    assert len(sent) == 2
    assert (
        sent[0].content
        == sent[1].content
        == httpx.Request("POST", "https://example.test", json=BODY).content
    )


async def test_raw_and_cached_get_cannot_bypass_allowlist(client, tmp_path):
    with guard(tmp_path / "journal", []):
        with pytest.raises(GuardViolationError):
            await client.get(PATH)
        with pytest.raises(GuardViolationError):
            await client.get_raw(PATH)
    client._ensure_access_token.assert_not_awaited()


async def test_missing_intent_and_corrupt_journal_fail_closed(client, tmp_path):
    journal = tmp_path / "journal"
    with guard(journal), pytest.raises(GuardViolationError, match="intent"):
        await client.post(PATH, json=BODY)
    journal.write_text('{"event":"dispatched"')
    with (
        pytest.raises(GuardViolationError, match="journal"),
        guard(journal),
        intent_scope("one"),
    ):
        await client.post(PATH, json=BODY)
    assert client._client is None


async def test_real_task_cancellation_resets_scopes_before_dispatch(client, tmp_path):
    waiting = asyncio.Event()
    cleaned = []

    async def throttle():
        waiting.set()
        await asyncio.Event().wait()

    client._throttle.side_effect = throttle
    sent = []
    transport(client, lambda request: sent.append(request) or httpx.Response(201))
    journal = tmp_path / "journal"

    async def place():
        try:
            with guard(journal), intent_scope("cancelled"):
                await client.post(PATH, json=BODY)
        finally:
            cleaned.append((execution_guard.get(), current_intent.get()))

    async with client:
        task = asyncio.create_task(place())
        await waiting.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert cleaned == [(None, None)] and sent == []
    assert [r["event"] for r in records(journal)] == ["attempt"]


async def test_concurrent_posts_recheck_dispatch_after_throttle(client, tmp_path):
    ready = asyncio.Event()
    arrivals = 0

    async def throttle():
        nonlocal arrivals
        arrivals += 1
        if arrivals == 2:
            ready.set()
        await ready.wait()

    client._throttle.side_effect = throttle
    sent = []
    transport(
        client,
        lambda request: (
            sent.append(request) or httpx.Response(201, json={"workoutId": 42})
        ),
    )
    async with client:
        with guard(tmp_path / "journal"), intent_scope("one"):
            results = await asyncio.gather(
                client.post(PATH, json=BODY),
                client.post(PATH, json=BODY),
                return_exceptions=True,
            )
    assert len(sent) == 1
    assert sum(isinstance(result, GuardViolationError) for result in results) == 1


async def test_body_is_frozen_before_async_work(client, tmp_path):
    body = dict(BODY)

    async def throttle():
        body["athleteId"] = 1653162

    client._throttle.side_effect = throttle
    sent = []
    transport(
        client,
        lambda request: sent.append(json.loads(request.content)) or httpx.Response(201),
    )
    async with client:
        with guard(tmp_path / "journal"), intent_scope("one"):
            assert (await client.post(PATH, json=body)).success
    assert sent == [BODY]


@pytest.mark.parametrize(
    "body,ids",
    [
        ({"exerciseLibraryId": 10}, [10]),
        ({"data": [{"exerciseLibraryItemId": "20"}, {"id": 21}]}, ["20", 21]),
        (42, [42]),
        ("42", ["42"]),
        ([42, "43", 42], [42, "43"]),
        ({"workoutId": 42, "userTags": ["100", "200"]}, [42]),
        ({"workoutId": 42, "userTags": [100, 200]}, [42]),
        ({"data": [{"workoutId": 42, "userTags": ["100", 200]}]}, [42]),
        ({"userTags": ["100", 200]}, []),
        (None, []),
    ],
)
async def test_raw_resource_ids_survive_response_shapes(client, tmp_path, body, ids):
    transport(client, lambda request: httpx.Response(200, json=body))
    journal = tmp_path / "journal"
    async with client:
        with guard(journal), intent_scope("one"):
            await client.post(PATH, json=BODY)
    assert records(journal)[-1]["raw_ids"] == ids


async def test_token_exchange_also_obeys_allowlist_and_journal(
    client, tmp_path, monkeypatch
):
    from tp_mcp.auth.keyring import CredentialResult

    monkeypatch.setattr(
        "tp_mcp.client.http.get_credential",
        lambda: CredentialResult(success=True, cookie="fake", message="test"),
    )
    sent = []
    transport(
        client,
        lambda request: (
            sent.append(request)
            or httpx.Response(
                200, json={"success": True, "token": {"access_token": "fake-secret"}}
            )
        ),
    )
    journal = tmp_path / "journal"
    async with client:
        with guard(journal, []), pytest.raises(GuardViolationError):
            await client._exchange_cookie_for_token()
        with guard(journal, [("GET", "/users/v3/token")]):
            assert (await client._exchange_cookie_for_token()).success
    assert len(sent) == 1
    assert [r["event"] for r in records(journal)] == ["dispatched", "response"]
    assert "fake-secret" not in journal.read_text()


async def test_guarded_get_ignores_existing_cache_and_journals_raw_reads(
    client, tmp_path
):
    sent = []
    transport(
        client,
        lambda request: (
            sent.append(request) or httpx.Response(200, json={"workoutId": len(sent)})
        ),
    )
    journal = tmp_path / "journal"
    async with client:
        await client.get(PATH)
        with guard(journal):
            response = await client.get(PATH)
            assert response.data == {"workoutId": 2}
            assert (await client.get_raw(PATH)).success
    assert len(sent) == 3
    assert [r["raw_ids"] for r in records(journal) if r["event"] == "response"] == [
        [2],
        [3],
    ]


async def test_direct_create_handler_runs_through_guard(client, tmp_path, monkeypatch):
    wire_body = {
        **BODY,
        "workoutDay": "2026-10-12T00:00:00",
        "title": "probe",
        "workoutTypeFamilyId": 2,
        "workoutTypeValueId": 2,
        "totalTimePlanned": 1.0,
    }
    monkeypatch.setattr(
        client,
        "_get_user_data",
        AsyncMock(
            return_value={"personId": 1456247, "athletes": [{"athleteId": 2594040}]}
        ),
    )
    monkeypatch.setattr("tp_mcp.tools.workouts.TPClient", lambda: client)
    journal = tmp_path / "journal"

    def send(request):
        assert records(journal)[-1]["event"] == "dispatched"
        assert json.loads(request.content) == wire_body
        return httpx.Response(201, json={"workoutId": 42})

    transport(client, send)
    token = athlete_override.set("2594040")
    try:
        with (
            guarded_execution(
                allowlist=[("POST", PATH)],
                journal_path=journal,
                body_predicate=lambda method, path, body: body == wire_body,
            ),
            intent_scope("one"),
        ):
            require_guard()
            result = await tp_create_workout(
                date_str="2026-10-12",
                sport="Bike",
                title="probe",
                duration_minutes=60,
                is_hidden=True,
            )
    finally:
        athlete_override.reset(token)
    assert result.get("workout_id") == 42, result
    assert records(journal)[-1]["raw_ids"] == [42]
