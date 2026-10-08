import asyncio
import json
import re
import sys
from pathlib import Path

import pytest

from backend.services import llm
from backend.services.structured_output import response_format
from backend.tests.test_llm_adapter import (
    CLARIFY_JSON, SELECT_JSON, _FakeClient, _FakeCompletions, _FakeResponse, _adapter, _real_settings,
    _langfuse_generation_kwargs,
)

ROOT = Path(__file__).resolve().parents[2]
PROMPT = ROOT / "prompts" / "uhkegryo-interpreter-v1.md"
V4_PROMPT = ROOT / "prompts" / "uhkegryo-interpreter-v4.md"


def _v4_payload(content):
    payload = json.loads(content) if isinstance(content, str) else content
    payload.setdefault("ambiguous_fields", [])
    payload.setdefault("context_updates", [])
    payload.setdefault("answer_text", "")
    for selection in payload.get("selections", []):
        selection.setdefault("source_job_id", None)
    for update in payload.get("context_updates", []):
        update.setdefault("term_id", None)
    return payload


def test_catalog_schema_limits_term_ids_to_their_role():
    cards = json.dumps({"active_cards": [
        {"role": "view", "term_id": "view_front"},
        {"role": "layout", "term_id": "layout_center"},
    ]})
    definitions = response_format(cards)["json_schema"]["schema"]["$defs"]
    for name in ("InterpretationSelection", "ContextUpdate"):
        variants = [definitions[f"{name}_{role}"] for role in ("view", "layout")]
        assert len(variants) == 2
        for variant in variants:
            properties = variant["properties"]
            role = properties["role"]["enum"][0]
            term = properties["term_id"]
            if name == "ContextUpdate":
                assert term["anyOf"][1] == {"type": "null"}
                term = term["anyOf"][0]
            assert term["enum"] == ["view_front" if role == "view" else "layout_center"]
            assert variant["additionalProperties"] is False


def test_generation_stays_open_during_upstream_call(monkeypatch):
    recorded, _ = _langfuse_generation_kwargs(monkeypatch)
    events = []
    fake = sys.modules["langfuse"].Langfuse
    original = fake.start_as_current_observation
    from contextlib import contextmanager

    @contextmanager
    def observation(self, **kwargs):
        events.append("start")
        with original(self, **kwargs) as generation:
            yield generation
        events.append("end")

    monkeypatch.setattr(fake, "start_as_current_observation", observation)

    class Completions(_FakeCompletions):
        async def create(self, **kwargs):
            assert events == ["start"]
            events.append("call")
            await asyncio.sleep(0.01)
            return await super().create(**kwargs)

    settings = _real_settings().model_copy(update={
        "langfuse_public_key": "pk-test", "langfuse_secret_key": "sk-test",
    })
    adapter = _adapter(Completions(responses=[_FakeResponse(SELECT_JSON)]), settings=settings)
    asyncio.run(adapter.interpret("반동", job_id="j", session_id="s", attempt=1, max_attempts=3))
    assert events == ["start", "call", "end"]
    assert recorded["generation_update"]["usage_details"]["total_tokens"] == 15


def test_v4_provider_schema_preserves_prompt_array_contract():
    payload = _v4_payload(SELECT_JSON)
    completions = _FakeCompletions(responses=[
        _FakeResponse(json.dumps(payload)),
        _FakeResponse("최종 답변 문장입니다."),
    ])
    adapter = _adapter(completions, settings=_real_settings().model_copy(update={
        "interpreter_prompt_version": "uhkegryo-interpreter-v4"}))
    output = asyncio.run(adapter.interpret(
        "반동", job_id="j", session_id="s", attempt=1, max_attempts=3,
        active_cards_json=json.dumps({"active_cards": [{"role": "pose", "term_id": "pose_contrapposto"}]}),
    ))

    schema = completions.calls[0]["response_format"]["json_schema"]["schema"]
    assert output.selections and output.context_updates == []
    assert "ambiguous_fields" in schema["required"]
    assert schema["properties"]["selections"]["type"] == "array"
    assert schema["properties"]["context_updates"]["type"] == "array"
    assert schema["properties"]["answer_text"]["type"] == "string"
    assert output.answer_text == "최종 답변 문장입니다."
    assert len(completions.calls) == 2


