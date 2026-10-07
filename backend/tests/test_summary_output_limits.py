import asyncio
import json
import uuid

import pytest

from backend.schemas.memory import SummaryOutput
from backend.services.conversation_summary_worker import refresh_once
from backend.services.job_trace import JobTracer
from backend.services.llm import LLMInvalidStructuredOutput
from backend.tests.test_conversation_sessions import database_case
from backend.tests.test_llm_adapter import _adapter, _FakeCompletions, _FakeResponse, REPO_PROMPT_FILE
from backend.tests.test_memory_latency import seed


def adapter_for(text, monkeypatch):
    completions = _FakeCompletions([_FakeResponse(json.dumps({"text": text, "source_job_ids": []}))])
    adapter = _adapter(completions)
    monkeypatch.setattr(adapter, "_resolve_prompt_path", lambda: REPO_PROMPT_FILE.with_name("uhkegryo-interpreter-v4.md"))
    return adapter, completions


def memory_call(adapter):
    return adapter.memory("summarize", {"records": []}, SummaryOutput,
                          job_id=str(uuid.uuid4()), session_id=str(uuid.uuid4()), attempt=1, max_attempts=3)


@pytest.mark.parametrize("length", [1, 399, 400, 600])
def test_summary_adapter_accepts_short_and_boundary_outputs(length, monkeypatch):
    text = "요" * length
    adapter, completions = adapter_for(text, monkeypatch)
    assert asyncio.run(memory_call(adapter)).text == text
    instructions = completions.calls[0]["messages"][0]["content"]
    assert "at most 600 characters" in instructions and "never pad" in instructions
    schema = json.loads(instructions.split("Return only JSON matching this schema:\n", 1)[1])
    assert schema["properties"]["text"]["minLength"] == 1
    assert schema["properties"]["text"]["maxLength"] == 600


@pytest.mark.parametrize("length", [0, 601])
def test_summary_adapter_rejects_empty_and_oversized_outputs(length, monkeypatch):
    adapter, _ = adapter_for("요" * length, monkeypatch)
    with pytest.raises(LLMInvalidStructuredOutput) as error:
        asyncio.run(memory_call(adapter))
    assert error.value.stage == "memory_schema"


def test_oversized_summary_does_not_replace_saved_memory(monkeypatch):
    async def case(pool):
        session = await seed(pool)
        before = {"summary": "기존 요약", "summary_sources": [], "summary_input_hash": "previous",
                  "pending_question": "어떤 포즈인가요?"}
        await pool.execute("UPDATE sessions SET memory_json=$2::jsonb WHERE session_id=$1", session, json.dumps(before))
        adapter, _ = adapter_for("요" * 601, monkeypatch)
        with pytest.raises(LLMInvalidStructuredOutput):
            await refresh_once(pool, JobTracer(), adapter, session_id=session)
        after = json.loads(await pool.fetchval("SELECT memory_json FROM sessions WHERE session_id=$1", session))
        assert after == before
    asyncio.run(database_case(case))
