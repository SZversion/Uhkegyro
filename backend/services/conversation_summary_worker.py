"""Summarize only conversations signalled by a completed request."""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

from asyncpg import InterfaceError

from backend.services import conversation_context
from backend.services.conversation_memory import ConversationMemory, summary_input
from backend.services.llm import LLMInterpretationAdapter

logger = logging.getLogger(__name__)


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


async def summary_snapshot(pool, session_id):
    async with summary_connection(pool) as connection:
        row = await connection.fetchrow("""SELECT j.*, now() AS summary_cutoff FROM sessions s
            JOIN LATERAL (SELECT * FROM jobs WHERE session_id=s.session_id AND status='completed'
                AND final_payload_json->>'agent_status' NOT IN ('unsafe_input','out_of_scope')
                ORDER BY created_at DESC,job_id DESC LIMIT 1) j ON true
            WHERE s.session_id=$1 AND s.last_activity_at + interval '3 months' > now()""", session_id)
        if row is None:
            return None
        job = dict(row)
        job["created_at"] = job.pop("summary_cutoff")
        memory = ConversationMemory(connection)
        context = await memory.load(job)
        rows = await memory.older(job, context)
    data = summary_input(context, rows)
    if not data["records"] or context["state"].get("summary_input_hash") == data["input_hash"]:
        return None
    return job, context, rows


async def refresh_once(pool, tracer, adapter=None, *, session_id):
    snapshot = await summary_snapshot(pool, session_id)
    if snapshot is None:
        return False
    job, initial, rows = snapshot
    token = str(uuid4())
    async with summary_connection(pool) as connection:
        claimed = await connection.fetchval("""UPDATE sessions SET memory_json=memory_json ||
            jsonb_build_object('summary_claim', jsonb_build_object('token',$2::text,
                'expires_at',now()+interval '60 seconds'))
            WHERE session_id=$1 AND last_activity_at + interval '3 months' > now()
              AND (memory_json->'summary_claim' IS NULL OR
                   (memory_json->'summary_claim'->>'expires_at')::timestamptz <= now())
              AND memory_json->>'summary_input_hash' IS NOT DISTINCT FROM $3::text
            RETURNING true""", session_id, token, initial["state"].get("summary_input_hash"))
    if not claimed:
        return False
    try:
        with tracer._session(str(session_id)), tracer._observation(
            name="conversation-summary-background",
            metadata={"session_id": str(session_id), "job_id": str(job["job_id"])},
        ):
            trace = SimpleNamespace(stage=lambda name: tracer._observation(name=name))
            context = await conversation_context.summarize(
                ConversationMemory(pool), job, adapter or LLMInterpretationAdapter(), trace,
                context=initial, rows=rows)
        fields = {key: context["state"][key] for key in (
            "summary", "summary_sources", "summary_input_hash", "summary_truncated")}
        async with summary_connection(pool) as connection:
            stored = await connection.execute("""UPDATE sessions
                SET memory_json=(memory_json - 'summary_claim' - 'summarized_through') || $3::jsonb
                WHERE session_id=$1 AND memory_json->'summary_claim'->>'token'=$2
                  AND (memory_json->'summary_claim'->>'expires_at')::timestamptz > now()
                  AND last_activity_at + interval '3 months' > now()""",
                session_id, token, json.dumps(fields))
        return stored == "UPDATE 1"
    finally:
        try:
            async with summary_connection(pool) as connection:
                await connection.execute("""UPDATE sessions SET memory_json=memory_json - 'summary_claim'
                    WHERE session_id=$1 AND memory_json->'summary_claim'->>'token'=$2""", session_id, token)
        except Exception as error:
            logger.warning("conversation summary claim release failed", extra={"error_type": type(error).__name__})


class SummaryRequests:
    def __init__(self, pool):
        self.pool = pool
        self.queue = asyncio.Queue()
        self.pending = set()

    async def request(self, job):
        session_id = job["session_id"]
        if session_id in self.pending or await summary_snapshot(self.pool, session_id) is None:
            return
        if session_id not in self.pending:
            self.pending.add(session_id)
            self.queue.put_nowait(session_id)


async def run_summary_loop(pool, tracer, requests):
    adapter = None
    while True:
        session_id = await requests.queue.get()
        requests.pending.discard(session_id)
        try:
            if adapter is None:
                adapter = LLMInterpretationAdapter()
            await refresh_once(pool, tracer, adapter, session_id=session_id)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.warning("conversation summary refresh failed", extra={"error_type": type(error).__name__})
        finally:
            requests.queue.task_done()
