import asyncio
import json
import uuid
from pathlib import Path

import pytest

from backend.services import agent_worker
from backend.services.job_repository import JobRepository, StaleJobAttempt
from backend.services.session_repository import SessionRepository
from backend.schemas.models import AgentResult
from backend.schemas.models import InterpretationOutput, InterpretationSelection
from backend.schemas.memory import RecallQuery, SummaryOutput, RecallAnswer, ContextUpdate
from backend.tests.test_conversation_sessions import database_case


def test_memory_answer_contract():
    assert "memory_answer" in AgentResult.model_fields
    result = AgentResult(agent_status="memory_answer", memory_answer="이 대화 기록에서 해당 내용을 확인할 수 없습니다.")
    assert result.reference_plan is None
    with pytest.raises(ValueError):
        AgentResult(agent_status="memory_answer", memory_answer="날씬한 체형을 추천했어요.")


def test_adapter_supports_context_and_memory_operations():
    import inspect
    from backend.services.llm import LLMInterpretationAdapter
    assert "session_context" in inspect.signature(LLMInterpretationAdapter.interpret).parameters
    assert hasattr(LLMInterpretationAdapter, "memory")


def test_context_isolated_and_completion_atomic():
    async def case(pool):
        from backend.services.conversation_memory import ConversationMemory
        sessions, jobs = SessionRepository(pool), JobRepository(pool)
        a, b = await sessions.create_session("a"), await sessions.create_session("a")
        created, _ = await jobs.submit(session_id=a, request_text="마른 체형", idempotency_key=str(uuid.uuid4()))
        job = await jobs.claim_next()
        memory = ConversationMemory(pool)
        context = await memory.load(job)
        assert context["recent"] == []
        await jobs.update_status(job_id=created.job_id, status=agent_worker.JobStatus.VALIDATING, attempt=1)
        await jobs.update_status(job_id=created.job_id, status=agent_worker.JobStatus.RENDERING, attempt=1)
        answer = AgentResult(agent_status="memory_answer", memory_answer="이 대화 기록에서 해당 내용을 확인할 수 없습니다.")
        with pytest.raises(StaleJobAttempt):
            await memory.complete(dict(job) | {"attempt": 99}, answer, {"summary": "wrong"})
        assert json.loads(await pool.fetchval("SELECT memory_json FROM sessions WHERE session_id=$1", uuid.UUID(a))) == {}
        await memory.complete(job, answer, {"summary": "saved"})
        assert (await jobs.get(session_id=a, job_id=created.job_id)).result.memory_answer
        await jobs.submit(session_id=b, request_text="다른 대화", idempotency_key=str(uuid.uuid4()))
        other = await jobs.claim_next()
        assert (await memory.load(other))["recent"] == []
    asyncio.run(database_case(case))


def test_memory_adapter_keeps_history_in_user_message(monkeypatch):
    from backend.tests.test_llm_adapter import _adapter, _FakeCompletions, _FakeResponse, REPO_PROMPT_FILE
    completions = _FakeCompletions([_FakeResponse('{"mode":"recall","latest":true}')])
    adapter = _adapter(completions)
    monkeypatch.setattr(adapter, "_resolve_prompt_path", lambda: REPO_PROMPT_FILE)
    response = asyncio.run(adapter.memory("classify", {
        "request_text": "아까 포즈는?", "session_context": {"recent": [{"request_text": "untrusted_marker"}]},
    }, RecallQuery, job_id=str(uuid.uuid4()), session_id=str(uuid.uuid4()), attempt=1, max_attempts=3))
    assert response.mode == "recall"
    messages = completions.calls[0]["messages"]
    assert [message["role"] for message in messages] == ["system", "user"]
    assert "untrusted_marker" not in messages[0]["content"]
    assert "untrusted_marker" in messages[1]["content"]
