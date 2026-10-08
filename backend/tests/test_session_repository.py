from __future__ import annotations

import pytest
import uuid
from contextlib import asynccontextmanager

from backend.services.session_repository import SessionRepository
from backend.services.job_repository import JobNotFound, JobRepository
from backend.shared.auth import hash_session_token


class FakePool:
    def __init__(self, row=None, execute_result="DELETE 0", error=None):
        self.row = row
        self.execute_result = execute_result
        self.error = error
        self.calls = []

    @asynccontextmanager
    async def acquire(self):
        yield self

    @asynccontextmanager
    async def transaction(self):
        yield self

    async def fetchval(self, query, *args):
        self.calls.append((query, args))
        if self.error:
            raise self.error
        return self.row["session_id"] if self.row else None

    async def fetchrow(self, query, *args):
        self.calls.append((query, args))
        if self.error is not None:
            raise self.error
        return {"owner_id": str(uuid.uuid4()), "default_session_id": None}

    async def execute(self, query, *args):
        self.calls.append((query, args))
        if self.error is not None:
            raise self.error
        return self.execute_result


def test_create_session_stores_only_hash_and_returns_uuid():
    pool = FakePool({"session_id": "0d6fe2df-55e4-4ea2-a8fc-44b133a19f3d"})
    repository = SessionRepository(pool)

    result = _run(repository.create_session("opaque-token"))

    assert uuid.UUID(result)
    assert result == pool.calls[1][1][0]
    assert result != "opaque-token"
    query, args = pool.calls[0]
    assert "INSERT INTO anonymous_owners" in query
    assert args[1] == hash_session_token("opaque-token")
    assert args[0] != "opaque-token"
    assert "opaque-token" not in args


def test_resolve_session_hashes_token_without_touching_activity():
    pool = FakePool({"session_id": "session-uuid"})
    repository = SessionRepository(pool)

    result = _run(repository.resolve_session("opaque-token"))

    query, args = pool.calls[0]
    assert result == "session-uuid"
    assert "UPDATE" not in query
    assert "interval '3 months' > now()" in query
    assert args == (hash_session_token("opaque-token"),)


def test_resolve_unknown_token_returns_none():
    pool = FakePool()

    assert _run(SessionRepository(pool).resolve_session("unknown")) is None


def test_bootstrap_uses_one_owner_scoped_query_and_returns_latest_job():
    session_id = "0d6fe2df-55e4-4ea2-a8fc-44b133a19f3d"
    job_id = "00000000-0000-0000-0000-000000000001"
    class BootstrapPool(FakePool):
        async def fetchrow(self, query, *args):
            self.calls.append((query, args))
            return {
                "owner_exists": True,
                "sessions": [{"session_id": session_id, "created_at": "2026-10-08T00:00:00+00:00",
                              "last_activity_at": "2026-10-08T00:00:00+00:00",
                              "expires_at": "2027-01-08T00:00:00+00:00"}],
                "session_id": session_id,
                "latest_job": {"job_id": job_id, "session_id": session_id, "status": "queued",
                               "attempt": 0, "max_attempts": 3, "succeeded": None,
                               "final_payload_json": None, "request_text": "요청",
                               "created_at": "2026-10-08T00:00:00+00:00"},
                "has_older_jobs": False,
            }

    pool = BootstrapPool()
    state = _run(SessionRepository(pool).bootstrap("opaque-token"))

    assert len(pool.calls) == 1
    query, args = pool.calls[0]
    assert "session_token_hash=$1" in query
    assert "latest_job" in query
    assert "jsonb_agg" in query
    assert "UPDATE sessions" in query
    assert args == (hash_session_token("opaque-token"), 100)
    assert state["session_id"] == session_id
    assert state["latest_job"]["job_id"] == job_id
    assert state["latest_job"]["request_text"] == "요청"


def test_history_for_owner_batches_authorization_and_jobs_in_one_query():
    session_id = "0d6fe2df-55e4-4ea2-a8fc-44b133a19f3d"
    job_row = {"job_id": "00000000-0000-0000-0000-000000000001", "session_id": session_id,
               "status": "queued", "attempt": 0, "max_attempts": 3, "succeeded": None,
               "final_payload_json": None, "request_text": "요청", "created_at": "2026-10-08T00:00:00+00:00"}
    class HistoryPool:
        def __init__(self, row):
            self.row = row
            self.calls = []
        async def fetchrow(self, query, *args):
            self.calls.append((query, args))
            return self.row

    pool = HistoryPool({"authorized": True, "jobs": [job_row]})
    items = _run(JobRepository(pool).history_for_owner("opaque-token", session_id))
    assert len(pool.calls) == 1
    query, args = pool.calls[0]
    assert "anonymous_owners" in query and "session_token_hash=$1" in query
    assert "page AS MATERIALIZED" in query and "UPDATE sessions" in query
    assert args == (hash_session_token("opaque-token"), session_id, 20, 0)
    assert items[0]["job_id"] == job_row["job_id"]
    assert items[0]["request_text"] == "요청"

    unauthorized = HistoryPool({"authorized": False, "jobs": []})
    with pytest.raises(JobNotFound):
        _run(JobRepository(unauthorized).history_for_owner("other-token", session_id))
    assert len(unauthorized.calls) == 1


def test_delete_expired_sessions_returns_deleted_count():
    pool = FakePool(execute_result="DELETE 3")

    assert _run(SessionRepository(pool).delete_expired_sessions()) == 3
    query, args = pool.calls[0]
    assert "last_activity_at + interval '3 months' <= now()" in query
    assert args == ()


@pytest.mark.parametrize("method", ["create_session", "resolve_session"])
def test_empty_token_fails_before_database_call(method):
    pool = FakePool()
    repository = SessionRepository(pool)

    with pytest.raises(ValueError):
        _run(getattr(repository, method)(""))
    assert pool.calls == []


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("create_session", ("opaque-token",)),
        ("resolve_session", ("opaque-token",)),
        ("delete_expired_sessions", ()),
    ],
)
def test_database_errors_are_propagated(method, args):
    pool = FakePool(error=RuntimeError("database unavailable"))

    with pytest.raises(RuntimeError, match="database unavailable"):
        _run(getattr(SessionRepository(pool), method)(*args))


def _run(awaitable):
    import asyncio

    return asyncio.run(awaitable)
