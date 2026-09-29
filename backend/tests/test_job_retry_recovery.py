from __future__ import annotations

import asyncio
import json
import os
import uuid

import asyncpg
import pytest

from backend.db.migrate import migrate
from backend.schemas.enums import FailureCode, JobStatus
from backend.services.job_repository import JobRepository, StaleJobAttempt
from backend.services.job_retry_recovery import JobRetryRecovery, retry_delay_ms
from backend.services.llm import LLMRateLimited, LLMTimeout, PromptConfigurationError


@pytest.mark.parametrize(
    ("attempt", "error", "expected_ms"),
    [
        (1, LLMTimeout("timeout"), 1_000),
        (2, LLMTimeout("timeout"), 2_000),
        (1, LLMRateLimited("limited", retry_after_ms=60_000), 30_000),
        (1, LLMRateLimited("limited", retry_after_ms=100), 1_000),
    ],
)
def test_retry_delay_follows_attempt_and_retry_after(attempt, error, expected_ms):
    assert retry_delay_ms(attempt, error) == expected_ms


def test_retry_and_lease_recovery_follow_postgres_contract():
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for the PostgreSQL retry test")

    async def verify_retry_and_recovery():
        schema = f"retry_test_{uuid.uuid4().hex}"
        admin = await asyncpg.connect(database_url)
        pool = None
        try:
            await admin.execute(f'CREATE SCHEMA "{schema}"')

            async def setup_connection(connection):
                await connection.execute(f'SET search_path TO "{schema}"')

            pool = await asyncpg.create_pool(
                database_url, min_size=2, max_size=2, setup=setup_connection
            )
            async with pool.acquire() as connection:
                await migrate(connection)
                session_id = str(uuid.uuid4())
                await connection.execute(
                    "INSERT INTO sessions (session_id, session_token_hash) VALUES ($1::uuid, $2)",
                    session_id,
                    uuid.uuid4().hex,
                )

            repository = JobRepository(pool)
            recovery = JobRetryRecovery(pool)
            retry_job, _ = await repository.submit(
                session_id=session_id, request_text="retry", idempotency_key=str(uuid.uuid4())
            )
            claimed = await repository.claim_next()
            assert str(claimed["job_id"]) == retry_job.job_id
            assert claimed["attempt"] == 1

            assert await recovery.handle_attempt_failure(
                job_id=retry_job.job_id,
                attempt=1,
                max_attempts=3,
                error=LLMTimeout("timeout"),
            ) is True
            async with pool.acquire() as connection:
                row = await connection.fetchrow(
                    """SELECT status, attempt, next_retry_at, lease_expires_at, updated_at
                       FROM jobs WHERE job_id=$1::uuid""",
                    retry_job.job_id,
                )
                delay_ms = (row["next_retry_at"] - row["updated_at"]).total_seconds() * 1000
            assert row["status"] == "queued" and row["attempt"] == 1
            assert 800 <= delay_ms <= 1_500
            assert row["lease_expires_at"] is None
            async with pool.acquire() as connection:
                await connection.execute(
                    "UPDATE jobs SET next_retry_at=now()-interval '1 second' WHERE job_id=$1::uuid",
                    retry_job.job_id,
                )
            claimed = await repository.claim_next()
            assert claimed["attempt"] == 2
            assert await recovery.handle_attempt_failure(
                job_id=retry_job.job_id,
                attempt=2,
                max_attempts=3,
                error=LLMRateLimited("limited", retry_after_ms=60_000),
            ) is True
            async with pool.acquire() as connection:
                row = await connection.fetchrow(
                    "SELECT next_retry_at, updated_at FROM jobs WHERE job_id=$1::uuid",
                    retry_job.job_id,
                )
                delay_ms = (row["next_retry_at"] - row["updated_at"]).total_seconds() * 1000
            assert 29_000 <= delay_ms <= 31_000
            assert await repository.claim_next() is None

            async with pool.acquire() as connection:
                await connection.execute(
                    "UPDATE jobs SET next_retry_at=now()-interval '1 second' WHERE job_id=$1::uuid",
                    retry_job.job_id,
                )
            claimed = await repository.claim_next()
            assert claimed["attempt"] == 3
            assert await recovery.handle_attempt_failure(
                job_id=retry_job.job_id,
                attempt=3,
                max_attempts=3,
                error=LLMTimeout("timeout"),
            ) is True
            async with pool.acquire() as connection:
                row = await connection.fetchrow(
                    "SELECT status, succeeded, final_payload_json FROM jobs WHERE job_id=$1::uuid",
                    retry_job.job_id,
                )
            payload = json.loads(row["final_payload_json"])
            assert row["status"] == "failed" and row["succeeded"] is False
            assert payload["failure_code"] == FailureCode.LLM_TIMEOUT.value
            assert await repository.claim_next() is None

            config_job, _ = await repository.submit(
                session_id=session_id, request_text="configuration", idempotency_key=str(uuid.uuid4())
            )
            claimed = await repository.claim_next()
            assert str(claimed["job_id"]) == config_job.job_id
            assert await recovery.handle_attempt_failure(
                job_id=config_job.job_id,
                attempt=1,
                max_attempts=3,
                error=PromptConfigurationError("missing prompt"),
            ) is True
            async with pool.acquire() as connection:
                row = await connection.fetchrow(
                    "SELECT status, final_payload_json FROM jobs WHERE job_id=$1::uuid",
                    config_job.job_id,
                )
            payload = json.loads(row["final_payload_json"])
            assert row["status"] == "failed"
            assert payload["failure_code"] == FailureCode.CONFIGURATION_ERROR.value

            lease_job, _ = await repository.submit(
                session_id=session_id, request_text="lease", idempotency_key=str(uuid.uuid4())
            )
            claimed = await repository.claim_next()
            assert str(claimed["job_id"]) == lease_job.job_id
            async with pool.acquire() as connection:
                await connection.execute(
                    "UPDATE jobs SET lease_expires_at=now()-interval '1 second' WHERE job_id=$1::uuid",
                    lease_job.job_id,
                )
            assert await recovery.recover_expired_leases() == {"requeued": 1, "failed": 0}
            claimed = await repository.claim_next()
            assert claimed["attempt"] == 2
            with pytest.raises(StaleJobAttempt):
                await repository.update_status(
                    job_id=lease_job.job_id,
                    status=JobStatus.VALIDATING,
                    attempt=1,
                )
            async with pool.acquire() as connection:
                row = await connection.fetchrow(
                    "SELECT status, attempt FROM jobs WHERE job_id=$1::uuid",
                    lease_job.job_id,
                )
            assert row["status"] == "running" and row["attempt"] == 2

            async with pool.acquire() as connection:
                await connection.execute(
                    """UPDATE jobs SET attempt=3, lease_expires_at=now()-interval '1 second'
                       WHERE job_id=$1::uuid""",
                    lease_job.job_id,
                )
            assert await recovery.recover_expired_leases() == {"requeued": 0, "failed": 1}
            async with pool.acquire() as connection:
                row = await connection.fetchrow(
                    "SELECT status, final_payload_json FROM jobs WHERE job_id=$1::uuid",
                    lease_job.job_id,
                )
            payload = json.loads(row["final_payload_json"])
            assert row["status"] == "failed"
            assert payload["failure_code"] == FailureCode.JOB_INSTANCE_INTERRUPTED.value
        finally:
            if pool is not None:
                await pool.close()
            await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            await admin.close()

    asyncio.run(verify_retry_and_recovery())
