"""실제 loader가 전달하는 v1 출력 계약의 회귀 검증."""
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from backend.schemas.memory import ContextUpdate
from backend.schemas.models import InterpretationOutput, InterpretationSelection
from backend.services.llm import (
    LLMInterpretationAdapter,
    LLMInvalidStructuredOutput,
    _validate_output,
    load_interpreter_prompt,
)
from backend.shared.config import Settings
from backend.services import conversation_context

ROOT = Path(__file__).resolve().parents[2]
PROMPT = ROOT / "prompts" / "uhkegryo-interpreter-v1.md"


def test_loaded_system_contains_complete_selection_shape_and_valid_examples():
    system, user = load_interpreter_prompt(PROMPT)
    examples = [json.loads(line) for line in system.splitlines() if line.startswith('{"interpretation_state"')]
    assert len(examples) == 2
    selected, clarification = [InterpretationOutput.model_validate(item) for item in examples]
    top_fields = set(InterpretationOutput.model_fields)
    selection_fields = set(InterpretationSelection.model_fields)
    assert len(top_fields) == 6
    assert "all six top-level fields" in system
    assert all(set(example) == top_fields for example in examples)
    assert set(examples[0]["selections"][0]) == selection_fields
    assert selected.selections[0].evidence
    assert clarification.selections == []
    assert clarification.clarification_type is not None
    assert "Never return null, a string, or a single object for selections" in system
    assert "{{request_text}}" in user and "{{active_cards_json}}" in user


def test_documented_table_and_pretty_examples_match_pydantic_contract():
    from backend.services.llm import _extract_fenced_block

    prompt = PROMPT.read_text(encoding="utf-8")
    table = prompt.split("## 출력 JSON 계약", 1)[1].split("정상 선택 형태:", 1)[0]
    assert all(f"| `{name}` |" in table for name in InterpretationOutput.model_fields)
    assert all(f"| `selections[].{name}` |" in table for name in InterpretationSelection.model_fields)
    assert all(f"| `context_updates[].{name}` |" in table for name in ContextUpdate.model_fields)
    for heading in ("정상 선택 형태:", "질문 형태:"):
        example = json.loads(_extract_fenced_block(prompt, heading))
        assert set(example) == set(InterpretationOutput.model_fields)
        InterpretationOutput.model_validate(example)
    selected = json.loads(_extract_fenced_block(prompt, "정상 선택 형태:"))
    assert set(selected["selections"][0]) == set(InterpretationSelection.model_fields)


@pytest.mark.parametrize("source_job_id", [None, "00000000-0000-0000-0000-000000000001"])
def test_english_original_evidence_preserves_spelling(source_job_id):
    system, _ = load_interpreter_prompt(PROMPT)
    assert "preserve the original spelling and case, including English" in system
    example = next(json.loads(line) for line in system.splitlines()
                   if line.startswith('{"interpretation_state":"select_terms"'))
    example["selections"][0]["evidence"] = ["Low Angle 3/4"]
    example["selections"][0]["source_job_id"] = source_job_id
    result = _validate_output(json.dumps(example, ensure_ascii=False))
    assert result.selections[0].evidence == ["Low Angle 3/4"]


def test_loaded_system_separates_selection_and_context_update_sources():
    system, _ = load_interpreter_prompt(PROMPT)
    assert "selections[].evidence must preserve the original spelling and case, including English" in system
    assert "identified by a valid source_job_id" in system
    assert "context_updates[].evidence must preserve the original spelling and case, including English, from the current request only" in system
    assert "context_updates has no source_job_id field" in system
    assert "evidence and context_updates evidence" not in system


@pytest.mark.parametrize("update_evidence", ["High Angle", "Low Angle", "low angle"])
def test_context_update_uses_current_english_request_only(snapshot_factory, card_factory, update_evidence):
    source_id = "00000000-0000-0000-0000-000000000001"
    job = {"request_text": "Change the view to High Angle"}
    memory = AsyncMock()
    memory.records.return_value = [{
        "job_id": source_id, "request_text": "High Angle or Low Angle",
        "terms": [{"label_ko": "로우 앵글", "label_en": "low angle"}],
    }]
    snapshot = snapshot_factory([
        card_factory("view_low_angle", role="view"),
        card_factory("view_high_angle", role="view"),
    ])
    output = InterpretationOutput(
        interpretation_state="select_terms",
        selections=[InterpretationSelection(role="view", term_id="view_high_angle",
            evidence=["High Angle"], confidence=0.9, source_job_id=source_id)],
        context_updates=[ContextUpdate(role="view", term_id="view_high_angle", evidence=update_evidence)],
    )
    if update_evidence == "High Angle":
        asyncio.run(conversation_context.validate(memory, job, output, snapshot))
        assert output.context_updates[0].evidence == "High Angle"
    else:
        with pytest.raises(LLMInvalidStructuredOutput, match="조건 변경에 현재 요청의 명시적 근거가 필요합니다") as raised:
            asyncio.run(conversation_context.validate(memory, job, output, snapshot))
        assert raised.value.failure_code.value == "LLM_INVALID_STRUCTURED_OUTPUT"
    memory.records.assert_awaited_once_with(job, [output.selections[0].source_job_id])


@pytest.mark.parametrize("selections", [None, {}, "pose"])
def test_invalid_selection_type_is_still_rejected(selections):
    with pytest.raises(LLMInvalidStructuredOutput):
        _validate_output(json.dumps({"interpretation_state": "select_terms", "selections": selections}))


def test_v1_path_and_trace_version_can_be_activated_together():
    settings = Settings(_env_file=None, database_url="sqlite:///test.db",
                        interpreter_prompt_path=str(PROMPT), interpreter_prompt_version="uhkegryo-interpreter-v1")
    adapter = LLMInterpretationAdapter(client=object(), settings=settings)
    assert adapter.prompt_version == "uhkegryo-interpreter-v1"
    assert '"selections":[{' in adapter._system_message
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY prompts/uhkegryo-interpreter-v1.md /app/prompts/uhkegryo-interpreter-v1.md" in dockerfile


def test_v1_preserves_main_memory_instructions():
    from backend.services.llm import _extract_fenced_block
    baseline = (ROOT / "prompts/uhkegryo-interpreter-v0.md").read_text(encoding="utf-8")
    current = PROMPT.read_text(encoding="utf-8")
    for operation in ("classify", "summarize", "answer"):
        heading = "## Memory " + operation
        assert _extract_fenced_block(current, heading) == _extract_fenced_block(baseline, heading)
