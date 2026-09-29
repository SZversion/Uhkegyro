"""Worker pipeline tests for the task 9 job contract."""

import asyncio

import pytest

from backend.schemas.enums import (
    AgentStatus,
    ClarificationType,
    InterpretationState,
    JobStatus,
    ReasonCode,
    Role,
)
from backend.schemas.models import InterpretationOutput, InterpretationSelection
from backend.services.job_repository import StaleJobAttempt
from backend.services.llm import LLMTimeout
from backend.services.response_assembler import RoleSearchOutcome
from backend.services import agent_worker
from backend.services.agent_worker import AgentJobWorker


JOB = {
    "job_id": "job-1",
    "session_id": "session-1",
    "request_text": "한쪽 다리에 체중을 실은 자세",
    "attempt": 2,
    "max_attempts": 3,
}


def _selected(term_id="pose_shift"):
    return InterpretationOutput(
        interpretation_state=InterpretationState.SELECT_TERMS,
        clarification_type=None,
        selections=[InterpretationSelection(
            role=Role.POSE, term_id=term_id, evidence=["한쪽 다리에 체중"], confidence=0.9
        )],
        unresolved_constraints=[],
        clarifying_question=None,
    )


class FakeJobs:
    def __init__(self, job=JOB, *, stale_status=None, stale_heartbeat=False):
        self.job = job
        self.stale_status = stale_status
        self.stale_heartbeat = stale_heartbeat
        self.writes = []
        self.heartbeats = 0

    async def claim_next(self):
        return self.job

    async def extend_lease(self, *, job_id, attempt):
        assert (job_id, attempt) == (self.job["job_id"], self.job["attempt"])
        self.heartbeats += 1
        if self.stale_heartbeat:
            raise StaleJobAttempt

    async def update_status(self, *, job_id, status, attempt, result=None, failure=None):
        assert job_id == self.job["job_id"]
        assert attempt == self.job["attempt"]
        if status is self.stale_status:
            raise StaleJobAttempt
        self.writes.append((status, result, failure))


class FakeRecovery:
    def __init__(self):
        self.failures = []

    async def handle_attempt_failure(self, **kwargs):
        self.failures.append(kwargs)
        return True


class FakeAdapter:
    def __init__(self, output=None, error=None):
        self.output = output or _selected()
        self.error = error
        self.calls = []

    async def interpret(self, request_text, **kwargs):
        self.calls.append((request_text, kwargs))
        if self.error:
            raise self.error
        return self.output


class BlockingAdapter:
    def __init__(self):
        self.started = asyncio.Event()

    async def interpret(self, request_text, **kwargs):
        self.started.set()
        await asyncio.Future()


def _run(coro):
    return asyncio.run(coro)


def _worker(monkeypatch, jobs, recovery, snapshot, adapter, heartbeat_interval=10):
    monkeypatch.setattr(agent_worker, "JobRepository", lambda _pool: jobs)
    monkeypatch.setattr(agent_worker, "JobRetryRecovery", lambda _pool: recovery)
    return AgentJobWorker(
        object(), snapshot, adapter=adapter, heartbeat_interval=heartbeat_interval
    )


def test_worker_runs_claimed_job_through_assembler(monkeypatch, snapshot_factory, card_factory):
    snapshot = snapshot_factory([card_factory("pose_shift", role="pose")])
    jobs, recovery, adapter = FakeJobs(), FakeRecovery(), FakeAdapter()

    _run(_worker(monkeypatch, jobs, recovery, snapshot, adapter).run_once())

    assert [entry[0] for entry in jobs.writes] == [
        JobStatus.VALIDATING,
        JobStatus.SEARCHING,
        JobStatus.RENDERING,
        JobStatus.COMPLETED,
    ]
    assert jobs.writes[-1][1].agent_status is AgentStatus.SUCCESS
    assert adapter.calls[0][1] == {
        "job_id": "job-1",
        "session_id": "session-1",
        "attempt": 2,
        "max_attempts": 3,
        "active_cards_json": '{"active_cards": [{"role": "pose", "term_id": "pose_shift", '
        '"label_ko": "라벨", "confidence_gate": {"require_any": ["단서 A"], '
        '"do_not_infer_from": ["단서 B"]}, "requires_all_of": [], "requires_any_of": []}]}',
    }
    assert recovery.failures == []


