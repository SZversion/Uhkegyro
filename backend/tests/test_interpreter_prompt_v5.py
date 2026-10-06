import asyncio
import json
from pathlib import Path

import pytest

from backend.schemas.models import InterpretationOutput
from backend.services.llm import (
    LLMInterpretationAdapter, LLMInvalidStructuredOutput, PromptConfigurationError,
    _extract_fenced_block, load_interpreter_prompt,
)
from backend.tests.test_llm_adapter import (
    SELECT_JSON, CLARIFY_JSON, _FakeClient, _FakeCompletions, _FakeResponse, _real_settings,
)

ROOT = Path(__file__).resolve().parents[2]
V5 = ROOT / "prompts/uhkegryo-interpreter-v5.md"
ROLES = ("body", "pose", "view", "perspective", "layout")
CARDS = '{"active_cards":[{"role":"pose","term_id":"pose_contrapposto"}]}'


def adapter(completions, path=V5):
    return LLMInterpretationAdapter(client=_FakeClient(completions), prompt_path=path,
        settings=_real_settings().model_copy(update={"interpreter_prompt_version": "uhkegryo-interpreter-v5"}))


def slots(raw):
    payload = json.loads(raw)
    for field in ("selections", "context_updates"):
        payload[field] = {role: next((s for s in payload.get(field, []) if s["role"] == role), None) for role in ROLES}
    return payload


def invoke(a, **kwargs):
    return asyncio.run(a.interpret("반동", job_id="j", session_id="s", attempt=kwargs.pop("attempt", 1),
        max_attempts=3, active_cards_json=CARDS, **kwargs))


@pytest.mark.parametrize("raw", [SELECT_JSON, CLARIFY_JSON])
def test_v5_sends_file_instructions_once_and_normalizes_slots(raw):
    completions = _FakeCompletions(responses=[_FakeResponse(json.dumps(slots(raw)))])
    result = invoke(adapter(completions))
    call = completions.calls[0]
    system, template = load_interpreter_prompt(V5)
    assert call["messages"][0]["content"] == system
    assert template.count("{{request_text}}") == 1
    assert template.index("{{active_cards_json}}") < template.index("{{request_text}}")
    assert call["messages"][1]["content"].count("반동") == 1
    assert call["response_format"]["json_schema"]["strict"] is True
    assert call["response_format"]["json_schema"]["schema"]["properties"]["selections"]["type"] == "object"
    assert len(result.selections) == (1 if raw == SELECT_JSON else 0)


@pytest.mark.parametrize("bad", ["array", "missing", "wrong_role"])
def test_invalid_slots_fail_and_feedback_can_repair(bad):
    payload = slots(SELECT_JSON)
    if bad == "array":
        payload["selections"] = json.loads(SELECT_JSON)["selections"]
    elif bad == "missing":
        del payload["selections"]["view"]
    else:
        payload["selections"]["pose"]["role"] = "view"
    completions = _FakeCompletions(responses=[_FakeResponse(json.dumps(payload)),
        _FakeResponse(json.dumps(slots(SELECT_JSON)))])
    a = adapter(completions)
    with pytest.raises(LLMInvalidStructuredOutput) as error:
        invoke(a)
    assert error.value.retryable
    result = invoke(a, attempt=2, validation_feedback=error.value.feedback)
    assert result.selections[0].role == "pose"
    if error.value.feedback:
        assert json.loads(completions.calls[-1]["messages"][-1]["content"]) == {
            "validation_feedback": error.value.feedback}


@pytest.mark.parametrize("cards", ["", '{"active_cards":[]}', "invalid"])
def test_empty_catalog_fails_before_model_call(cards):
    completions = _FakeCompletions()
    with pytest.raises(PromptConfigurationError):
        asyncio.run(adapter(completions).interpret("입력", job_id="j", session_id="s",
            attempt=1, max_attempts=3, active_cards_json=cards))
    assert completions.calls == []


def test_wrong_version_file_is_rejected_and_memory_prompts_are_unchanged():
    with pytest.raises(PromptConfigurationError):
        adapter(_FakeCompletions(), ROOT / "prompts/uhkegryo-interpreter-v4.md")
    v4 = (ROOT / "prompts/uhkegryo-interpreter-v4.md").read_text(encoding="utf-8")
    for section in ("classify", "summarize", "answer"):
        assert _extract_fenced_block(V5.read_text(encoding="utf-8"), "## Memory " + section) == (
            _extract_fenced_block(v4, "## Memory " + section))


def test_all_prompt_examples_follow_the_slot_and_state_contract():
    system, _ = load_interpreter_prompt(V5)
    examples = [json.loads(line) for line in system.splitlines() if line.startswith('{"interpretation_state"')]
    assert len(examples) == 3
    for payload in examples:
        assert set(payload) == set(InterpretationOutput.model_fields)
        for field in ("selections", "context_updates"):
            assert set(payload[field]) == set(ROLES)
            assert all(value is None or value["role"] == role for role, value in payload[field].items())
            payload[field] = [payload[field][role] for role in ROLES if payload[field][role] is not None]
        InterpretationOutput.model_validate(payload)
