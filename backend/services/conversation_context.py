"""Bounded context, original-source validation, and recall orchestration."""
from copy import deepcopy

from backend.schemas.enums import AgentStatus
from backend.schemas.models import AgentResult, InterpretationOutput, InterpretationSelection
from backend.schemas.memory import RecallQuery, SummaryOutput, RecallAnswer, MemorySource, NO_RECORDS, TOO_MANY
from backend.services.conversation_memory import record, evidence_text
from backend.services.llm import LLMInvalidStructuredOutput
from backend.services.resolver import resolve, STATUS_ALL_INVALID

async def prepare(memory, job, adapter, trace):
    context = await memory.load(job)
    state = context["state"]
    while rows := await memory.older(job, context):
        with trace.stage("memory-summary"):
            summary = await adapter.memory("summarize", {
                "summary": state.get("summary", ""),
                "summary_sources": state.get("summary_sources", []),
                "records": [record(row) for row in rows],
            }, SummaryOutput, **trace_args(job))
            allowed = set(state.get("summary_sources", [])) | {str(row["job_id"]) for row in rows}
            if not set(map(str, summary.source_job_ids)) <= allowed:
                raise LLMInvalidStructuredOutput("요약 출처가 입력 기록에 없습니다")
            state.update(summary=summary.text, summary_sources=list(map(str, summary.source_job_ids)),
                         summarized_through=[rows[-1]["created_at"].isoformat(), str(rows[-1]["job_id"])])
    return context


def prompt_context(context):
    state = context["state"]
    return {"constraints": state.get("constraints", {}), "pending_question": state.get("pending_question"),
            "summary": state.get("summary", ""), "summary_sources": state.get("summary_sources", []),
            "recent": context["recent"], "sources": context["sources"]}


def trace_args(job):
    return {key: str(job[key]) if key in ("job_id", "session_id") else job[key]
            for key in ("job_id", "session_id", "attempt", "max_attempts")}


async def recall(memory, job, context, adapter, trace):
    with trace.stage("memory-recall"):
        query = await adapter.memory("classify", {
            "request_text": job["request_text"], "session_context": prompt_context(context),
        }, RecallQuery, **trace_args(job))
        if query.mode == "none":
            return None, False
        records = await memory.search(job, query)
        if not records or len(records) > 20:
            return AgentResult(agent_status=AgentStatus.MEMORY_ANSWER,
                               memory_answer=NO_RECORDS if not records else TOO_MANY), query.mode == "recall"
        answer = await adapter.memory("answer", {
            "request_text": job["request_text"], "records": records,
        }, RecallAnswer, **trace_args(job))
        by_id = {item["job_id"]: item for item in records}
        sources = {}
        for citation in answer.citations:
            job_id = str(citation.job_id)
            if job_id not in by_id or not citation.quote.strip() or citation.quote not in evidence_text(by_id[job_id]):
                raise LLMInvalidStructuredOutput("회상 답변의 원본 인용을 확인할 수 없습니다")
            sources[job_id] = MemorySource(job_id=job_id, href="/api/jobs/" + job_id)
        context["sources"] += records
        return AgentResult(agent_status=AgentStatus.MEMORY_ANSWER, memory_answer=answer.answer,
                           sources=list(sources.values())), query.mode == "recall"


async def validate(memory, job, interpretation, snapshot):
    ids = [item.source_job_id for item in interpretation.selections if item.source_job_id]
    originals = await memory.records(job, ids) if ids else []
    by_id = {item["job_id"]: item for item in originals}
    for selection in interpretation.selections:
        if selection.source_job_id:
            original = by_id[str(selection.source_job_id)]
            allowed = [original["request_text"]] + [t[k] for t in original["terms"] for k in ("label_ko", "label_en")]
        else:
            allowed = [job["request_text"]]
        if any(not any(phrase in text for text in allowed) for phrase in selection.evidence):
            raise LLMInvalidStructuredOutput("선택 근거가 실제 요청 또는 원본 카드 라벨에 없습니다")
    seen = set()
    for update in interpretation.context_updates:
        if update.role in seen or not update.evidence.strip() or update.evidence not in job["request_text"]:
            raise LLMInvalidStructuredOutput("조건 변경에 현재 요청의 명시적 근거가 필요합니다")
        seen.add(update.role)
        if update.term_id is not None:
            candidate = InterpretationOutput(interpretation_state="select_terms", selections=[
                InterpretationSelection(role=update.role, term_id=update.term_id,
                                        evidence=[update.evidence], confidence=1)])
            if resolve(candidate, snapshot).status == STATUS_ALL_INVALID:
                raise LLMInvalidStructuredOutput("기억할 조건의 카드가 유효하지 않습니다")
    resolution = resolve(interpretation, snapshot)
    if resolution.status == STATUS_ALL_INVALID or resolution.invalid_candidates:
        raise LLMInvalidStructuredOutput("선택 카드가 현재 카탈로그에서 유효하지 않습니다")
    return resolution


def next_state(context, job, interpretation, result):
    state = deepcopy(context["state"])
    if result.agent_status not in (AgentStatus.SUCCESS, AgentStatus.PARTIAL_RESULT, AgentStatus.NEEDS_CLARIFICATION):
        return state
    constraints = state.setdefault("constraints", {})
    for update in interpretation.context_updates:
        if update.term_id is None:
            constraints.pop(update.role.value, None)
        else:
            constraints[update.role.value] = {"term_id": update.term_id, "evidence": update.evidence,
                                              "source_job_id": str(job["job_id"])}
    state["pending_question"] = result.clarifying_question
    return state