def test_worker_stores_clarification_as_completed(monkeypatch, snapshot_factory):
    output = InterpretationOutput(
        interpretation_state=InterpretationState.NEEDS_CLARIFICATION,
        clarification_type=ClarificationType.ABSTRACT_INTENT,
        selections=[],
        unresolved_constraints=["구체적인 포즈 단서가 없음"],
        clarifying_question="어떤 자세를 원하시나요?",
    )
    jobs = FakeJobs()

    _run(_worker(
        monkeypatch, jobs, FakeRecovery(), snapshot_factory([]), FakeAdapter(output)
    ).run_once())

    result = jobs.writes[-1][1]
    assert jobs.writes[-1][0] is JobStatus.COMPLETED
    assert result.agent_status is AgentStatus.NEEDS_CLARIFICATION
    assert result.clarifying_question == "어떤 자세를 원하시나요?"


def test_worker_stores_partial_result_as_completed(
    monkeypatch, snapshot_factory, card_factory
):
    jobs = FakeJobs()
    snapshot = snapshot_factory([card_factory("pose_shift", role="pose")])
    outcomes = {
        Role.POSE: RoleSearchOutcome(role=Role.POSE, code=ReasonCode.PIN_SEARCH_UNAVAILABLE)
    }

    _run(_worker(monkeypatch, jobs, FakeRecovery(), snapshot, FakeAdapter()).run_once(
        search_outcomes=outcomes
    ))

    result = jobs.writes[-1][1]
    assert jobs.writes[-1][0] is JobStatus.COMPLETED
    assert result.agent_status is AgentStatus.PARTIAL_RESULT
    assert result.reason_codes == [ReasonCode.PIN_SEARCH_UNAVAILABLE]


@pytest.mark.parametrize("attempt", [2, 3])
def test_worker_sends_llm_failure_to_retry_policy(monkeypatch, snapshot_factory, attempt):
    job = {**JOB, "attempt": attempt}
    recovery = FakeRecovery()

    _run(_worker(
        monkeypatch, FakeJobs(job), recovery, snapshot_factory([]),
        FakeAdapter(error=LLMTimeout("timeout")),
    ).run_once())

    assert recovery.failures[0]["job_id"] == job["job_id"]
    assert recovery.failures[0]["attempt"] == attempt
    assert recovery.failures[0]["max_attempts"] == 3
    assert isinstance(recovery.failures[0]["error"], LLMTimeout)


def test_worker_stops_on_stale_attempt_without_creating_failure(
    monkeypatch, snapshot_factory, card_factory
):
    jobs, recovery = FakeJobs(stale_status=JobStatus.SEARCHING), FakeRecovery()

    snapshot = snapshot_factory([card_factory("pose_shift", role="pose")])
    _run(_worker(monkeypatch, jobs, recovery, snapshot, FakeAdapter()).run_once())

    assert [entry[0] for entry in jobs.writes] == [JobStatus.VALIDATING]
    assert recovery.failures == []


def test_stale_heartbeat_cancels_worker_without_failure(monkeypatch, snapshot_factory):
    jobs, recovery, adapter = FakeJobs(stale_heartbeat=True), FakeRecovery(), BlockingAdapter()

    async def run():
        worker = _worker(
            monkeypatch, jobs, recovery, snapshot_factory([]), adapter, heartbeat_interval=0.01
        )
        task = asyncio.create_task(worker.run_once())
        await adapter.started.wait()
        await asyncio.wait_for(task, timeout=1)

    _run(run())
    assert jobs.heartbeats == 1
    assert [entry[0] for entry in jobs.writes] == [JobStatus.VALIDATING]
    assert recovery.failures == []
