"""Acceptance checks for selective-reference-update.md and reference-refresh.md."""
import asyncio
import json
from uuid import uuid4

import pytest

from backend.schemas.enums import Role, ReasonCode, JobStatus
from backend.schemas.memory import RecallQuery, ContextUpdate
from backend.schemas.models import AgentResult, InterpretationOutput, PinResult, ReferencePlan, TermResult
from backend.services.reference_update import previous_terms, refresh_resolution
from backend.services.searxng_pinterest_search import SearXNGPinterestSearchProvider
from backend.tests.test_agent_worker import FakeAdapter, FakeJobs, FakeRecovery, FakeMcpGateway, _worker, JOB


def pin(value):
    return PinResult(pin_id=value, pin_url=f"https://www.pinterest.com/pin/{value}/", status="available")


def prior():
    return AgentResult(agent_status="success", reference_plan=ReferencePlan(terms=[
        TermResult(role=role, term_id=term_id, label_ko=term_id, label_en=term_id,
            plain_meaning_ko="설명", search_url="https://www.pinterest.com/search/pins/",
            pins=[pin(value)])
        for role, term_id, value in [("body", "body_slim", "11"), ("pose", "pose_standing", "22")]
    ])).model_dump(mode="json")


def run_worker(monkeypatch, snapshot_factory, card_factory, *, refresh=False, previous=None,
               inherited=False, failure=False, clear=False, old_pins=False, changed_role="pose"):
    previous = prior() if previous is None else previous
    selected_id = {"body": "body_muscular", "pose": "pose_sitting", "view": "view_profile"}[changed_role]
    search_terms = [(t["role"], t["term_id"]) for t in (previous.get("reference_plan") or {}).get("terms", [])]
    if not refresh:
        search_terms = [(changed_role, selected_id)]
    output = InterpretationOutput(interpretation_state="select_terms", selections=[
        {"role": changed_role, "term_id": selected_id, "evidence": ["옆모습" if changed_role == "view" else "앉은 모습"], "confidence": 1}],
        answer_text="앉은 포즈로 바꿨어요.")
    if inherited:
        output.selections.insert(0, output.selections[0].model_copy(update={
            "role": Role.BODY, "term_id": "body_slim", "evidence": ["body_slim"], "source_job_id": uuid4()}))
    if clear:
        output.context_updates = [ContextUpdate(role="body", term_id=None, evidence="체형 제외")]
    adapter = FakeAdapter(output, tool_calls=[[
        {"id": role, "name": "search_pinterest_pins", "arguments": {
            "role": role, "query_fragments": [term_id], "exclude_pin_ids": ["999"]}}
        for role, term_id in search_terms
    ], []])
    if failure:
        adapter.tool_calls = [adapter.tool_calls[0]] * 3 + [[]]
        monkeypatch.setattr("backend.services.agent_worker.SEARCH_RETRY_DELAYS_SECONDS", (0, 0))
    async def classify(*args, **kwargs):
        return RecallQuery(mode="none", reference_action="refresh_all" if refresh else "update")
    adapter.memory = classify
    snapshot = snapshot_factory([card_factory(term_id, role=role, query_fragments=[term_id])
        for role, term_id in [('body', 'body_slim'), ('body', 'body_muscular'), ('pose', 'pose_standing'), ('pose', 'pose_sitting'),
                             ('view', 'view_front'), ('view', 'view_profile')]])
    jobs, recovery = FakeJobs({**JOB, "request_text": "체형 제외 앉은 모습 옆모습"}), FakeRecovery()
    roles = [role for role, _ in search_terms]
    gateway = FakeMcpGateway([{"role": role, "code": "PIN_SEARCH_UNAVAILABLE" if failure else None,
        "pins": [] if failure else [pin(("22" if role == "body" else "11") if old_pins
            else ("33" if role == "body" else "44")).model_dump(mode="json")]}
        for role in roles] * (3 if failure else 1))
    worker = _worker(monkeypatch, jobs, recovery, snapshot, adapter, mcp_gateway=gateway)
    async def load(job):
        return {"state": {}, "recent": [], "sources": [], "oldest_recent": None,
                "previous_result": previous}
    async def records(job, ids):
        return [{"job_id": str(ids[0]), "request_text": "body_slim", "terms": []}]
    worker._memory.load, worker._memory.records = load, records
    asyncio.run(worker.run_once())
    assert not recovery.failures
    assert jobs.writes[-1][0] is JobStatus.COMPLETED
    return jobs.writes[-1][1], gateway.calls, adapter


