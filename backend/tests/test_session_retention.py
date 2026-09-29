from __future__ import annotations

import asyncio

from backend.tasks import session_retention


def test_cleanup_task_deletes_expired_sessions_and_closes_pool(monkeypatch):
    pool = object()
    created = []
    closed = []
    deleted = []

    async def create_pool(settings):
        created.append(settings)
        return pool

    async def close_pool(received_pool):
        closed.append(received_pool)

    class FakeSessionRepository:
        def __init__(self, received_pool):
            assert received_pool is pool

        async def delete_expired_sessions(self):
            deleted.append(True)
            return 3

    monkeypatch.setattr(session_retention, "create_pool", create_pool)
    monkeypatch.setattr(session_retention, "close_pool", close_pool)
    monkeypatch.setattr(session_retention, "SessionRepository", FakeSessionRepository)

    assert asyncio.run(session_retention.cleanup_expired_sessions()) == 3
    assert created
    assert deleted == [True]
    assert closed == [pool]


def test_cleanup_task_closes_pool_when_delete_fails(monkeypatch):
    pool = object()
    closed = []

    async def create_pool(settings):
        return pool

    async def close_pool(received_pool):
        closed.append(received_pool)

    class FailingSessionRepository:
        def __init__(self, received_pool):
            assert received_pool is pool

        async def delete_expired_sessions(self):
            raise RuntimeError("database unavailable")

    monkeypatch.setattr(session_retention, "create_pool", create_pool)
    monkeypatch.setattr(session_retention, "close_pool", close_pool)
    monkeypatch.setattr(session_retention, "SessionRepository", FailingSessionRepository)

    try:
        asyncio.run(session_retention.cleanup_expired_sessions())
    except RuntimeError as error:
        assert str(error) == "database unavailable"
    else:
        raise AssertionError("cleanup failure must propagate")

    assert closed == [pool]
