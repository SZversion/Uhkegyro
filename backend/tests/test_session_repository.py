from __future__ import annotations

import pytest

from backend.services.session_repository import SessionRepository
from backend.shared.auth import hash_session_token


class FakePool:
    def __init__(self, row=None, execute_result="DELETE 0"):
        self.row = row
        self.execute_result = execute_result
        self.calls = []

    async def fetchrow(self, query, *args):
        self.calls.append((query, args))
        return self.row

    async def execute(self, query, *args):
        self.calls.append((query, args))
        return self.execute_result


def test_create_session_stores_only_hash_and_returns_uuid():
    pool = FakePool({"session_id": "0d6fe2df-55e4-4ea2-a8fc-44b133a19f3d"})
    repository = SessionRepository(pool)

    result = _run(repository.create_session("opaque-token"))

    assert result == "0d6fe2df-55e4-4ea2-a8fc-44b133a19f3d"
    query, args = pool.calls[0]
    assert "INSERT INTO sessions" in query
    assert args[1] == hash_session_token("opaque-token")
    assert args[0] != "opaque-token"
    assert "opaque-token" not in args


def test_resolve_session_hashes_token_and_updates_activity():
    pool = FakePool({"session_id": "session-uuid"})
    repository = SessionRepository(pool)

    result = _run(repository.resolve_session("opaque-token"))

    query, args = pool.calls[0]
    assert result == "session-uuid"
    assert "SET last_activity_at = now()" in query
    assert args == (hash_session_token("opaque-token"),)


def test_resolve_unknown_token_returns_none():
    pool = FakePool()

    assert _run(SessionRepository(pool).resolve_session("unknown")) is None


def test_delete_expired_sessions_returns_deleted_count():
    pool = FakePool(execute_result="DELETE 3")

    assert _run(SessionRepository(pool).delete_expired_sessions()) == 3
    query, args = pool.calls[0]
    assert "last_activity_at < now() - interval '3 months'" in query
    assert args == ()


@pytest.mark.parametrize("method", ["create_session", "resolve_session"])
def test_empty_token_fails_before_database_call(method):
    pool = FakePool()
    repository = SessionRepository(pool)

    with pytest.raises(ValueError):
        _run(getattr(repository, method)(""))
    assert pool.calls == []


def _run(awaitable):
    import asyncio

    return asyncio.run(awaitable)
