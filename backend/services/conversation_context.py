"""Bounded context, original-source validation, and recall orchestration."""
import asyncio
import re
from copy import deepcopy

from backend.schemas.enums import AgentStatus
from backend.schemas.models import AgentResult, InterpretationOutput, InterpretationSelection
from backend.schemas.memory import RecallQuery, SummaryOutput, RecallAnswer, MemorySource, NO_RECORDS, TOO_MANY
from backend.services.conversation_memory import record, evidence_text, summary_input
from backend.services.llm import LLMInvalidStructuredOutput, LLMTimeout
from backend.services.resolver import resolve, STATUS_ALL_INVALID

SUMMARY_BUDGET_SECONDS = 30

async def prepare(memory, job, adapter, trace):
    context = await memory.load(job)
    data = summary_input(context, await memory.older(job, context))
    context["summary_incomplete"] = bool(data["records"]) and (
        data["truncated"] or context["state"].get("summary_input_hash") != data["input_hash"])
    return context


async def summarize(memory, job, adapter, trace, *, context=None, rows=None):
    context = context if context is not None else await memory.load(job)
    data = summary_input(context, rows if rows is not None else await memory.older(job, context))
    if not data["records"] or context["state"].get("summary_input_hash") == data["input_hash"]:
        return context
    with trace.stage("memory-summary"):
        try:
            summary = await asyncio.wait_for(adapter.memory("summarize", {
                "summary": "", "summary_sources": [], "records": data["records"],
            }, SummaryOutput, **trace_args(job)), timeout=SUMMARY_BUDGET_SECONDS)
        except TimeoutError as error:
            raise LLMTimeout("대화 요약 시간 초과") from error
    allowed = {item["job_id"] for item in data["records"]}
    if not set(map(str, summary.source_job_ids)) <= allowed:
        raise LLMInvalidStructuredOutput("요약 출처가 입력 기록에 없습니다", stage="conversation_validation",
                                         feedback=[{"path": [], "code": "summary_source_invalid"}])
    context["state"].update(summary=summary.text, summary_sources=list(map(str, summary.source_job_ids)),
                            summary_input_hash=data["input_hash"], summary_truncated=data["truncated"])
    context["state"].pop("summarized_through", None)
    context["summary_incomplete"] = data["truncated"]
    return context


def prompt_context(context):
    state = context["state"]
    return {"constraints": state.get("constraints", {}), "pending_question": state.get("pending_question"),
            "summary": state.get("summary", ""), "summary_sources": state.get("summary_sources", []),
            "recent": context["recent"], "sources": context["sources"],
            "summary_incomplete": context.get("summary_incomplete", False)}


def trace_args(job):
    return {key: str(job[key]) if key in ("job_id", "session_id") else job[key]
            for key in ("job_id", "session_id", "attempt", "max_attempts")}


async def recall(memory, job, context, adapter, trace):
    if is_clear_new_request(job["request_text"], context):
        return None, False
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
                raise LLMInvalidStructuredOutput("회상 답변의 원본 인용을 확인할 수 없습니다", stage="conversation_validation",
                                                 feedback=[{"path": [], "code": "recall_citation_invalid"}])
            sources[job_id] = MemorySource(job_id=job_id, href="/api/jobs/" + job_id)
        context["sources"] += records
        return AgentResult(agent_status=AgentStatus.MEMORY_ANSWER, memory_answer=answer.answer,
                           sources=list(sources.values())), query.mode == "recall"


def is_clear_new_request(text, context):
    text = text.casefold().strip()
    if context["state"].get("pending_question") or len(text) < 12:
        return False
    historical = ("아까|이전|전에|지난|그때|방금|추천|기억|했|였|뭐|무엇|어떤|그거|그것|똑같|"
                  "같은|다시|그대로|유지|바꿔|변경|말해|알려|앞서|저번|마지막|첫|결과|사용한|보낸|선택한|[?？]|"
                  r"(^|\s)(이|그|저|해당)\s|\b(first|previous|earlier|remember|recommend\w*|suggest\w*|again|that|what|change|same|history)\b")
    if re.search(historical, text):
        return False
    return bool(re.search(r"체형|자세|포즈|시점|원근|배치|캐릭터|레퍼런스|\b(reference|pose|character|perspective)\b", text)
                and re.search(r"찾아|그려|보여|검색|\b(find|draw|show|search)\b", text))


async def validate(memory, job, interpretation, snapshot):
    ids = [item.source_job_id for item in interpretation.selections if item.source_job_id]
    originals = await memory.records(job, ids) if ids else []
    by_id = {item["job_id"]: item for item in originals}
    verified_source_texts = {}
    for selection in interpretation.selections:
        if selection.source_job_id:
            original = by_id.get(str(selection.source_job_id))
            if original is None:
                raise LLMInvalidStructuredOutput("선택 출처가 검증된 선행 기록에 없습니다", stage="conversation_validation",
                                                 feedback=[{"path": [], "code": "selection_source_invalid"}])
            allowed = [original["request_text"]] + [t[k] for t in original["terms"] for k in ("label_ko", "label_en")]
        else:
            allowed = [job["request_text"]]
        if any(not any(phrase in text for text in allowed) for phrase in selection.evidence):
            raise LLMInvalidStructuredOutput("선택 근거가 실제 요청 또는 원본 카드 라벨에 없습니다", stage="conversation_validation",
                                             feedback=[{"path": [], "code": "selection_evidence_invalid"}])
        if selection.source_job_id:
            verified_source_texts[str(selection.source_job_id)] = tuple(allowed)
    seen = set()
    for update in interpretation.context_updates:
        if update.role in seen or not update.evidence.strip() or update.evidence not in job["request_text"]:
            raise LLMInvalidStructuredOutput("조건 변경에 현재 요청의 명시적 근거가 필요합니다", stage="conversation_validation",
                                             feedback=[{"path": [], "code": "context_evidence_invalid"}])
        seen.add(update.role)
        if update.term_id is not None:
            candidate = InterpretationOutput(interpretation_state="select_terms", selections=[
                InterpretationSelection(role=update.role, term_id=update.term_id,
                                        evidence=[update.evidence], confidence=1)])
            if resolve(candidate, snapshot, request_text=str(job["request_text"])).status == STATUS_ALL_INVALID:
                raise LLMInvalidStructuredOutput("기억할 조건의 카드가 유효하지 않습니다", stage="conversation_validation",
                                                 feedback=[{"path": [], "code": "context_card_invalid"}])
    resolution = resolve(interpretation, snapshot, request_text=str(job["request_text"]),
                         verified_source_texts=verified_source_texts)
    if resolution.status == STATUS_ALL_INVALID or resolution.invalid_candidates:
        raise LLMInvalidStructuredOutput("선택 카드가 현재 카탈로그에서 유효하지 않습니다", stage="conversation_validation",
                                         feedback=[{"path": [], "code": "selection_card_invalid"}])
    return resolution


def next_state(context, job, interpretation, result):
    state = deepcopy(context["state"])
    if result.agent_status not in (AgentStatus.SUCCESS, AgentStatus.PARTIAL_RESULT, AgentStatus.NEEDS_CLARIFICATION):
        return state
    constraints = state.setdefault("constraints", {})
    for update in interpretation.context_updates if result.agent_status is not AgentStatus.NEEDS_CLARIFICATION else []:
        if update.term_id is None:
            constraints.pop(update.role.value, None)
        else:
            constraints[update.role.value] = {"term_id": update.term_id, "evidence": update.evidence,
                                              "source_job_id": str(job["job_id"])}
    state["pending_question"] = result.clarifying_question
    return state
