"""Ensure the evaluation never credits an incorrect terminal result."""
import asyncio
import json
import os
from pathlib import Path
import uuid
from types import SimpleNamespace

import asyncpg
import pytest

from scripts.run_live_eval import MeasuredAdapter, ROOT, _safe_validation_path, execute
from backend.services.llm import LLMInvalidStructuredOutput, _validate_output
from backend.services.catalog_repository import load_catalog
from backend.services import conversation_context


def test_validation_diagnostics_are_bounded_and_do_not_store_error_text():
    adapter = object.__new__(MeasuredAdapter)
    adapter.reset({"runtime_fixture": {}})
    marker, value = "PRIVATE_MARKER_8472", "SENSITIVE_INPUT_3190"
    payload = {"interpretation_state": "needs_clarification", "clarification_type": "abstract_intent",
               "selections": [], "unresolved_constraints": ["불명확"], "clarifying_question": "어떤 포즈인가요?",
               "context_updates": [], marker: value}
    with pytest.raises(LLMInvalidStructuredOutput) as raised:
        _validate_output(json.dumps(payload, ensure_ascii=False))
    adapter.record_validation_failure(raised.value, attempt=2)
    adapter.record_validation_failure(LLMInvalidStructuredOutput(f"{marker} 선택 근거 {value}"), attempt=3)
    serialized = json.dumps(adapter.validation_failures, ensure_ascii=False)
    assert all(text not in serialized for text in (marker, value, str(raised.value), str(raised.value.__cause__)))
    assert adapter.validation_failures[0]["code"] == "output_schema"
    assert adapter.validation_failures[0]["detail"]["field"] == "unknown_field"
    assert len(adapter.validation_failures[0]["detail"]["field"]) <= 96
    assert len(_safe_validation_path(["selections"] * 12)) <= 96
    assert len(adapter.validation_failures[0]["detail"]["type"]) <= 64
    assert adapter.validation_failures[1] == {"attempt": 3, "code": "selection_evidence"}


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is not configured")
def test_execute_completes_postgres_worker_and_measured_request_path(monkeypatch):
    async def run():
        case = json.loads(next(line for line in (ROOT / "evals/dataset.jsonl").read_text(encoding="utf-8").splitlines() if '"id":"EVAL-01"' in line))
        snapshot = load_catalog(ROOT / "docs/domains/illustration-reference/term-cards")
        schema, url = "live_eval_test_" + uuid.uuid4().hex, os.environ["TEST_DATABASE_URL"]
        admin = await asyncpg.connect(url)
        pool = None
        try:
            await admin.execute(f'CREATE SCHEMA "{schema}"')
            pool = await asyncpg.create_pool(url, setup=lambda conn: conn.execute(f'SET search_path TO "{schema}"'), server_settings={"search_path": schema})
            for migration in sorted((ROOT / "backend/db/migrations").glob("*.sql")):
                await pool.execute(migration.read_text(encoding="utf-8"))
            class Completions:
                async def create(self, **kwargs):
                    self.response_format = kwargs["response_format"]
                    content = '{"interpretation_state":"select_terms","selections":[{"role":"body","term_id":"body_slim","evidence":["마른 체형"],"confidence":0.9},{"role":"pose","term_id":"pose_standing","evidence":["두 발로 똑바로 서서"],"confidence":0.9},{"role":"view","term_id":"view_front","evidence":["정면"],"confidence":0.9}],"unresolved_constraints":[],"clarifying_question":null,"clarification_type":null,"context_updates":[]}'
                    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))], usage=None)
            completions = Completions()
            adapter = object.__new__(MeasuredAdapter)
            adapter.settings = SimpleNamespace(interpreter_prompt_version="v0", llm_model="test", llm_max_tokens=128,
                                                langfuse_public_key="", langfuse_secret_key="")
            adapter._system_message, adapter._user_template, adapter._structured_output = "system", "{{request_text}}", False
            adapter._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
            async def no_recall(*args): return None, False
            monkeypatch.setattr(conversation_context, "recall", no_recall)
            result = await execute(case, pool, snapshot, adapter)
            assert result["passed"] and result["calls"] and completions.response_format == {"type": "json_object"}
        finally:
            if pool: await pool.close()
            await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'); await admin.close()
    asyncio.run(run())
