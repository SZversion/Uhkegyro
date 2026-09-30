"""실제 loader가 전달하는 v1 출력 계약의 회귀 검증."""
import json
from pathlib import Path

import pytest

from backend.schemas.models import InterpretationOutput
from backend.services.llm import (
    LLMInterpretationAdapter,
    LLMInvalidStructuredOutput,
    _validate_output,
    load_interpreter_prompt,
)
from backend.shared.config import Settings

ROOT = Path(__file__).resolve().parents[2]
PROMPT = ROOT / "prompts" / "uhkegryo-interpreter-v1.md"


def test_loaded_system_contains_complete_selection_shape_and_valid_examples():
    system, user = load_interpreter_prompt(PROMPT)
    examples = [json.loads(line) for line in system.splitlines() if line.startswith('{"interpretation_state"')]
    assert len(examples) == 2
    selected, clarification = [InterpretationOutput.model_validate(item) for item in examples]
    assert set(examples[0]["selections"][0]) == {"role", "term_id", "evidence", "confidence", "source_job_id"}
    assert "source_job_id" in system and "context_updates" in system
    assert selected.selections[0].evidence
    assert clarification.selections == []
    assert clarification.clarification_type is not None
    assert "Never return null, a string, or a single object for selections" in system
    assert "{{request_text}}" in user and "{{active_cards_json}}" in user


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
