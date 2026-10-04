import asyncio
import json
import pytest

from backend.services.job_retry_recovery import JobRetryRecovery
from backend.services.llm import LLMInvalidStructuredOutput, LLMTimeout


class Connection:
    async def fetchrow(self, sql, *args):
        self.sql, self.args = sql, args
        return {"job_id": "test"}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class Pool:
    def __init__(self):
        self.connection = Connection()

    def acquire(self):
        return self.connection


def persisted(error, attempt=3):
    pool = Pool()
    asyncio.run(JobRetryRecovery(pool).handle_attempt_failure(
        job_id="test", attempt=attempt, max_attempts=3, error=error))
    return pool.connection


def test_final_validation_failure_retains_diagnostics():
    connection = persisted(LLMInvalidStructuredOutput("private output", feedback=[
        {"path": ["selections", 0, "evidence"], "code": "missing"}]))
    assert "validation_feedback_json = $6::jsonb" in connection.sql
    assert json.loads(connection.args[5]) == [{
        "stage": "interpretation_schema", "path": ["selections", 0, "evidence"], "code": "missing"}]
    assert "private output" not in repr(connection.args)


def test_final_nonvalidation_failure_clears_diagnostics():
    connection = persisted(LLMTimeout("private timeout"))
    assert "validation_feedback_json = $6::jsonb" in connection.sql
    assert connection.args[5] is None


def test_final_diagnostics_reject_arbitrary_values():
    connection = persisted(LLMInvalidStructuredOutput("secret", feedback=[
        {"path": ["secret", 0], "code": "secret", "input": "secret"}]))
    assert "secret" not in connection.args[5]
    assert json.loads(connection.args[5])[0]["code"] == "invalid_candidate"


def test_retry_feedback_remains_unchanged():
    feedback = [{"path": [], "code": "role_duplicate"}]
    connection = persisted(LLMInvalidStructuredOutput("private", feedback=feedback), attempt=1)
    assert json.loads(connection.args[5]) == feedback


def test_evidence_mismatch_has_specific_diagnostic_stage():
    from backend.schemas.models import InterpretationOutput
    from backend.services.conversation_context import validate

    interpretation = InterpretationOutput(interpretation_state="select_terms", selections=[{
        "role": "body", "term_id": "body_slim", "evidence": ["원문에 없는 표현"], "confidence": 1}])
    with pytest.raises(LLMInvalidStructuredOutput) as raised:
        asyncio.run(validate(None, {"request_text": "마른 캐릭터"}, interpretation, None))
    connection = persisted(raised.value)
    assert json.loads(connection.args[5]) == [{
        "stage": "conversation_validation", "path": [], "code": "selection_evidence_invalid"}]


@pytest.mark.parametrize("stage", ["interpretation_schema", "memory_schema", "conversation_validation"])
def test_preserves_known_stages(stage):
    connection = persisted(LLMInvalidStructuredOutput("private", stage=stage))
    assert json.loads(connection.args[5])[0]["stage"] == stage
