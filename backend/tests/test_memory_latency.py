import asyncio
import json
import uuid
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from backend.services import conversation_context
from backend.schemas.enums import JobStatus
from backend.schemas.memory import NO_RECORDS
from backend.services.conversation_memory import ConversationMemory
from backend.services.conversation_summary_worker import refresh_once
from backend.services.job_repository import JobRepository
from backend.services.job_trace import JobTracer
from backend.services.session_repository import SessionRepository
from backend.tests.test_conversation_memory import MemoryAdapter
from backend.tests.test_conversation_sessions import database_case


@pytest.mark.parametrize("text,fast", [
    ("마른 캐릭터가 서 있는 자세 레퍼런스를 찾아줘", True),
    ("Find character pose references", True),
    ("아까 추천한 포즈는?", False), ("추천했던 자세 이름은?", False),
    ("아까보다 팔을 높여줘", False), ("포즈만 앉은 모습으로 바꿔줘", False),
    ("앉은 자세로", False), ("이전에라는 단어가 적힌 캐릭터를 그려줘", False),
    ("What pose did you suggest?", False), ("지난번 결과와 같은 자세를 찾아줘", False),
    ("이 캐릭터를 더 자연스럽게", False),
])
def test_conservative_recall_gate(text, fast):
    assert conversation_context.is_clear_new_request(text, {"state": {}}) is fast
    assert not conversation_context.is_clear_new_request(text, {"state": {"pending_question": "어떤 자세인가요?"}})


def test_fast_path_preserves_context_without_classification():
    async def case():
        context = {"state": {"constraints": {"body": {"term_id": "slim"}}}}
        adapter = SimpleNamespace(memory=lambda *a, **k: pytest.fail("classify must not run"))
        result = await conversation_context.recall(None, {"request_text": "마른 캐릭터 자세를 찾아줘"},
                                                   context, adapter, None)
        assert result == (None, False)
        assert context["state"]["constraints"]["body"]["term_id"] == "slim"
    asyncio.run(case())


async def seed(pool):
    session = await SessionRepository(pool).create_session("summary-test")
    await pool.execute("""INSERT INTO jobs(job_id,session_id,request_text,request_text_hash,
        idempotency_key_hash,idempotency_expires_at,status,final_payload_json,created_at)
        SELECT gen_random_uuid(),$1::uuid,'서 있는 자세',md5(g::text),md5(g::text),
        now()+interval '10 minutes','completed','{"agent_status":"success"}'::jsonb,
        now()-interval '1 day'+g*interval '1 second' FROM generate_series(1,9) g""", session)
    return uuid.UUID(session)


def test_background_refresh_restart_lock_and_concurrent_completion():
    async def case(pool):
        session = await seed(pool)
        jobs, memory = JobRepository(pool), ConversationMemory(pool)
        new, _ = await jobs.submit(session_id=str(session), request_text="새로운 요청", idempotency_key=str(uuid.uuid4()))
        job = await jobs.claim_next()
        adapter, tracer = MemoryAdapter(), JobTracer()
        context = await conversation_context.prepare(memory, job, adapter, SimpleNamespace(stage=lambda *_: nullcontext()))
        assert adapter.summary_calls == 0 and context["summary_incomplete"]
        started, release = asyncio.Event(), asyncio.Event()
        original = adapter.memory
        async def blocked(*args, **kwargs):
            started.set()
            await release.wait()
            return await original(*args, **kwargs)
        adapter.memory = blocked
        task = asyncio.create_task(refresh_once(pool, tracer, adapter))
        await asyncio.wait_for(started.wait(), 2)
        assert not await refresh_once(pool, tracer, adapter)
        release.set()
        assert await task
        saved = json.loads(await pool.fetchval("SELECT memory_json FROM sessions WHERE session_id=$1", session))
        assert saved["summarized_through"] and adapter.summary_calls == 1
        # A foreground context loaded before refresh must preserve its newer summary.
        for status in (JobStatus.VALIDATING, JobStatus.RENDERING):
            await jobs.update_status(job_id=str(new.job_id), attempt=1, status=status)
        from backend.schemas.models import AgentResult
        await memory.complete(job, AgentResult(agent_status="memory_answer", memory_answer=NO_RECORDS),
                              context["state"] | {"pending_question": "자세?"})
        state = json.loads(await pool.fetchval("SELECT memory_json FROM sessions WHERE session_id=$1", session))
        assert state["summary"] == saved["summary"] and state["pending_question"] == "자세?"
        # A new worker instance picks up newly aged-out records, then reaches no backlog.
        assert await refresh_once(pool, JobTracer(), MemoryAdapter())
        assert not await refresh_once(pool, JobTracer(), MemoryAdapter())
        assert json.loads(await pool.fetchval("SELECT memory_json FROM sessions WHERE session_id=$1", session))["pending_question"] == "자세?"
    asyncio.run(database_case(case))


