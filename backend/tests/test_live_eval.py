"""Ensure the evaluation never credits an incorrect terminal result."""
from copy import deepcopy
import json
from pathlib import Path

from scripts.run_live_eval import MeasuredAdapter, assess
from backend.services.llm import LLMInvalidStructuredOutput


def test_required_selection_and_reason_mismatches_are_failures():
    case = json.loads((Path(__file__).parents[2] / "evals/dataset.jsonl").read_text(encoding="utf-8").splitlines()[0])
    submitted = {"job_status": "queued", "poll_after_ms": 1000}
    terminal = {"job_status": "completed", "result": {
        "agent_status": "success", "reason_codes": [], "reference_plan": {
            "terms": [{**term, "pins": []} for term in case["expected"]["required_selections"]]}}}
    assert all(assess(case, submitted, terminal, []).values())
    missing = deepcopy(terminal)
    missing["result"]["reference_plan"]["terms"].pop()
    assert not assess(case, submitted, missing, [])["required_selections"]
    wrong = deepcopy(terminal)
    wrong["result"]["reason_codes"] = ["PIN_RESULTS_EMPTY"]
    assert not assess(case, submitted, wrong, [])["reason_codes"]


def test_interrupted_case_requires_real_failure_and_third_attempt():
    case = json.loads((Path(__file__).parents[2] / "evals/dataset.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    submitted = {"job_status": "queued", "poll_after_ms": 1000}
    terminal = {"job_status": "failed", "attempt": 3,
                "failure": {"failure_code": "JOB_INSTANCE_INTERRUPTED"}}
    assert all(assess(case, submitted, terminal, []).values())
    terminal["attempt"] = 1
    assert not assess(case, submitted, terminal, [])["attempt"]


def test_validation_diagnostics_are_bounded_and_do_not_store_error_text():
    adapter = object.__new__(MeasuredAdapter)
    adapter.reset({"runtime_fixture": {}})
    adapter.record_validation_failure(LLMInvalidStructuredOutput("선택 근거에 비밀 원문"), attempt=2)
    assert adapter.validation_failures == [{"attempt": 2, "code": "selection_evidence"}]


def test_retry_fixture_fails_every_correction_in_first_attempt():
    import asyncio

    adapter = object.__new__(MeasuredAdapter)
    adapter.reset({"runtime_fixture": {"llm_sequence": ["invalid_structured_output", "valid"]}})

    async def run():
        for _ in range(3):
            try:
                await adapter.interpret("request", attempt=1)
            except LLMInvalidStructuredOutput:
                pass
            else:
                raise AssertionError("first attempt must fail")

    asyncio.run(run())
