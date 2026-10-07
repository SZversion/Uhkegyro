import asyncio
import os
from contextlib import asynccontextmanager
from types import SimpleNamespace

import asyncpg
import pytest

from backend.schemas.memory import SummaryOutput
from backend.services.conversation_summary_worker import LOCK_KEY, refresh_once, summary_connection
from backend.services.job_trace import JobTracer
from backend.tests.test_conversation_sessions import database_case
from backend.tests.test_memory_latency import seed


@pytest.mark.parametrize("size", [1, 10])
def test_repeated_disconnect_returns_all_pool_slots(size):
    async def case(pool):
        session = await seed(pool)
        schema = await pool.fetchval('SELECT current_schema()')
        admin = await asyncpg.connect(os.environ['MEMORY_TEST_DATABASE_URL'])
        name = 'summary_recovery_' + schema
        target = await asyncpg.create_pool(os.environ['MEMORY_TEST_DATABASE_URL'], min_size=size, max_size=size,
                                          server_settings={'search_path': schema, 'application_name': name})
        task = None
        async def success(operation, data, *args, **kwargs):
            return SummaryOutput(text='요약', source_job_ids=[data['records'][-1]['job_id']])
        try:
            for _ in range(20):
                started, release = asyncio.Event(), asyncio.Event()
                async def blocked(operation, data, *args, **kwargs):
                    started.set()
                    await release.wait()
                    return await success(operation, data, *args, **kwargs)
                task = asyncio.create_task(refresh_once(target, JobTracer(), SimpleNamespace(memory=blocked)))
                await asyncio.wait_for(started.wait(), 2)
                pid = await admin.fetchval("""SELECT l.pid FROM pg_locks l JOIN pg_stat_activity a USING(pid)
                    WHERE l.locktype='advisory' AND l.objid=$1 AND a.application_name=$2""", LOCK_KEY, name)
                assert pid is not None and await admin.fetchval('SELECT pg_terminate_backend($1)', pid)
                release.set()
                with pytest.raises((asyncpg.InterfaceError, asyncpg.PostgresError)):
                    await asyncio.wait_for(task, 2)
                assert await admin.fetchval('SELECT pg_try_advisory_lock($1)', LOCK_KEY)
                await admin.execute('SELECT pg_advisory_unlock($1)', LOCK_KEY)
                # Reserve every slot: a successful SELECT alone misses partial capacity loss.
                acquired = []
                async def reserve():
                    acquired.append(await target.acquire())
                try:
                    await asyncio.wait_for(asyncio.gather(*(reserve() for _ in range(size))), 2)
                    assert len(acquired) == size
                finally:
                    for connection in acquired:
                        await target.release(connection)
                assert await asyncio.wait_for(target.fetchval('SELECT 1'), 2) == 1
            assert await asyncio.wait_for(refresh_once(target, JobTracer(), SimpleNamespace(memory=success)), 2)
            assert await pool.fetchval("SELECT memory_json->'summarized_through' FROM sessions WHERE session_id=$1", session)
        finally:
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            target.terminate()
            await admin.close()
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
            assert not await refresh_once(target, JobTracer(), None)
            assert await target.fetchval('SELECT pg_backend_pid()') == pid
        finally:
            await target.close()
    asyncio.run(database_case(case))
