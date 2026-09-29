from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json

import pytest

from backend.schemas import AgentResult, Failure
from backend.schemas.enums import AgentStatus, FailureCode, JobStatus, ReasonCode
from backend.services.job_repository import IdempotencyConflict, JobNotFound, JobRepository
from backend.shared.auth import hash_session_token


class FakeConnection:
    def __init__(self, rows=(), update_row=True, fail_job_insert=False):
        self.rows = list(rows)
        self.update_row = update_row
        self.fail_job_insert = fail_job_insert
        self.calls = []
        self.rolled_back = False

    async def execute(self, query, *args):
        self.calls.append((query, args))
        return "SELECT 1"

    async def fetchrow(self, query, *args):
        self.calls.append((query, args))
        if query.lstrip().startswith("SELECT * FROM jobs"):
            return self.rows.pop(0) if self.rows else None
        if "INSERT INTO jobs" in query:
            if self.fail_job_insert:
                raise RuntimeError("job insert failed")
            row = _job_row((args[0], args[1], args[2], args[3], args[4], None,
                            args[5], 0, args[6], None))
            return row
        if "UPDATE jobs" in query:
            if not self.update_row:
                return None
            row = _job_row((args[0], SESSION_ID, "text", "hash", "key", None,
                            args[1], 0, 3, None))
            row["attempt"] = 1
            row["status"] = args[1]
            row["succeeded"] = args[1] == "completed" if args[1] in ("completed", "failed") else None
            row["final_payload_json"] = args[2] if args[1] == "completed" else args[3] if args[1] == "failed" else None
            return row
        raise AssertionError(query)

    @asynccontextmanager
    async def transaction(self):
        try:
            yield
        except BaseException:
            self.rolled_back = True
            raise


class FakePool:
    def __init__(self, connection):
        self.connection = connection

    @asynccontextmanager
    async def acquire(self):
        yield self.connection

    async def fetchrow(self, query, *args):
        return await self.connection.fetchrow(query, *args)


SESSION_ID = "a8098b2a-941e-4ce9-9dd2-22da1b55d744"
JOB_ID = "51498152-d371-4fd8-9e5a-a81befee3b17"


def _job_row(args):
    return {
        "job_id": args[0], "session_id": args[1], "request_text": args[2],
        "request_text_hash": args[3], "idempotency_key_hash": args[4],
        "idempotency_expires_at": datetime.now(timezone.utc), "status": args[6],
        "attempt": args[7], "max_attempts": args[8], "next_retry_at": None,
        "succeeded": None, "final_payload_json": None,
    }


def _run(awaitable):
    return asyncio.run(awaitable)


def test_submit_creates_hashed_queued_job_under_session_lock():
    connection = FakeConnection()
    job, created = _run(JobRepository(FakePool(connection)).submit(
        session_id=SESSION_ID, request_text="draw", idempotency_key=JOB_ID
    ))

    assert created is True
    assert job.job_status is JobStatus.QUEUED and job.attempt == 1
    lock_query, lock_args = connection.calls[0]
    assert "pg_advisory_xact_lock" in lock_query
    assert lock_args == (SESSION_ID,)
    lookup_query, _ = connection.calls[1]
    assert "idempotency_expires_at > now()" in lookup_query
    insert_query, insert_args = connection.calls[2]
    assert "INSERT INTO jobs" in insert_query
    assert insert_args[2] == "draw"
    assert insert_args[3] != "draw"
    assert insert_args[4] != JOB_ID


def test_new_session_and_job_share_transaction():
    connection = FakeConnection()
    token = "opaque-session-token"

    job, created = _run(JobRepository(FakePool(connection)).submit_new_session(
        session_token=token, request_text="draw", idempotency_key=JOB_ID
    ))

    session_query, session_args = connection.calls[0]
    assert "INSERT INTO sessions" in session_query
    assert session_args[1] == hash_session_token(token)
    assert "opaque-session-token" not in session_args
    assert "INSERT INTO jobs" in connection.calls[3][0]
    assert connection.calls[3][1][1] == job.session_id
    assert created is True
    assert connection.rolled_back is False


def test_new_session_rolls_back_when_job_insert_fails():
    connection = FakeConnection(fail_job_insert=True)

    with pytest.raises(RuntimeError, match="job insert failed"):
        _run(JobRepository(FakePool(connection)).submit_new_session(
            session_token="opaque-session-token",
            request_text="draw",
            idempotency_key=JOB_ID,
        ))

    assert "INSERT INTO sessions" in connection.calls[0][0]
    assert any("INSERT INTO jobs" in query for query, _ in connection.calls)
    assert connection.rolled_back is True


def test_submit_reuses_matching_unexpired_job():
    existing = _job_row((JOB_ID, SESSION_ID, "draw", "same-hash", "key", None,
                         "queued", 0, 3, None))
    from backend.services.job_repository import _hash
    existing["request_text_hash"] = _hash("draw")
    connection = FakeConnection([existing])

    job, created = _run(JobRepository(FakePool(connection)).submit(
        session_id=SESSION_ID, request_text="draw", idempotency_key=JOB_ID
    ))

    assert job.job_id == JOB_ID and created is False
    assert len(connection.calls) == 2


def test_submit_rejects_same_key_with_different_request_text():
    existing = _job_row((JOB_ID, SESSION_ID, "different", "other-hash", "key", None,
                         "queued", 0, 3, None))
    connection = FakeConnection([existing])

    with pytest.raises(IdempotencyConflict):
        _run(JobRepository(FakePool(connection)).submit(
            session_id=SESSION_ID, request_text="draw", idempotency_key=JOB_ID
        ))
    assert len(connection.calls) == 2


def test_get_hides_jobs_not_owned_by_session():
    with pytest.raises(JobNotFound):
        _run(JobRepository(FakePool(FakeConnection())).get(
            session_id=SESSION_ID, job_id=JOB_ID
        ))


def test_update_status_persists_terminal_payload_without_thumbnail():
    connection = FakeConnection()
    result = AgentResult(
        agent_status=AgentStatus.OUT_OF_SCOPE,
        reason_codes=[ReasonCode.OUT_OF_SCOPE_REQUEST],
    )

    job = _run(JobRepository(FakePool(connection)).update_status(
        job_id=JOB_ID, status=JobStatus.COMPLETED, result=result
    ))

    update_query, args = connection.calls[0]
    saved = json.loads(args[2])
    assert "thumbnail_url" not in json.dumps(saved)
    assert "completed_at = CASE" in update_query
    assert job.job_status is JobStatus.COMPLETED
    assert job.result == result


def test_update_status_requires_contractual_terminal_payload():
    repository = JobRepository(FakePool(FakeConnection()))
    failure = Failure(failure_code=FailureCode.INTERNAL_CODE_ERROR, user_message="failed")

    with pytest.raises(ValueError):
        _run(repository.update_status(job_id=JOB_ID, status=JobStatus.COMPLETED))
    with pytest.raises(ValueError):
        _run(repository.update_status(
            job_id=JOB_ID, status=JobStatus.QUEUED, failure=failure
        ))


@pytest.mark.parametrize("terminal_status", [JobStatus.COMPLETED, JobStatus.FAILED])
def test_update_status_does_not_overwrite_terminal_job(terminal_status):
    connection = FakeConnection(update_row=False)

    with pytest.raises(JobNotFound):
        _run(JobRepository(FakePool(connection)).update_status(
            job_id=JOB_ID, status=JobStatus.RUNNING
        ))

    query, _ = connection.calls[0]
    assert "status NOT IN ('completed', 'failed')" in query