def test_v4_prompt_explains_ambiguous_fields():
    prompt = V4_PROMPT.read_text(encoding="utf-8")
    assert "ambiguous_fields" in prompt
    assert "body, pose, view, perspective, and layout" in prompt
    assert "Never include a role the user did not request" in prompt
    assert 'ambiguous_fields is ["pose"]' in prompt


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


def test_v4_schema_matches_existing_arrays_and_adds_ambiguous_fields():
    cards = json.dumps({"active_cards": [{"role": "pose", "term_id": "pose_sitting"}]})
    schema = response_format(cards, include_ambiguous_fields=True)["json_schema"]["schema"]
    assert "ambiguous_fields" in schema["required"]
    assert schema["properties"]["ambiguous_fields"]["items"]["$ref"] == "#/$defs/Role"
    assert schema["properties"]["selections"]["type"] == "array"
    assert schema["properties"]["context_updates"]["type"] == "array"
    assert schema["properties"]["answer_text"]["type"] == "string"
    assert "ambiguous_fields" not in response_format()["json_schema"]["schema"]["properties"]


def test_v4_prompt_output_examples_match_provider_schema():
    schema = response_format(include_ambiguous_fields=True)["json_schema"]["schema"]
    prompt = V4_PROMPT.read_text(encoding="utf-8")
    examples = [json.loads(block) for block in re.findall(r"```json\s*(\{.*?\})\s*```", prompt, re.DOTALL)]
    examples.extend(json.loads(line) for line in prompt.splitlines()
                    if line.startswith("{") and '"interpretation_state"' in line)
    output_examples = [example for example in examples if "interpretation_state" in example]
    assert output_examples
    for example in output_examples:
        assert set(example) == set(schema["properties"])
        assert isinstance(example["selections"], list)
        assert isinstance(example["context_updates"], list)
        assert example["answer_text"] == ""
        llm._validate_output(json.dumps(example, ensure_ascii=False), require_ambiguous_fields=True)


def test_v4_rejects_missing_ambiguous_fields():
    adapter = _adapter(
        _FakeCompletions(responses=[_FakeResponse(CLARIFY_JSON)]),
        settings=_real_settings().model_copy(update={"interpreter_prompt_version": "uhkegryo-interpreter-v4"}),
    )
    with pytest.raises(llm.LLMInvalidStructuredOutput) as raised:
        asyncio.run(adapter.interpret("망토", job_id="j", session_id="s", attempt=1, max_attempts=3))
    assert raised.value.feedback == [{"path": ["ambiguous_fields"], "code": "missing"}]


@pytest.mark.parametrize("field", ["clarification_type", "selections", "unresolved_constraints", "answer_text"])
def test_v4_validator_requires_every_schema_field(field):
    payload = _v4_payload(SELECT_JSON)
    payload.pop(field, None)
    with pytest.raises(llm.LLMInvalidStructuredOutput) as raised:
        llm._validate_output(json.dumps(payload), require_ambiguous_fields=True)
    assert raised.value.feedback == [{"path": [field], "code": "missing"}]


def test_v4_validator_rejects_answer_text_before_final_response_for_select_terms():
    payload = _v4_payload(SELECT_JSON)
    payload["answer_text"] = "첫 호출에서 만든 답변"
    with pytest.raises(llm.LLMInvalidStructuredOutput) as raised:
        llm._validate_output(json.dumps(payload), require_ambiguous_fields=True)
    assert raised.value.feedback == [{"path": ["answer_text"], "code": "must_be_empty_before_final_response"}]


def test_v4_validator_requires_empty_answer_text_for_clarification():
    payload = _v4_payload(CLARIFY_JSON)
    payload["answer_text"] = "질문 전용 경로"
    with pytest.raises(llm.LLMInvalidStructuredOutput) as raised:
        llm._validate_output(json.dumps(payload), require_ambiguous_fields=True)
    assert raised.value.feedback == [{"path": ["answer_text"], "code": "must_be_empty_before_final_response"}]


