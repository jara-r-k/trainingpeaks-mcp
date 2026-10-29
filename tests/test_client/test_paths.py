"""Safety paths agree with locally built httpx requests; nothing is sent."""

import httpx
import pytest

from tp_mcp.client.context import GuardViolationError, guarded_execution, intent_scope, is_plan_write
from tp_mcp.client.paths import normalise_path


@pytest.mark.parametrize(
    "endpoint,raw_path,normalised",
    [
        ("/plans/v1/plans/../commands/applyplan", b"/plans/v1/commands/applyplan", "/plans/v1/commands/applyplan"),
        ("/plans/v1/commands/./applyplan", b"/plans/v1/commands/applyplan", "/plans/v1/commands/applyplan"),
        ("/plans/v1/plans/../commands/copyplan", b"/plans/v1/commands/copyplan", "/plans/v1/commands/copyplan"),
        ("/plans/v1/commands/./copyplan", b"/plans/v1/commands/copyplan", "/plans/v1/commands/copyplan"),
        ("/foo/../plans/v1/plans", b"/plans/v1/plans", "/plans/v1/plans"),
        ("/%70lans/v1/plans", b"/%70lans/v1/plans", "/plans/v1/plans"),
        ("/foo%2fbar/../plans/v1/plans", b"/plans/v1/plans", "/plans/v1/plans"),
        ("/plans/v1/plans?title=my%20product%2Fplan", b"/plans/v1/plans?title=my%20product%2Fplan", "/plans/v1/plans"),
        ("/plans/v1/plans#product/", b"/plans/v1/plans", "/plans/v1/plans"),
        ("/plans/%2e/v1/plans", b"/plans/%2e/v1/plans", "/plans/v1/plans"),
        ("/foo/%252e%252e/plans/v1/plans", b"/foo/%252e%252e/plans/v1/plans", "/plans/v1/plans"),
        ("/../../plans//v1/plans/.", b"/plans//v1/plans", "/plans//v1/plans"),
        ("/Plans/v1/plans/..", b"/Plans/v1", "/plans/v1"),
        ("/plans/v1/plans/%2525252541", b"/plans/v1/plans/%2525252541", "/plans/v1/plans/a"),
        ("/plans/v1/plans/%3Fproduct%2F", b"/plans/v1/plans/%3Fproduct%2F", "/plans/v1/plans/?product/"),
        ("/plans/v1/plans/%23product%2F", b"/plans/v1/plans/%23product%2F", "/plans/v1/plans/#product/"),
    ],
)
def test_normalised_path_matches_httpx_wire_path(endpoint, raw_path, normalised):
    request = httpx.Request("POST", "https://example.test" + endpoint)
    assert request.url.raw_path == raw_path
    assert normalise_path(endpoint) == normalised
    assert normalise_path(raw_path.decode("ascii")) == normalised


def test_unstable_path_cannot_prove_a_write_is_retryable():
    path = "/%252525252541/v1/plans"
    assert normalise_path(path) is None
    assert is_plan_write("PUT", path)
    assert not is_plan_write("GET", path)


@pytest.mark.parametrize("path", ["/foo/../plans/v1/plans", "/%70lans/v1/plans"])
def test_guard_keeps_rejecting_noncanonical_paths(tmp_path, path):
    with (
        guarded_execution(
            allowlist=[("GET", r".*")],
            body_predicate=lambda *args: True,
            journal_path=tmp_path / "journal",
        ) as guard,
        pytest.raises(GuardViolationError, match="Non-canonical"),
    ):
        guard.check("GET", path, None)


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
@pytest.mark.parametrize("path", ["/foo/../plans/v1/plans", "/%70lans/v1/plans"])
def test_guard_counts_noncanonical_plan_write_attempts(tmp_path, method, path):
    with guarded_execution(
        allowlist=[(method, r".*")],
        body_predicate=lambda *args: True,
        journal_path=tmp_path / "journal",
    ) as guard, intent_scope("one"):
        for _ in range(2):
            with pytest.raises(GuardViolationError, match="Non-canonical"):
                guard.begin(method, path, {})
        with pytest.raises(GuardViolationError, match="ceiling"):
            guard.begin(method, "/plans/v1/plans", {})