@pytest.mark.parametrize("inherited", [False, True])
def test_pose_only_search_preserves_body(monkeypatch, snapshot_factory, card_factory, inherited):
    result, calls, _ = run_worker(monkeypatch, snapshot_factory, card_factory, inherited=inherited)
    assert [args["role"] for _, args in calls] == ["pose"]
    assert [t.term_id for t in result.reference_plan.terms] == ["body_slim", "pose_sitting"]
    assert result.reference_plan.terms[0].pins[0].pin_id == "11"


@pytest.mark.parametrize("changed_role,refresh", [("body", False), ("pose", False), ("view", False), ("pose", True)])
def test_body_pose_view_board_updates_only_requested_roles(monkeypatch, snapshot_factory, card_factory, changed_role, refresh):
    previous = prior()
    previous["reference_plan"]["terms"].append({**previous["reference_plan"]["terms"][0],
        "role": "view", "term_id": "view_front", "pins": [pin("55").model_dump(mode="json")]})
    result, calls, _ = run_worker(monkeypatch, snapshot_factory, card_factory,
        previous=previous, refresh=refresh, changed_role=changed_role)
    assert [args["role"] for _, args in calls] == (["body", "pose", "view"] if refresh else [changed_role])
    for term, original in zip(result.reference_plan.terms, previous["reference_plan"]["terms"]):
        if refresh:
            assert term.term_id == original["term_id"]
            assert all(p.pin_id not in {"11", "22", "55"} for p in term.pins)
        elif term.role.value != changed_role:
            assert term.model_dump(mode="json") == original


def test_clear_and_search_failure_do_not_replace_other_roles(monkeypatch, snapshot_factory, card_factory):
    failed, _, _ = run_worker(monkeypatch, snapshot_factory, card_factory, failure=True)
    assert failed.agent_status.value == "partial_result"
    assert failed.reference_plan.terms[0].pins[0].pin_id == "11"
    cleared, _, _ = run_worker(monkeypatch, snapshot_factory, card_factory, clear=True)
    assert [t.role for t in cleared.reference_plan.terms] == [Role.POSE]


def test_refresh_preserves_cards_overrides_model_exclusions_and_repeats(monkeypatch, snapshot_factory, card_factory):
    result, calls, adapter = run_worker(monkeypatch, snapshot_factory, card_factory, refresh=True)
    assert [t.term_id for t in result.reference_plan.terms] == ["body_slim", "pose_standing"]
    assert [args["exclude_pin_ids"] for _, args in calls] == [["11", "22"], ["11", "22"]]
    assert not adapter.calls  # No card reinterpretation.
    _, calls, _ = run_worker(monkeypatch, snapshot_factory, card_factory, refresh=True,
        previous=result.model_dump(mode="json"))
    assert [args["exclude_pin_ids"] for _, args in calls] == [["33", "44"], ["33", "44"]]


def test_refresh_without_previous_board_asks_without_search(monkeypatch, snapshot_factory, card_factory):
    result, calls, _ = run_worker(monkeypatch, snapshot_factory, card_factory, refresh=True, previous={})
    assert result.agent_status.value == "needs_clarification" and calls == []


def test_worker_rejects_old_pins_even_when_returned_under_another_role(monkeypatch, snapshot_factory, card_factory):
    result, _, _ = run_worker(monkeypatch, snapshot_factory, card_factory, refresh=True, old_pins=True)
    assert result.reason_codes == [ReasonCode.PIN_RESULTS_EMPTY]
    assert all(not term.pins for term in result.reference_plan.terms)
    assert "찾지 못" in result.answer_text


def test_adapter_preserves_refresh_action_when_normalizing_unused_filters(monkeypatch):
    from backend.tests.test_llm_adapter import _adapter, _FakeCompletions, _FakeResponse
    transport = _FakeCompletions([_FakeResponse('{"mode":"none","reference_action":"refresh_all"}')])
    adapter = _adapter(transport)
    from pathlib import Path
    monkeypatch.setattr(adapter, "_resolve_prompt_path", lambda: Path(__file__).parents[2] / "prompts/uhkegryo-interpreter-v4.md")
    result = asyncio.run(adapter.memory("classify", {"request_text": "전부 새 레퍼런스"}, RecallQuery,
        job_id=str(uuid4()), session_id=str(uuid4()), attempt=1, max_attempts=3))
    assert result.reference_action == "refresh_all"
    assert "Role changes" in transport.calls[0]["messages"][0]["content"]


