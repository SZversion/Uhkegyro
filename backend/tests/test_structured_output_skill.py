import asyncio
import json
from pathlib import Path

import pytest

from backend.services import llm
from backend.services.structured_output import response_format
from backend.tests.test_llm_adapter import (
    SELECT_JSON, _FakeClient, _FakeCompletions, _FakeResponse, _adapter, _real_settings,
)

ROOT = Path(__file__).resolve().parents[2]


def test_schema_preserves_code_types_and_requires_nullable_fields():
    schema = response_format()["json_schema"]["schema"]
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False
    assert schema["properties"]["selections"]["type"] == "array"
    selection = schema["$defs"]["InterpretationSelection"]
    assert set(selection["required"]) == set(selection["properties"])
    assert {"role", "term_id", "evidence", "confidence", "source_job_id"} <= set(selection["required"])
    assert selection["properties"]["confidence"]["minimum"] == 0
    assert selection["properties"]["confidence"]["maximum"] == 1
    assert {item["type"] for item in schema["properties"]["clarifying_question"]["anyOf"]} == {"string", "null"}


def test_duplicate_role_feedback_is_used_on_next_single_call():
    payload = json.loads(SELECT_JSON)
    payload["selections"].append(payload["selections"][0].copy())
    completions = _FakeCompletions(responses=[_FakeResponse(json.dumps(payload)), _FakeResponse(SELECT_JSON)])
    adapter = _adapter(completions)
    kwargs = dict(job_id="job-1", session_id="session-1", max_attempts=3)
    with pytest.raises(llm.LLMInvalidStructuredOutput) as raised:
        asyncio.run(adapter.interpret("반동", attempt=1, **kwargs))
    assert raised.value.feedback == [{"path": [], "code": "role_duplicate"}]
    output = asyncio.run(adapter.interpret("반동", attempt=2, validation_feedback=raised.value.feedback, **kwargs))
    assert len(output.selections) == 1 and len(completions.calls) == 2
    sent = completions.calls[1]["messages"]
    assert sum(item["role"] == "system" for item in sent) == 1
    assert json.loads(sent[-1]["content"]) == {"validation_feedback": raised.value.feedback}


def test_feedback_never_contains_unknown_field_names_or_input_values():
    payload = json.loads(SELECT_JSON)
    payload["secret-field-marker"] = "secret-value-marker"
    with pytest.raises(llm.LLMInvalidStructuredOutput) as raised:
        llm._validate_output(json.dumps(payload))
    assert raised.value.feedback == [{"path": ["unknown_field"], "code": "extra_forbidden"}]
    assert "secret" not in json.dumps(raised.value.feedback)


def test_missing_skill_fails_before_call():
    settings = _real_settings().model_copy(update={"structured_output_skill_path": "missing-skill.md"})
    with pytest.raises(llm.PromptConfigurationError):
        llm.LLMInterpretationAdapter(settings=settings, client=object(),
                                    prompt_path=ROOT / "prompts/uhkegryo-interpreter-v2.md")


def test_v2_call_combines_semantic_and_output_instructions():
    settings = _real_settings().model_copy(update={"interpreter_prompt_version": "uhkegryo-interpreter-v2"})
    completions = _FakeCompletions(responses=[_FakeResponse(SELECT_JSON)])
    adapter = llm.LLMInterpretationAdapter(settings=settings, client=_FakeClient(completions),
                                         prompt_path=ROOT / "prompts/uhkegryo-interpreter-v2.md")
    asyncio.run(adapter.interpret("반동", job_id="j", session_id="s", attempt=1, max_attempts=3))
    system = completions.calls[0]["messages"][0]["content"]
    assert "semantic interpreter" in system and "role_duplicate" in system
    assert adapter.prompt_version == "uhkegryo-interpreter-v2"


def test_v2_preserves_main_memory_instructions():
    baseline = (ROOT / "prompts/uhkegryo-interpreter-v0.md").read_text(encoding="utf-8")
    current = (ROOT / "prompts/uhkegryo-interpreter-v2.md").read_text(encoding="utf-8")
    for operation in ("classify", "summarize", "answer"):
        heading = "## Memory " + operation
        assert llm._extract_fenced_block(current, heading) == llm._extract_fenced_block(baseline, heading)
