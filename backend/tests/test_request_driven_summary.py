import asyncio
import json
import os
import uuid
from types import SimpleNamespace

import asyncpg
import pytest

from backend.schemas.memory import SummaryOutput
from backend.services import conversation_summary_worker as summaries
from backend.services.agent_worker import AgentJobWorker
from backend.services.job_repository import JobRepository
from backend.services.job_trace import JobTracer
from backend.services.session_repository import SessionRepository
from backend.tests.test_conversation_memory import MemoryAdapter
from backend.tests.test_conversation_sessions import database_case
from backend.tests.test_memory_latency import seed


async def stop(task):
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_idle_loop_never_queries_or_constructs_llm(monkeypatch):
    async def case():
        class IdlePool:
            def __getattr__(self, name):
                pytest.fail("idle summary accessed DB: " + name)
        monkeypatch.setattr(summaries, "LLMInterpretationAdapter", lambda: pytest.fail("idle LLM constructed"))
        requests = summaries.SummaryRequests(IdlePool())
        task = asyncio.create_task(summaries.run_summary_loop(requests.pool, JobTracer(), requests))
        try:
            await asyncio.sleep(.03)
            assert not task.done() and requests.queue.empty()
        finally:
            await stop(task)
    asyncio.run(case())


def test_only_needed_session_is_enqueued_and_duplicates_coalesce():
    async def case(pool):
        a = await seed(pool)
        b = await seed(pool)
        short = uuid.UUID(await SessionRepository(pool).create_session("short"))
        requests = summaries.SummaryRequests(pool)
        await requests.request({"session_id": short})
        assert requests.queue.empty()
        await asyncio.gather(*(requests.request({"session_id": a}) for _ in range(3)))
        assert requests.queue.qsize() == 1 and await requests.queue.get() == a
        requests.queue.task_done()
        requests.pending.discard(a)
        adapter = MemoryAdapter()
        assert await summaries.refresh_once(pool, JobTracer(), adapter, session_id=a)
        await requests.request({"session_id": a})
        assert requests.queue.empty()
        assert not await pool.fetchval("SELECT memory_json->>'summary' FROM sessions WHERE session_id=$1", b)
    asyncio.run(database_case(case))


def test_completed_answer_triggers_summary_and_next_answer_runs_with_one_connection(
    monkeypatch, snapshot_factory, card_factory,
):
    async def case(pool):
        session = await seed(pool)
        schema = await pool.fetchval("SELECT current_schema()")
        target = await asyncpg.create_pool(os.environ["MEMORY_TEST_DATABASE_URL"], min_size=1, max_size=1,
                                          server_settings={"search_path": schema})
        adapter = MemoryAdapter()
        started, release = asyncio.Event(), asyncio.Event()
        original = adapter.memory
        async def blocked(operation, *args, **kwargs):
            if operation == "summarize":
                started.set()
                await release.wait()
            return await original(operation, *args, **kwargs)
        adapter.memory = blocked
        monkeypatch.setattr(summaries, "LLMInterpretationAdapter", lambda: adapter)
        worker = AgentJobWorker(target, snapshot_factory([card_factory("pose_standing")]), adapter=adapter)
        loop = asyncio.create_task(summaries.run_summary_loop(target, JobTracer(), worker._summary_requests))
        jobs = JobRepository(target)
        try:
            await asyncio.sleep(.02)
            assert adapter.summary_calls == 0 and not started.is_set()
            first, _ = await jobs.submit(session_id=str(session), request_text="캐릭터가 서 있는 자세를 찾아줘",
                                         idempotency_key=str(uuid.uuid4()))
            assert await asyncio.wait_for(worker.run_once(), 2)
            await asyncio.wait_for(started.wait(), 2)
            assert (await jobs.get(session_id=str(session), job_id=first.job_id)).job_status == "completed"
            assert await asyncio.wait_for(target.fetchval("SELECT 1"), .5) == 1
            second, _ = await jobs.submit(session_id=str(session), request_text="캐릭터가 서 있는 자세를 찾아줘",
                                          idempotency_key=str(uuid.uuid4()))
            assert await asyncio.wait_for(worker.run_once(), 2)
            assert (await jobs.get(session_id=str(session), job_id=second.job_id)).job_status == "completed"
            assert adapter.summary_calls == 0
            release.set()
            await asyncio.wait_for(worker._summary_requests.queue.join(), 2)
            state = json.loads(await target.fetchval("SELECT memory_json FROM sessions WHERE session_id=$1", session))
            assert state["summary_input_hash"] and state["constraints"]["pose"]
            assert "summarized_through" not in state and "summary_claim" not in state
        finally:
            release.set()
            await stop(loop)
            await target.close()
    asyncio.run(database_case(case))


