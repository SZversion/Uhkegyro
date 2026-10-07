"""Refresh summaries independently; database records are the durable backlog."""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from types import SimpleNamespace

from asyncpg import InterfaceError

from backend.services import conversation_context
from backend.services.conversation_memory import ConversationMemory
from backend.services.llm import LLMInterpretationAdapter

logger = logging.getLogger(__name__)
LOCK_KEY = 734209116


@asynccontextmanager
async def summary_connection(pool):
    async with pool.acquire() as connection:
        try:
            yield connection
        finally:
            try:
                if connection.is_closed():
                    connection.terminate()
            except InterfaceError:
                # asyncpg already detached this proxy and returned its slot.
                pass


async def refresh_once(pool, tracer, adapter=None):
    async with summary_connection(pool) as connection:
        if not await connection.fetchval("SELECT pg_try_advisory_lock($1)", LOCK_KEY):
            return False
        try:
            row = await connection.fetchrow("""
                SELECT j.*, now() AS summary_cutoff FROM sessions s
                JOIN LATERAL (SELECT * FROM jobs WHERE session_id=s.session_id
                    AND status IN ('completed','failed') ORDER BY created_at DESC,job_id DESC
                    LIMIT 1) j ON true
                JOIN LATERAL (SELECT created_at,job_id FROM jobs WHERE session_id=s.session_id
                    AND status IN ('completed','failed') ORDER BY created_at DESC,job_id DESC
                    OFFSET 6 LIMIT 1) older ON true
                WHERE s.last_activity_at + interval '3 months' > now()
                  AND (s.memory_json->'summarized_through' IS NULL OR
                       (older.created_at,older.job_id) >
                       ((s.memory_json->'summarized_through'->>0)::timestamptz,
                        (s.memory_json->'summarized_through'->>1)::uuid))
                ORDER BY j.created_at,s.session_id LIMIT 1
            """)
            if row is None:
                return False
            job = dict(row)
            job["created_at"] = job.pop("summary_cutoff")
            memory = ConversationMemory(connection)
            initial = await memory.load(job)
            with tracer._session(str(job["session_id"])), tracer._observation(
                name="conversation-summary-background",
                metadata={"session_id": str(job["session_id"]), "job_id": str(job["job_id"])},
            ):
                trace = SimpleNamespace(stage=lambda name: tracer._observation(name=name))
                context = await conversation_context.summarize(
                    memory, job, adapter or LLMInterpretationAdapter(), trace)
            state = context["state"]
            fields = {key: state[key] for key in ("summary", "summary_sources", "summarized_through")
                      if key in state}
            await connection.execute("""
                UPDATE sessions SET memory_json=memory_json || $2::jsonb WHERE session_id=$1
                  AND last_activity_at + interval '3 months' > now()
                  AND memory_json->'summarized_through' IS NOT DISTINCT FROM $3::jsonb
            """, job["session_id"], json.dumps(fields),
                json.dumps(initial["state"]["summarized_through"])
                if "summarized_through" in initial["state"] else None)
            return True
        finally:
            await connection.execute("SELECT pg_advisory_unlock($1)", LOCK_KEY)


async def run_summary_loop(pool, tracer):
    adapter = None
    while True:
        delay = 1
        try:
            if adapter is None:
                adapter = LLMInterpretationAdapter()
            await refresh_once(pool, tracer, adapter)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.warning("conversation summary refresh failed", extra={"error_type": type(error).__name__})
            delay = 30
        await asyncio.sleep(delay)