def test_summary_source_validation_preserves_watermark():
    async def case(pool):
        from backend.schemas.memory import SummaryOutput
        from backend.services.llm import LLMInvalidStructuredOutput
        session = await seed(pool)
        async def invalid(*args, **kwargs):
            return SummaryOutput(text="요약", source_job_ids=[uuid.uuid4()])
        with pytest.raises(LLMInvalidStructuredOutput):
            await refresh_once(pool, JobTracer(), SimpleNamespace(memory=invalid))
        assert json.loads(await pool.fetchval("SELECT memory_json FROM sessions WHERE session_id=$1", session)) == {}
        assert await refresh_once(pool, JobTracer(), MemoryAdapter())
    asyncio.run(database_case(case))


def test_worker_shutdown_waits_for_summary_loop(monkeypatch, snapshot_factory):
    async def case():
        from backend.services import conversation_summary_worker
        from backend.services.agent_worker import AgentJobWorker
        started, stopped = asyncio.Event(), asyncio.Event()
        async def blocked(*args):
            started.set()
            try:
                await asyncio.Future()
            finally:
                stopped.set()
        monkeypatch.setattr(conversation_summary_worker, "run_summary_loop", blocked)
        tracer = SimpleNamespace(shutdown=lambda: stopped.is_set() or pytest.fail("summary still running"))
        worker = AgentJobWorker(None, snapshot_factory([]), tracer=tracer)
        task = asyncio.create_task(worker.run_forever(concurrency=0))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert stopped.is_set()
    asyncio.run(case())


def test_worker_fast_path_and_pending_question_keep_context(snapshot_factory, card_factory):
    async def case(pool):
        from backend.services.agent_worker import AgentJobWorker
        session = await SessionRepository(pool).create_session("routing-test")
        jobs, adapter = JobRepository(pool), MemoryAdapter()
        operations = []
        original = adapter.memory
        async def counted(operation, *args, **kwargs):
            operations.append(operation)
            return await original(operation, *args, **kwargs)
        adapter.memory = counted
        worker = AgentJobWorker(pool, snapshot_factory([card_factory("pose_standing")]), adapter=adapter)
        for _ in range(2):
            await jobs.submit(session_id=session, request_text="캐릭터가 서 있는 자세를 찾아줘", idempotency_key=str(uuid.uuid4()))
            assert await worker.run_once()
        assert operations == [] and adapter.contexts[1]["constraints"]["pose"]["term_id"] == "pose_standing"
        await pool.execute("UPDATE sessions SET memory_json=memory_json || $2::jsonb WHERE session_id=$1",
                           uuid.UUID(session), json.dumps({"pending_question": "어떤 자세를 원하시나요?"}))
        await jobs.submit(session_id=session, request_text="서 있는 자세", idempotency_key=str(uuid.uuid4()))
        assert await worker.run_once()
        assert operations == ["classify"] and adapter.contexts[-1]["pending_question"] == "어떤 자세를 원하시나요?"
    asyncio.run(database_case(case))


def test_cancelled_summary_is_resumable_and_does_not_block_answer():
    async def case(pool):
        session = await seed(pool)
        started = asyncio.Event()
        adapter = MemoryAdapter()
        async def blocked(*args, **kwargs):
            started.set()
            await asyncio.Event().wait()
        adapter.memory = blocked
        task = asyncio.create_task(refresh_once(pool, JobTracer(), adapter))
        await asyncio.wait_for(started.wait(), 2)
        memory = ConversationMemory(pool)
        job = await pool.fetchrow("SELECT *, now() AS cutoff FROM jobs WHERE session_id=$1 LIMIT 1", session)
        job = dict(job) | {"created_at": job["cutoff"]}
        context = await asyncio.wait_for(conversation_context.prepare(memory, job, adapter, None), .5)
        assert context["summary_incomplete"]
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert json.loads(await pool.fetchval("SELECT memory_json FROM sessions WHERE session_id=$1", session)) == {}
        assert await refresh_once(pool, JobTracer(), MemoryAdapter())
    asyncio.run(database_case(case))