def test_failure_has_no_periodic_retry_and_next_request_can_retry(monkeypatch):
    async def case(pool):
        session = await seed(pool)
        calls = []
        async def failure(*args, **kwargs):
            calls.append(1)
            raise RuntimeError("summary failed")
        monkeypatch.setattr(summaries, "LLMInterpretationAdapter", lambda: SimpleNamespace(memory=failure))
        requests = summaries.SummaryRequests(pool)
        task = asyncio.create_task(summaries.run_summary_loop(pool, JobTracer(), requests))
        try:
            await requests.request({"session_id": session})
            await asyncio.wait_for(requests.queue.join(), 2)
            await asyncio.sleep(.03)
            assert len(calls) == 1 and requests.queue.empty()
            assert json.loads(await pool.fetchval("SELECT memory_json FROM sessions WHERE session_id=$1", session)) == {}
            await requests.request({"session_id": session})
            await asyncio.wait_for(requests.queue.join(), 2)
            assert len(calls) == 2
        finally:
            await stop(task)
    asyncio.run(database_case(case))


def test_expired_owner_cannot_overwrite_new_summary():
    async def case(pool):
        session = await seed(pool)
        started, release = asyncio.Event(), asyncio.Event()
        async def old(operation, data, *args, **kwargs):
            started.set()
            await release.wait()
            return SummaryOutput(text="old", source_job_ids=[data["records"][-1]["job_id"]])
        async def new(operation, data, *args, **kwargs):
            return SummaryOutput(text="new", source_job_ids=[data["records"][-1]["job_id"]])
        task = asyncio.create_task(summaries.refresh_once(pool, JobTracer(), SimpleNamespace(memory=old), session_id=session))
        try:
            await asyncio.wait_for(started.wait(), 2)
            assert not await summaries.refresh_once(pool, JobTracer(), SimpleNamespace(memory=new), session_id=session)
            await pool.execute("""UPDATE sessions SET memory_json=jsonb_set(memory_json,
                '{summary_claim,expires_at}',to_jsonb((now()-interval '1 second')::text)) WHERE session_id=$1""", session)
            assert await summaries.refresh_once(pool, JobTracer(), SimpleNamespace(memory=new), session_id=session)
            release.set()
            assert not await task
            state = json.loads(await pool.fetchval("SELECT memory_json FROM sessions WHERE session_id=$1", session))
            assert state["summary"] == "new" and "summary_claim" not in state
        finally:
            if not task.done():
                await stop(task)
    asyncio.run(database_case(case))


def test_legacy_watermark_is_ignored_and_snapshot_is_rewritten():
    async def case(pool):
        session = await seed(pool)
        await pool.execute("UPDATE sessions SET memory_json=$2::jsonb WHERE session_id=$1", session,
                           json.dumps({"summary": "legacy", "summary_sources": [str(uuid.uuid4())],
                                       "summarized_through": ["2099-01-01T00:00:00+00:00", str(uuid.uuid4())],
                                       "pending_question": "포즈?"}))
        async def rewritten(operation, data, *args, **kwargs):
            assert data["summary"] == "" and data["summary_sources"] == []
            assert len(data["records"]) == 3
            return SummaryOutput(text="new", source_job_ids=[data["records"][-1]["job_id"]])
        assert await summaries.refresh_once(pool, JobTracer(), SimpleNamespace(memory=rewritten), session_id=session)
        state = json.loads(await pool.fetchval("SELECT memory_json FROM sessions WHERE session_id=$1", session))
        assert state["summary"] == "new" and state["pending_question"] == "포즈?"
        assert "summarized_through" not in state
    asyncio.run(database_case(case))


@pytest.mark.parametrize("error_type", ["stale", "failure"])
def test_unsaved_answer_never_requests_summary(error_type, snapshot_factory, card_factory):
    async def case(pool):
        from backend.services.job_repository import StaleJobAttempt
        session = await seed(pool)
        jobs = JobRepository(pool)
        worker = AgentJobWorker(pool, snapshot_factory([card_factory("pose_standing")]), adapter=MemoryAdapter())
        async def fail_save(*args, **kwargs):
            raise StaleJobAttempt() if error_type == "stale" else RuntimeError("save failed")
        async def forbidden(*args, **kwargs):
            pytest.fail("unsaved answer requested summary")
        worker._memory.complete = fail_save
        worker._summary_requests.request = forbidden
        await jobs.submit(session_id=str(session), request_text="캐릭터가 서 있는 자세를 찾아줘",
                          idempotency_key=str(uuid.uuid4()))
        assert await worker.run_once()
        assert worker._summary_requests.queue.empty()
    asyncio.run(database_case(case))


def test_snapshot_character_budget_marks_missing_history():
    from backend.services.conversation_memory import summary_input
    rows = [{"job_id": str(uuid.uuid4()), "status": "completed", "request_text": "x" * 3500,
             "final_payload_json": {"agent_status": "success"}} for _ in range(20)]
    data = summary_input({}, rows)
    assert data["truncated"] and 0 < len(data["records"]) < 20
    assert len(json.dumps(data["records"], ensure_ascii=False)) <= 48_000
    assert data["records"][-1]["job_id"] == rows[-1]["job_id"]