@pytest.mark.parametrize("field", ["source_job_id", "context_term_id"])
def test_v4_validator_requires_nested_schema_fields(field):
    payload = _v4_payload(SELECT_JSON)
    if field == "source_job_id":
        payload["selections"][0].pop("source_job_id")
        path = ["selections", 0, "source_job_id"]
    else:
        payload["context_updates"] = [{"role": "pose", "evidence": "반동"}]
        path = ["context_updates", 0, "term_id"]
    with pytest.raises(llm.LLMInvalidStructuredOutput) as raised:
        llm._validate_output(json.dumps(payload), require_ambiguous_fields=True)
    assert raised.value.feedback == [{"path": path, "code": "missing"}]


def test_v4_select_terms_does_not_load_clarification_skill():
    payload = _v4_payload(SELECT_JSON)
    completions = _FakeCompletions(responses=[
        _FakeResponse(json.dumps(payload)),
        _FakeResponse("최종 답변 문장입니다."),
    ])
    adapter = _adapter(completions, settings=_real_settings().model_copy(update={
        "interpreter_prompt_version": "uhkegryo-interpreter-v4",
        "clarification_skill_path": "missing-clarification-skill.md",
    }))

    context = {"constraints": [{"role": "body", "term_id": "body_slim"}]}
    output = asyncio.run(adapter.interpret(
        "반동", job_id="j", session_id="s", attempt=1, max_attempts=3, session_context=context
    ))

    assert output.interpretation_state.value == "select_terms"
    assert len(completions.calls) == 2
    first_system = completions.calls[0]["messages"][0]["content"]
    assert "For abstract_intent" not in first_system
    assert "캐주얼 캐릭터 일러스트 레퍼런스 해석 Skill" in first_system
    assert "LLM은 입력의 의미를 해석하고 허용된 `term_id` 후보와 근거를 구조화한다." in first_system
    assert "COPY skills/SKILL.md /app/skills/SKILL.md" in (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert output.answer_text == "최종 답변 문장입니다."
    final_messages = completions.calls[1]["messages"]
    assert "For abstract_intent" not in final_messages[0]["content"]
    final_input = json.loads(final_messages[1]["content"])
    assert final_input["request_text"] == "반동"
    assert final_input["validated_interpretation"]["answer_text"] == ""
    assert final_input["session_context"] == context
    assert "active_cards_json" in final_input
    assert json.dumps(context, ensure_ascii=False, separators=(",", ":")) in completions.calls[0]["messages"][1]["content"]


def test_v4_needs_clarification_loads_skill_for_followup_call():
    payload = _v4_payload(CLARIFY_JSON)
    payload["ambiguous_fields"] = ["pose"]
    completions = _FakeCompletions(responses=[
        _FakeResponse(json.dumps(payload)),
        _FakeResponse("어떤 동작이나 체중 지지 자세를 원하시나요?"),
    ])
    adapter = _adapter(completions, settings=_real_settings().model_copy(update={
        "interpreter_prompt_version": "uhkegryo-interpreter-v4",
    }))

    context = {"pending_question": "어떤 자세인가요?"}
    output = asyncio.run(adapter.interpret(
        "당당한 자세", job_id="j", session_id="s", attempt=1, max_attempts=3, session_context=context
    ))

    assert output.clarifying_question == "어떤 동작이나 체중 지지 자세를 원하시나요?"
    assert len(completions.calls) == 2
    first_system = completions.calls[0]["messages"][0]["content"]
    second = completions.calls[1]["messages"]
    assert "캐주얼 캐릭터 일러스트 레퍼런스 해석 Skill" in first_system
    assert "For abstract_intent" not in first_system
    assert "For abstract_intent" in second[0]["content"]
    assert "For insufficient_visual_evidence" in second[0]["content"]
    followup_input = json.loads(second[1]["content"])
    assert followup_input["request_text"] == "당당한 자세"
    assert followup_input["validated_interpretation"]["clarification_type"] == "insufficient_visual_evidence"
    assert followup_input["validated_interpretation"]["ambiguous_fields"] == ["pose"]
    assert followup_input["validated_interpretation"]["interpretation_state"] == "needs_clarification"
    assert followup_input["session_context"] == context


def test_v4_missing_clarification_skill_fails_only_after_clarify():
    payload = _v4_payload(CLARIFY_JSON)
    payload["ambiguous_fields"] = ["pose"]
    settings = _real_settings().model_copy(update={
        "interpreter_prompt_version": "uhkegryo-interpreter-v4",
        "clarification_skill_path": "missing-clarification-skill.md",
    })
    completions = _FakeCompletions(responses=[_FakeResponse(json.dumps(payload))])
    adapter = _adapter(completions, settings=settings)
    with pytest.raises(llm.PromptConfigurationError):
        asyncio.run(adapter.interpret("당당한 자세", job_id="j", session_id="s", attempt=1, max_attempts=3))
    assert len(completions.calls) == 1


@pytest.mark.parametrize("version", ["uhkegryo-interpreter-v1", "uhkegryo-interpreter-v4"])
def test_duplicate_role_feedback_is_used_on_next_single_call(version):
    payload = json.loads(SELECT_JSON)
    valid_output = json.loads(SELECT_JSON)
    if version == "uhkegryo-interpreter-v4":
        payload = _v4_payload(payload)
        valid_output = _v4_payload(valid_output)
    payload["selections"].append(payload["selections"][0].copy())
    responses = [_FakeResponse(json.dumps(payload)), _FakeResponse(json.dumps(valid_output))]
    if version == "uhkegryo-interpreter-v4":
        responses.append(_FakeResponse("최종 답변 문장입니다."))
    completions = _FakeCompletions(responses=responses)
    adapter = _adapter(completions, settings=_real_settings().model_copy(update={
        "interpreter_prompt_version": version,
    }))
    kwargs = dict(job_id="job-1", session_id="session-1", max_attempts=3)
    with pytest.raises(llm.LLMInvalidStructuredOutput) as raised:
        asyncio.run(adapter.interpret("반동", attempt=1, **kwargs))
    assert raised.value.feedback == [{"path": [], "code": "role_duplicate"}]
    output = asyncio.run(adapter.interpret("반동", attempt=2, validation_feedback=raised.value.feedback, **kwargs))
    assert len(output.selections) == 1 and len(completions.calls) == (3 if version == "uhkegryo-interpreter-v4" else 2)
    sent = completions.calls[1]["messages"]
    assert sum(item["role"] == "system" for item in sent) == 1
    repair = json.loads(sent[-1]["content"])
    assert repair["validation_feedback"] == raised.value.feedback
    if version == "uhkegryo-interpreter-v4":
        assert "pose_sitting" in repair["repair_rules"] and "pose_gesture" in repair["repair_rules"]
    else:
        assert repair == {"validation_feedback": raised.value.feedback}


def test_feedback_never_contains_unknown_field_names_or_input_values():
    payload = json.loads(SELECT_JSON)
    payload["secret-field-marker"] = "secret-value-marker"
    with pytest.raises(llm.LLMInvalidStructuredOutput) as raised:
        llm._validate_output(json.dumps(payload))
    assert raised.value.feedback == [{"path": ["unknown_field"], "code": "extra_forbidden"}]
    assert "secret" not in json.dumps(raised.value.feedback)


def test_missing_skill_fails_before_call():
    settings = _real_settings().model_copy(update={"structured_output_skill_path": "missing-skill.md",
                                                 "interpreter_prompt_version": "uhkegryo-interpreter-v1"})
    with pytest.raises(llm.PromptConfigurationError):
        llm.LLMInterpretationAdapter(settings=settings, client=object(),
                                    prompt_path=PROMPT)


def test_v1_call_combines_interpreter_and_output_instructions():
    settings = _real_settings().model_copy(update={
        "interpreter_prompt_path": str(PROMPT),
        "interpreter_prompt_version": "uhkegryo-interpreter-v1",
    })
    completions = _FakeCompletions(responses=[_FakeResponse(SELECT_JSON)])
    adapter = llm.LLMInterpretationAdapter(settings=settings, client=_FakeClient(completions))
    asyncio.run(adapter.interpret("반동", job_id="j", session_id="s", attempt=1, max_attempts=3))
    call = completions.calls[0]
    messages = call["messages"]
    system = messages[0]["content"]
    assert sum(item["role"] == "system" for item in messages) == 1
    assert system.startswith(llm.load_interpreter_prompt(PROMPT)[0])
    assert "role_duplicate" in system
    assert call["response_format"] == response_format()
    assert call["extra_body"] == {"provider": {"require_parameters": True}}
    assert adapter.prompt_version == "uhkegryo-interpreter-v1"
    for rule in ("Return exactly one JSON object", "Include every field", "always arrays",
                 "For select_terms:", "For needs_clarification:", "Selection shape example:",
                 "Clarification shape example:"):
        assert system.count(rule) == 1


def test_v0_keeps_json_mode_without_skill_or_feedback():
    prompt = ROOT / "prompts/uhkegryo-interpreter-v0.md"
    settings = _real_settings().model_copy(update={"structured_output_skill_path": "missing.md"})
    completions = _FakeCompletions(responses=[_FakeResponse(SELECT_JSON)])
    adapter = llm.LLMInterpretationAdapter(settings=settings, prompt_path=prompt, client=_FakeClient(completions))
    asyncio.run(adapter.interpret("반동", job_id="j", session_id="s", attempt=1, max_attempts=3,
                                  validation_feedback=[{"path": [], "code": "role_duplicate"}]))
    call = completions.calls[0]
    assert adapter.prompt_version == "uhkegryo-interpreter-v0"
    assert call["messages"][0]["content"].startswith(llm.load_interpreter_prompt(prompt)[0] + "\n")
    assert "Include answer_text" in call["messages"][0]["content"]
    assert len(call["messages"]) == 2 and len(completions.calls) == 1
    assert call["response_format"] == {"type": "json_object"} and "extra_body" not in call


@pytest.mark.parametrize("content", ["raw-secret", json.dumps({
    **json.loads(SELECT_JSON), **{f"raw-secret-{i}": "raw-secret" for i in range(12)},
})])
@pytest.mark.parametrize("version", ["uhkegryo-interpreter-v0", "uhkegryo-interpreter-v1"])
def test_validation_failure_generation_is_bounded_and_has_no_raw_data(monkeypatch, caplog, content, version):
    recorded, _ = _langfuse_generation_kwargs(monkeypatch)
    settings = _real_settings().model_copy(update={"langfuse_public_key": "pk-test",
        "langfuse_secret_key": "sk-test", "interpreter_prompt_version": version})
    adapter = _adapter(_FakeCompletions(responses=[_FakeResponse(content)]), settings=settings)
    with caplog.at_level("DEBUG"), pytest.raises(llm.LLMInvalidStructuredOutput) as raised:
        asyncio.run(adapter.interpret("request-secret", job_id="j", session_id="s", attempt=2, max_attempts=3))
    generation, update = recorded["generation"], recorded["generation_update"]
    assert recorded["parent_trace_id"] == "worker-owned-trace"
    assert generation["input"] is None and update["output"] is None
    assert update["level"] == "ERROR" and update["usage_details"]["total_tokens"] == 15
    assert generation["metadata"] == {"job_id": "j", "session_id": "s", "attempt": 2, "max_attempts": 3,
        "finish_reason": "stop", "error_type": "pydantic_validation_error",
        "validation_feedback": raised.value.feedback}
    assert len(raised.value.feedback) == (8 if content.startswith("{") else 1)
    serialized = json.dumps(recorded) + caplog.text
    assert "request-secret" not in serialized and "raw-secret" not in serialized


@pytest.mark.parametrize("mode", ["no_worker_trace", "sdk_failure"])
def test_failed_generation_observation_does_not_change_validation_failure(monkeypatch, caplog, mode):
    recorded, _ = _langfuse_generation_kwargs(monkeypatch)
    fake = sys.modules["langfuse"].Langfuse
    if mode == "no_worker_trace":
        monkeypatch.setattr(fake, "get_current_trace_id", lambda self: None)
    else:
        def fail(self, **kwargs):
            raise RuntimeError("sdk-secret-exception")
        monkeypatch.setattr(fake, "start_as_current_observation", fail)
    recorded.clear()
    settings = _real_settings().model_copy(update={"langfuse_public_key": "pk-test", "langfuse_secret_key": "sk-test"})
    adapter = _adapter(_FakeCompletions(responses=[_FakeResponse("raw-secret")]), settings=settings)
    with caplog.at_level("DEBUG"), pytest.raises(llm.LLMInvalidStructuredOutput) as raised:
        asyncio.run(adapter.interpret("request-secret", job_id="j", session_id="s", attempt=1, max_attempts=3))
    assert raised.value.feedback == [{"path": [], "code": "json_invalid"}]
    assert "generation" not in recorded
    assert all(secret not in caplog.text for secret in ("sdk-secret-exception", "request-secret", "raw-secret"))
