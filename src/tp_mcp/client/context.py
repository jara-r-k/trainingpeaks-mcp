"""Scoped athlete targeting and opt-in, durable HTTP execution guards.

HC callers hold an exclusive run lock, enter ``guarded_execution``, then use
``intent_scope`` for each intent and call ``require_guard`` before mutations.
Allowlist regexes match the whole path. The predicate receives (method, path,
JSON body), including GETs; include /users/v3/token for token refresh reads.
Body hashes use canonical JSON (sort_keys=True, separators=(',', ':')).
Reconciliation and proving non-dispatch remain the caller's responsibility.
"""

import contextvars
import hashlib
import json
import os
import re
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

athlete_override: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "athlete_override", default=None
)

current_intent: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_intent", default=None
)
execution_guard: contextvars.ContextVar["ExecutionGuard | None"] = (
    contextvars.ContextVar("execution_guard", default=None)
)

JSONBody = dict[str, Any] | list[Any] | None


class GuardViolationError(RuntimeError):
    """A guarded request is refused before it can reach the transport."""


class ExecutionGuard:
    """Allowlist and append-only journal for one exclusively locked HC run."""

    def __init__(
        self,
        allowlist: Sequence[tuple[str, str]],
        body_predicate: Callable[[str, str, JSONBody], bool],
        journal_path: str | Path,
    ) -> None:
        self.allowlist = tuple(
            (method.upper(), re.compile(path)) for method, path in allowlist
        )
        self.body_predicate = body_predicate
        self.journal_path = Path(journal_path)
        self._journal_failed = False

    def check(self, method: str, path: str, body: JSONBody) -> None:
        """Refuse requests outside the explicit method/path/body allowlist."""
        if self._journal_failed:
            raise GuardViolationError(
                "Execution guard journal failed; stop and reconcile."
            )
        # Do not let URL normalisation turn an allowed spelling into another path.
        if (
            not path.startswith("/")
            or path.startswith("//")
            or any(char in path for char in ("%", "?", "#", "\\"))
            or any(part in (".", "..") for part in path.split("/"))
            or any(ord(char) <= 32 for char in path)
        ):
            raise GuardViolationError(f"Non-canonical guarded path: {path!r}")
        if not any(
            verb == method and pattern.fullmatch(path)
            for verb, pattern in self.allowlist
        ):
            raise GuardViolationError(
                f"Request outside execution allowlist: {method} {path}"
            )
        if not self.body_predicate(method, path, body):
            raise GuardViolationError(
                f"Body outside execution allowlist: {method} {path}"
            )
        if method != "GET" and not current_intent.get():
            raise GuardViolationError(
                "A current intent is required for guarded mutations."
            )

    def _post_state(self) -> tuple[int, bool]:
        """Restore POST attempts and dispatches, refusing damaged journals."""
        attempts = 0
        dispatched = False
        # ponytail: scan the run journal; index it if large runs make this costly.
        try:
            with self.journal_path.open() as journal:
                for line in journal:
                    if not line.endswith("\n"):
                        raise ValueError("incomplete journal line")
                    event = json.loads(line)
                    if not isinstance(event, dict) or not isinstance(
                        event.get("event"), str
                    ):
                        raise ValueError("invalid journal event")
                    if event.get("intent_id") != current_intent.get():
                        continue
                    if event["event"] in ("attempt", "dispatched"):
                        # Missing method cannot safely prove this was only a GET.
                        method = event.get("method", "POST")
                        if method == "POST":
                            attempts += event["event"] == "attempt"
                            dispatched |= event["event"] == "dispatched"
        except FileNotFoundError:
            pass
        except (ValueError, UnicodeError) as exc:
            raise GuardViolationError(
                "Invalid execution journal; stop and reconcile."
            ) from exc
        return attempts, dispatched

    def _append(self, event: dict[str, Any]) -> None:
        """Append one complete JSONL event and fsync before permitting progress."""
        if self._journal_failed:
            raise GuardViolationError(
                "Execution guard journal failed; stop and reconcile."
            )
        data = (
            json.dumps({**event, "ts": datetime.now(timezone.utc).isoformat()}) + "\n"
        ).encode()
        try:
            fd = os.open(
                self.journal_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600
            )
            try:
                if os.write(fd, data) != len(data):
                    raise OSError("Incomplete execution journal append")
                os.fsync(fd)
            finally:
                os.close(fd)
        except BaseException:
            self._journal_failed = True
            raise

    def begin(self, method: str, path: str, body: JSONBody) -> None:
        """Count POST attempts, including refused/pre-auth attempts, before work."""
        if method == "POST":
            if not current_intent.get():
                raise GuardViolationError(
                    "A current intent is required for guarded POSTs."
                )
            attempts, dispatched = self._post_state()
            if dispatched:
                raise GuardViolationError(
                    "This intent already dispatched a POST; reconcile, never replay."
                )
            if attempts >= 2:
                raise GuardViolationError(
                    "POST attempt ceiling of 2 reached for this intent."
                )
            self._append(
                {
                    "event": "attempt",
                    "intent_id": current_intent.get(),
                    "method": method,
                    "path": path,
                    "attempt": attempts + 1,
                }
            )
        self.check(method, path, body)

    def dispatch(self, method: str, path: str, body: JSONBody) -> dict[str, Any]:
        """Persist dispatch immediately before send; recheck after async waits."""
        self.check(method, path, body)
        if method == "POST":
            attempts, dispatched = self._post_state()
            if dispatched:
                raise GuardViolationError(
                    "This intent already dispatched a POST; reconcile, never replay."
                )
            if not 1 <= attempts <= 2:
                raise GuardViolationError(
                    "Guarded POST requires a recorded attempt within the ceiling of 2."
                )
        metadata = {
            "intent_id": current_intent.get(),
            "method": method,
            "path": path,
            "body_sha256": hashlib.sha256(
                json.dumps(
                    body, sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode()
            ).hexdigest(),
        }
        self._append({"event": "dispatched", **metadata})
        return metadata

    def response(self, metadata: dict[str, Any], status: int, body: Any) -> None:
        """Persist resource IDs from raw JSON before handlers see the response."""
        ids: list[int | str] = []

        def collect(value: Any) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in (
                        "id",
                        "workoutId",
                        "exerciseLibraryId",
                        "exerciseLibraryItemId",
                        "noteId",
                    ):
                        if type(item) in (int, str) and item not in ids:
                            ids.append(item)
                    elif isinstance(item, (dict, list)):
                        collect(item)
            elif isinstance(value, list):
                for item in value:
                    collect(item)
            elif (
                type(value) in (int, str) and str(value).isdigit() and value not in ids
            ):
                ids.append(value)

        collect(body)
        self._append(
            {"event": "response", **metadata, "status": status, "raw_ids": ids}
        )


@contextmanager
def guarded_execution(
    *,
    allowlist: Sequence[tuple[str, str]],
    body_predicate: Callable[[str, str, JSONBody], bool],
    journal_path: str | Path,
) -> Iterator[ExecutionGuard]:
    """Install an opt-in HTTP guard, restoring its predecessor even on cancellation."""
    guard = ExecutionGuard(allowlist, body_predicate, journal_path)
    token = execution_guard.set(guard)
    try:
        yield guard
    finally:
        execution_guard.reset(token)


@contextmanager
def intent_scope(intent_id: str) -> Iterator[None]:
    """Scope an intent ID and always reset the ContextVar token in finally."""
    if not isinstance(intent_id, str) or not intent_id.strip():
        raise GuardViolationError("A non-empty intent ID is required.")
    token = current_intent.set(intent_id)
    try:
        yield
    finally:
        current_intent.reset(token)


def require_guard() -> ExecutionGuard:
    """Fail closed at an HC placer/publisher entrypoint without an active guard."""
    guard = execution_guard.get()
    if guard is None:
        raise GuardViolationError("An execution guard is required for this mutation.")
    return guard
