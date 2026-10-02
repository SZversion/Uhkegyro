"""Execute claimed jobs through the LLM, resolver, and response assembler."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Mapping

from pydantic import ValidationError

from backend.schemas.enums import AgentStatus, JobStatus, ReasonCode, Role
from backend.schemas.models import AgentResult
from backend.services.catalog_repository import CatalogSnapshot
from backend.services.conversation_memory import ConversationMemory
from backend.services import conversation_context
from backend.services.input_safety import is_unsafe_input
from backend.services.job_repository import JobRepository, StaleJobAttempt
from backend.services.job_retry_recovery import JobRetryRecovery
from backend.services.job_trace import AttemptTrace, JobTracer
from backend.services.llm import (
    AgentInterpretationAdapter,
    LLMInvalidStructuredOutput,
    LLMInterpretationAdapter,
)
from backend.services.llm import format_active_cards_json
from backend.services.pinterest_provider import PinterestProvider
from backend.services.pinterest_public_search import PinterestPublicSearchProvider
from backend.services.pinterest_widget import PinterestWidgetClient, PinterestWidgetProvider
from backend.services.resolver import ResolutionResult
from backend.services.response_assembler import RoleSearchOutcome, assemble
from backend.services.failure_mapping import DATABASE_ERRORS, OperationalFailure, classify_failure

logger = logging.getLogger(__name__)
WORKER_CONCURRENCY = 5
POLL_INTERVAL_SECONDS = 1
SEARCH_RETRY_DELAYS_SECONDS = (1, 2)
MAX_INTERPRETATION_CORRECTIONS = 2


class AgentJobWorker:
    """Claim and execute one job; retry and lease policy stays in JobRetryRecovery."""

    def __init__(
        self,
        pool: Any,
        snapshot: CatalogSnapshot,
        *,
        adapter: AgentInterpretationAdapter | None = None,
        pinterest_provider: PinterestProvider | None = None,
        heartbeat_interval: float = 10,
        tracer: JobTracer | None = None,
    ) -> None:
        self._jobs = JobRepository(pool)
        self._memory = ConversationMemory(pool)
        self._recovery = JobRetryRecovery(pool)
        self._snapshot = snapshot
        self._adapter = adapter
        self._pinterest_provider = pinterest_provider
        self._heartbeat_interval = heartbeat_interval
        self._tracer = tracer if tracer is not None else JobTracer.from_settings()

    async def run_once(
        self,
        *,
        search_outcomes: Mapping[Role, RoleSearchOutcome] | None = None,
    ) -> bool:
        job = await self._jobs.claim_next()
        if job is None:
            return False
        with self._tracer.attempt(job) as trace:
            try:
                await self._with_heartbeat(job, self._process_claimed(job, search_outcomes, trace))
            except StaleJobAttempt:
                trace.stale()
            except Exception as error:
                trace.failed(job, error)
                raise
        return True

    async def _process_claimed(
        self, job: Any, search_outcomes: Mapping | None, trace: AttemptTrace
    ) -> None:
        job_id, attempt = str(job["job_id"]), job["attempt"]
        try:
            if not await self._update(job_id, attempt, JobStatus.VALIDATING):
                trace.stale()
                return
            if is_unsafe_input(str(job["request_text"])):
                result = AgentResult(
                    agent_status=AgentStatus.UNSAFE_INPUT,
                    reason_codes=[ReasonCode.UNSAFE_INPUT],
                    reference_plan=None,
                    clarifying_question=None,
                    user_message=(
                        "요청하신 내용은 지원할 수 없습니다. "
                        "캐릭터의 체형·포즈·시점을 텍스트로 설명해 주세요."
                    ),
                )
                if await self._update(job_id, attempt, JobStatus.COMPLETED, result=result):
                    trace.completed(result)
                else:
                    trace.stale()
                return
            if self._adapter is None:
                self._adapter = LLMInterpretationAdapter()
            with trace.stage("memory-context"):
                context = await conversation_context.prepare(self._memory, job, self._adapter, trace)
            recalled, recall_only = await conversation_context.recall(
                self._memory, job, context, self._adapter, trace)
            state = context["state"]
            if recall_only:
                result = recalled
            else:
                with trace.stage("validating"):
                    feedback = job.get("validation_feedback_json")
                    if isinstance(feedback, str):
                        feedback = json.loads(feedback)
                    correction_feedback = None
                    for correction in range(MAX_INTERPRETATION_CORRECTIONS + 1):
                        try:
                            interpretation = await self._adapter.interpret(
                                job["request_text"], **conversation_context.trace_args(job),
                                active_cards_json=format_active_cards_json(self._snapshot),
                                session_context=conversation_context.prompt_context(context),
                                **({"validation_feedback": feedback} if feedback else {}),
                                **({"correction_feedback": correction_feedback}
                                   if correction_feedback else {}),
                            )
                            resolution = await conversation_context.validate(
                                self._memory, job, interpretation, self._snapshot)
                            break
                        except LLMInvalidStructuredOutput as error:
                            if correction >= MAX_INTERPRETATION_CORRECTIONS:
                                raise
                            feedback = error.feedback[:8]
                            correction_feedback = _interpretation_validation_feedback(
                                error, str(job["request_text"])
                            )
                with trace.stage("searching"):
                    if not await self._update(job_id, attempt, JobStatus.SEARCHING):
                        trace.stale()
                        return
                    if search_outcomes is None:
                        search_outcomes = await self._search_outcomes(resolution)
                result = assemble(resolution, self._snapshot, search_outcomes)
                if recalled is not None:
                    result.memory_answer, result.sources = recalled.memory_answer, recalled.sources
                state = conversation_context.next_state(context, job, interpretation, result)
            with trace.stage("rendering"):
                if not await self._update(job_id, attempt, JobStatus.RENDERING):
                    trace.stale()
                    return
                await self._memory.complete(job, result, state)
            trace.completed(result)
        except StaleJobAttempt:
            trace.stale()
        except Exception as error:
            await self._handle_failure(job, error, trace)

    async def _search_outcomes(
        self, resolution: ResolutionResult
    ) -> Mapping[Role, RoleSearchOutcome]:
        if self._pinterest_provider is None:
            return {}

        outcomes: dict[Role, RoleSearchOutcome] = {}
        for term in resolution.terms:
            role = term.selection.role
            query_fragments = tuple(term.card["query_fragments"])
            outcome = await self._pinterest_provider.search(role, query_fragments)
            if outcome.role is not role:
                raise ValueError("Pinterest provider 결과 역할이 요청과 다릅니다")
            for delay in SEARCH_RETRY_DELAYS_SECONDS:
                if outcome.code is not ReasonCode.PIN_SEARCH_UNAVAILABLE:
                    break
                await asyncio.sleep(delay)
                outcome = await self._pinterest_provider.search(role, query_fragments)
                if outcome.role is not role:
                    raise ValueError("Pinterest provider 결과 역할이 요청과 다릅니다")
            outcomes[role] = outcome
        return outcomes

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
                try:
                    await self._jobs.extend_lease(
                        job_id=str(job["job_id"]), attempt=job["attempt"]
                    )
                except DATABASE_ERRORS as error:
                    raise OperationalFailure(classify_failure(error, context="database")) from None

    async def _handle_failure(
        self, job: Any, error: Exception, trace: AttemptTrace
    ) -> None:
        try:
            updated = await self._recovery.handle_attempt_failure(
                job_id=str(job["job_id"]),
                attempt=job["attempt"],
                max_attempts=job["max_attempts"],
                error=error,
            )
        except DATABASE_ERRORS as persistence_error:
            raise OperationalFailure(classify_failure(persistence_error, context="database")) from None
        if updated:
            trace.failed(job, error)
        else:
            trace.stale()

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

        try:
            await asyncio.gather(recover_leases(), *(run_slot() for _ in range(concurrency)))
        finally:
            await asyncio.to_thread(self._tracer.shutdown)

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
        except DATABASE_ERRORS as error:
            raise OperationalFailure(classify_failure(error, context="database")) from None
        return True


def _interpretation_validation_feedback(error: LLMInvalidStructuredOutput, request_text: str) -> str:
    """Return fixed, non-sensitive correction guidance for the next model call."""
    detail = str(error)
    cause = error.__cause__
    duplicate_role = isinstance(cause, ValidationError) and any(
        "역할당 최대 하나" in str(item.get("ctx", {}).get("error", ""))
        for item in cause.errors(include_input=False)
    )
    if duplicate_role:
        candidates = []
        if isinstance(cause, ValidationError):
            first = next((item for item in cause.errors(include_input=True)
                          if "역할당 최대 하나" in str(item.get("ctx", {}).get("error", ""))), {})
            raw = first.get("input")
            selections = raw.get("selections", []) if isinstance(raw, dict) else getattr(raw, "selections", [])
            roles = {}
            for selection in selections:
                role = selection.get("role") if isinstance(selection, dict) else getattr(selection, "role", None)
                term_id = selection.get("term_id") if isinstance(selection, dict) else getattr(selection, "term_id", None)
                if role is not None and term_id:
                    roles.setdefault(str(role), []).append(str(term_id))
            candidates = [{"role": role, "term_ids": ids} for role, ids in roles.items() if len(ids) > 1]
        instruction = (
            "You selected more than one card for the same role. Keep exactly one "
            "best-supported card per role; do not repeat a role in selections. "
            "Conflicting candidates: " + json.dumps(candidates, ensure_ascii=True)
        )
    elif isinstance(cause, ValidationError) and any(
        any(state in str(item.get("ctx", {}).get("error", ""))
            for state in ("select_terms", "needs_clarification", "out_of_scope"))
        for item in cause.errors(include_input=False)
    ):
        instruction = (
            "Keep interpretation_state and all dependent fields consistent. "
            "For select_terms: at least one selection, unresolved_constraints=[], "
            "clarifying_question=null, clarification_type=null. "
            "For needs_clarification: selections=[], at least one unresolved constraint, "
            "one nonempty question, and a nonnull clarification_type. "
            "For out_of_scope: selections=[], unresolved_constraints=[], context_updates=[], "
            "clarifying_question=null, clarification_type=null. "
            "If visual evidence is insufficient, use needs_clarification; never select_terms with no selections."
        )
    elif "근거" in detail or "출처" in detail:
        instruction = (
            "Every evidence value must be an exact, non-empty substring of the current request, "
            "or of the verified source request/card label when source_job_id is set. "
            "Remove any selection or context update without direct evidence. Do not paraphrase, "
            "reuse a confidence_gate description, or add explanatory words. "
            "Specifically replace selections[].evidence with an array containing a literal quote, "
            "not the catalog's explanation. context_updates[].evidence is a separate string field. "
            "When both describe the same current role change, use the same supporting literal quote "
            "in both fields. A correct context update does not fix an incorrect selection evidence. "
            "Copy text character-for-character from this current request: "
            + json.dumps(request_text, ensure_ascii=False)
        )
    elif "카드" in detail or "카탈로그" in detail:
        instruction = "Use only active term_id values whose role matches the active card catalog."
    else:
        instruction = (
            "Correct the previous output to match the required strict InterpretationOutput JSON schema; "
            "include every required field and no additional fields."
        )
    return "Your previous output failed local validation. Return corrected JSON only. " + instruction


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
            pinterest_provider = PinterestWidgetProvider(
                PinterestPublicSearchProvider(), PinterestWidgetClient()
            )
            await AgentJobWorker(
                pool, snapshot, pinterest_provider=pinterest_provider
            ).run_forever(
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
