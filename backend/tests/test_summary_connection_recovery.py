import asyncio
import os
from contextlib import asynccontextmanager
from types import SimpleNamespace

import asyncpg
import pytest

from backend.schemas.memory import SummaryOutput
from backend.services.conversation_summary_worker import refresh_once, summary_connection
from backend.services.job_trace import JobTracer
from backend.tests.test_conversation_sessions import database_case
from backend.tests.test_memory_latency import seed


@pytest.mark.parametrize("size", [1, 10])
def test_summary_llm_wait_returns_all_pool_slots(size):
    async def case(pool):
        session = await seed(pool)
        schema = await pool.fetchval('SELECT current_schema()')
        target = await asyncpg.create_pool(os.environ['MEMORY_TEST_DATABASE_URL'], min_size=size, max_size=size,
                                          server_settings={'search_path': schema})
        started, release = asyncio.Event(), asyncio.Event()
        async def blocked(operation, data, *args, **kwargs):
            started.set()
            await release.wait()
            return SummaryOutput(text='요약', source_job_ids=[data['records'][-1]['job_id']])
        task = asyncio.create_task(refresh_once(target, JobTracer(), SimpleNamespace(memory=blocked), session_id=session))
        acquired = []
        try:
            await asyncio.wait_for(started.wait(), 2)
            async def reserve():
                acquired.append(await target.acquire())
            await asyncio.wait_for(asyncio.gather(*(reserve() for _ in range(size))), 2)
            assert len(acquired) == size
            assert await acquired[0].fetchval('SELECT 1') == 1
            for connection in acquired:
                await target.release(connection)
            acquired.clear()
            release.set()
            assert await asyncio.wait_for(task, 2)
            assert await pool.fetchval("SELECT memory_json->>'summary_input_hash' FROM sessions WHERE session_id=$1", session)
        finally:
            for connection in acquired:
                await target.release(connection)
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await target.close()
    asyncio.run(database_case(case))


def test_already_released_proxy_preserves_original_exception():
    class Released:
        def is_closed(self):
            raise asyncpg.InterfaceError('connection has been released back to the pool')
    class Pool:
        @asynccontextmanager
        async def acquire(self):
            yield Released()
    async def case():
        with pytest.raises(ValueError, match='original failure'):
            async with summary_connection(Pool()):
                raise ValueError('original failure')
    asyncio.run(case())


def test_healthy_summary_keeps_same_connection():
    async def case(pool):
        schema = await pool.fetchval('SELECT current_schema()')
        target = await asyncpg.create_pool(os.environ['MEMORY_TEST_DATABASE_URL'], min_size=1, max_size=1,
                                          server_settings={'search_path': schema})
        try:
            pid = await target.fetchval('SELECT pg_backend_pid()')
            from uuid import uuid4
            assert not await refresh_once(target, JobTracer(), None, session_id=uuid4())
            assert await target.fetchval('SELECT pg_backend_pid()') == pid
        finally:
            await target.close()
    asyncio.run(database_case(case))
