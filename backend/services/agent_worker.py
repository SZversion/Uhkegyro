"""Execute claimed jobs through the LLM, resolver, and response assembler."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Mapping

from backend.schemas.enums import JobStatus, Role
from backend.services.catalog_repository import CatalogSnapshot
from backend.services.job_repository import JobRepository, StaleJobAttempt
from backend.services.job_retry_recovery import JobRetryRecovery
from backend.services.llm import (
    AgentInterpretationAdapter,
    LLMInterpretationAdapter,
    LLMInvalidStructuredOutput,
)
from backend.services.llm import format_active_cards_json
from backend.services.resolver import STATUS_ALL_INVALID, resolve
from backend.services.response_assembler import RoleSearchOutcome, assemble

logger = logging.getLogger(__name__)
WORKER_CONCURRENCY = 5
POLL_INTERVAL_SECONDS = 1


class AgentJobWorker:
    """Claim and execute one job; retry and lease policy stays in JobRetryRecovery."""

    def __init__(
        self,
        pool: Any,
        snapshot: CatalogSnapshot,
        *,
        adapter: AgentInterpretationAdapter | None = None,
        heartbeat_interval: float = 10,
    ) -> None:
        self._jobs = JobRepository(pool)
        self._recovery = JobRetryRecovery(pool)
        self._snapshot = snapshot
        self._adapter = adapter
        self._heartbeat_interval = heartbeat_interval

    async def run_once(
        self,
        *,
        search_outcomes: Mapping[Role, RoleSearchOutcome] | None = None,
    ) -> bool:
        job = await self._jobs.claim_next()
        if job is None:
            return False
        try:
            await self._with_heartbeat(job, self._process_claimed(job, search_outcomes))
        except StaleJobAttempt:
            pass
        return True

    async def _process_claimed(self, job: Any, search_outcomes: Mapping | None) -> None:
        job_id = str(job["job_id"])
        attempt = job["attempt"]
        if not await self._update(job_id, attempt, JobStatus.VALIDATING):
            return

        try:
            if self._adapter is None:
                self._adapter = LLMInterpretationAdapter()
            interpretation = await self._adapter.interpret(
                job["request_text"],
                job_id=job_id,
                session_id=str(job["session_id"]),
                attempt=attempt,
                max_attempts=job["max_attempts"],
                active_cards_json=format_active_cards_json(self._snapshot),
            )
            resolution = resolve(interpretation, self._snapshot)
            if resolution.status == STATUS_ALL_INVALID:
                raise LLMInvalidStructuredOutput("resolver가 모든 선택 후보를 거부했다")
        except StaleJobAttempt:
            return
        except Exception as error:
            await self._handle_failure(job, error)
            return

        if not await self._update(job_id, attempt, JobStatus.SEARCHING):
            return
        if not await self._update(job_id, attempt, JobStatus.RENDERING):
            return
        try:
            result = assemble(resolution, self._snapshot, search_outcomes)
        except Exception as error:
            await self._handle_failure(job, error)
            return
        await self._update(job_id, attempt, JobStatus.COMPLETED, result=result)

    async def _with_heartbeat(self, job: Any, operation: Any) -> None:
        stopped = asyncio.Event()
        heartbeat = asyncio.create_task(self._heartbeat(job, stopped))
        execution = asyncio.create_task(operation)
        try:
            done, _ = await asyncio.wait(
                (heartbeat, execution), return_when=asyncio.FIRST_COMPLETED
            )
            if execution in done:
                await execution
            else:
                await heartbeat
                await execution
        finally:
            stopped.set()
            for task in (heartbeat, execution):
                if not task.done():
                    task.cancel()
            await asyncio.gather(heartbeat, execution, return_exceptions=True)

    async def _heartbeat(self, job: Any, stopped: asyncio.Event) -> None:
        while True:
            try:
                await asyncio.wait_for(stopped.wait(), timeout=self._heartbeat_interval)
                return
            except asyncio.TimeoutError:
                await self._jobs.extend_lease(
                    job_id=str(job["job_id"]), attempt=job["attempt"]
                )

    async def _handle_failure(self, job: Any, error: Exception) -> None:
        await self._recovery.handle_attempt_failure(
            job_id=str(job["job_id"]),
            attempt=job["attempt"],
            max_attempts=job["max_attempts"],
            error=error,
        )

    async def run_forever(self, *, concurrency: int = WORKER_CONCURRENCY) -> None:
        async def recover_leases() -> None:
            while True:
                try:
                    await self._recovery.recover_expired_leases()
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    logger.error(
                        "job lease recovery failed",
                        extra={"error_type": type(error).__name__},
                    )
                await asyncio.sleep(POLL_INTERVAL_SECONDS)

        async def run_slot() -> None:
            while True:
                try:
                    await self.run_once()
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    logger.error(
                        "job worker iteration failed",
                        extra={"error_type": type(error).__name__},
                    )
                await asyncio.sleep(POLL_INTERVAL_SECONDS)

        await asyncio.gather(recover_leases(), *(run_slot() for _ in range(concurrency)))

    async def _update(
        self,
        job_id: str,
        attempt: int,
        status: JobStatus,
        *,
        result: Any | None = None,
    ) -> bool:
        try:
            await self._jobs.update_status(
                job_id=job_id,
                status=status,
                attempt=attempt,
                result=result,
            )
        except StaleJobAttempt:
            return False
        return True


async def run_worker(snapshot: CatalogSnapshot) -> None:
    """Keep the polling worker alive without making API startup depend on the DB."""
    from backend.shared.config import get_settings
    from backend.shared.database import close_pool, create_pool

    while True:
        pool = None
        try:
            settings = get_settings()
            if settings.database_url.startswith("sqlite"):
                return
            pool = await create_pool(settings)
            await AgentJobWorker(pool, snapshot).run_forever(
                concurrency=settings.worker_concurrency
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.error(
                "job worker unavailable; retrying",
                extra={"error_type": type(error).__name__},
            )
        finally:
            if pool is not None:
                await close_pool(pool)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