def test_inactive_previous_card_blocks_whole_refresh(snapshot_factory):
    context, snapshot = {"previous_result": prior()}, snapshot_factory([])
    resolution = refresh_resolution(previous_terms(context, snapshot), snapshot, context)
    assert resolution.status == "clarify"


def test_new_reference_request_keeps_action_classification():
    from backend.services.conversation_context import is_clear_new_request
    assert not is_clear_new_request("전부 새로운 레퍼런스를 찾아줘", {"state": {}, "previous_result": prior()})


@pytest.mark.parametrize("new_pin", [True, False])
def test_provider_excludes_before_limit(new_pin):
    calls = []
    async def loader(url, params):
        calls.append(params["q"])
        ids = [str(i) for i in range(1, 9)] + (["99"] if new_pin else [])
        return {"results": [{"url": f"https://www.pinterest.com/pin/{i}/"} for i in ids]}
    provider = SearXNGPinterestSearchProvider(base_url="http://fake", json_loader=loader,
        exclude_pin_ids=tuple(str(i) for i in range(1, 9)))
    result = asyncio.run(provider.search(Role.POSE, ("pose",)))
    assert [p.pin_id for p in result.pins] == (["99"] if new_pin else [])
    assert len(calls) == 1
    assert result.code == (None if new_pin else ReasonCode.PIN_RESULTS_EMPTY)


def test_postgres_reuses_only_same_conversation_preceding_board(snapshot_factory, card_factory):
    from backend.tests.test_conversation_sessions import database_case
    from backend.services.session_repository import SessionRepository
    from backend.services.job_repository import JobRepository
    from backend.services.conversation_memory import ConversationMemory
    from backend.services.agent_worker import AgentJobWorker
    from backend.services.job_trace import JobTracer
    async def scenario(pool):
        sessions, jobs = SessionRepository(pool), JobRepository(pool)
        a, b = await sessions.create_session("a"), await sessions.create_session("b")
        async def seed(session, value, future=False):
            job, _ = await jobs.submit(session_id=session, request_text="seed", idempotency_key=str(uuid4()))
            payload = prior()
            payload["reference_plan"]["terms"][0]["pins"] = [pin(value).model_dump(mode="json")]
            await pool.execute("""UPDATE jobs SET status='completed', succeeded=true,
                final_payload_json=$2::jsonb, created_at=now()+$3::int*interval '1 day'
                WHERE job_id=$1::uuid""", job.job_id, json.dumps(payload), int(future))
        await seed(a, "11")
        await seed(b, "88")
        submitted, _ = await jobs.submit(session_id=a, request_text="앉은 모습", idempotency_key=str(uuid4()))
        await seed(a, "99", future=True)
        claimed = await jobs.claim_next()
        assert str(claimed["job_id"]) == submitted.job_id
        context = await ConversationMemory(pool).load(claimed)
        assert context["previous_result"]["reference_plan"]["terms"][0]["pins"][0]["pin_id"] == "11"
        snapshot = snapshot_factory([card_factory(term_id, role=role, query_fragments=[term_id])
            for role, term_id in [('body', 'body_slim'), ('pose', 'pose_standing'), ('pose', 'pose_sitting')]])
        adapter = FakeAdapter(InterpretationOutput(interpretation_state="select_terms", selections=[
            {"role": "pose", "term_id": "pose_sitting", "evidence": ["앉은 모습"], "confidence": 1}]),
            tool_calls=[[{"id": "pose", "name": "search_pinterest_pins", "arguments": {
                "role": "pose", "query_fragments": ["pose_sitting"]}}], []])
        gateway = FakeMcpGateway([{"role": "pose", "pins": [pin("44").model_dump(mode="json")], "code": None}])
        worker = AgentJobWorker(pool, snapshot, adapter=adapter, mcp_gateway=gateway, tracer=JobTracer())
        with worker._tracer.attempt(claimed) as trace:
            await worker._process_claimed(claimed, None, trace)
        result = (await jobs.get(session_id=a, job_id=submitted.job_id)).result
        assert [t.pins[0].pin_id for t in result.reference_plan.terms] == ["11", "44"]
        assert [args["role"] for _, args in gateway.calls] == ["pose"]
    asyncio.run(database_case(scenario))
