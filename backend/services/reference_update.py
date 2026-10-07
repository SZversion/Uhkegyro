"""Reuse trusted prior role results; refresh images without reinterpreting cards."""
from dataclasses import replace

from backend.schemas.enums import AgentStatus, ReasonCode, Role
from backend.schemas.models import AgentResult, InterpretationSelection, ReferencePlan
from backend.services.resolver import ResolutionResult, ValidatedTerm, STATUS_CLARIFY, STATUS_PROCEED


def previous_terms(context, snapshot):
    payload = context.get("previous_result") or {}
    if not payload:
        return {}
    result = AgentResult.model_validate(payload)
    return {term.role: term for term in result.reference_plan.terms
            if (card := snapshot.get_active(term.term_id)) and card["role"] == term.role.value
            and not snapshot.is_direct_search_disabled(term.term_id)} if result.reference_plan else {}


def refresh_resolution(previous, snapshot, context):
    original = ((context.get("previous_result") or {}).get("reference_plan") or {}).get("terms", [])
    if not previous or len(previous) != len(original):
        return ResolutionResult(status=STATUS_CLARIFY,
            reason_codes=[ReasonCode.INSUFFICIENT_VISUAL_EVIDENCE],
            clarifying_question="먼저 원하는 체형·포즈·시점을 알려주시겠어요?")
    return ResolutionResult(status=STATUS_PROCEED, terms=[ValidatedTerm(
        selection=InterpretationSelection(role=role, term_id=term.term_id,
            evidence=[term.label_ko], confidence=1), card=snapshot.get_active(term.term_id),
    ) for role, term in previous.items()])


def select_searches(resolution, previous):
    if resolution.status != STATUS_PROCEED:
        return resolution
    return replace(resolution, terms=[term for term in resolution.terms
        if term.selection.role not in previous
        or previous[term.selection.role].term_id != term.selection.term_id
        or term.selection.source_job_id is None])


def merge_preserved(result, previous, interpretation):
    if result.reference_plan is None:
        return result
    removed = {item.role for item in interpretation.context_updates if item.term_id is None}
    terms = {role: term.model_copy(deep=True) for role, term in previous.items() if role not in removed}
    terms.update({term.role: term for term in result.reference_plan.terms})
    ordered = [terms[role] for role in Role if role in terms]
    codes = list(dict.fromkeys(code for term in ordered for code in term.reason_codes))
    return AgentResult(agent_status=AgentStatus.PARTIAL_RESULT if codes else AgentStatus.SUCCESS,
        reference_plan=ReferencePlan(terms=ordered,
            unresolved_roles=[role for role in result.reference_plan.unresolved_roles if role not in terms]),
        reason_codes=codes, answer_text=result.answer_text)
