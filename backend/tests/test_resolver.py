"""trust-boundary AC-01 · term-card-catalog AC-03·AC-04 기반 resolver 테스트."""

from backend.schemas.enums import ClarificationType, ReasonCode, Role
from backend.schemas.models import InterpretationOutput, InterpretationSelection
from backend.services.resolver import (
    STATUS_ALL_INVALID,
    STATUS_CLARIFY,
    STATUS_PROCEED,
    ValidatedTerm,
    collapse_by_role,
    resolve,
)
from backend.schemas.enums import InterpretationState


def _interpretation(
    state=InterpretationState.SELECT_TERMS,
    selections=None,
    unresolved_constraints=None,
    clarifying_question=None,
    clarification_type=None,
):
    return InterpretationOutput(
        interpretation_state=state,
        selections=selections or [],
        unresolved_constraints=unresolved_constraints or [],
        clarifying_question=clarifying_question,
        clarification_type=clarification_type,
    )


def _sel(role, term_id, confidence=0.9):
    return InterpretationSelection(
        role=role, term_id=term_id, evidence=["단서"], confidence=confidence
    )


def _normal_cards(card_factory, snapshot_factory):
    cards = [
        card_factory("body_slim", role="body"),
        card_factory("pose_contrapposto", role="pose"),
        card_factory("pose_weight_shift", role="pose"),
        card_factory("view_front", role="view"),
        card_factory("pose_action", role="pose"),
    ]
    return snapshot_factory(cards, dsd=("pose_action",))


def test_proceed_single_selection_per_role(snapshot_factory, card_factory):
    snapshot = _normal_cards(card_factory, snapshot_factory)
    interp = _interpretation(
        selections=[
            _sel("body", "body_slim"),
            _sel("pose", "pose_weight_shift"),
            _sel("view", "view_front"),
        ]
    )
    result = resolve(interp, snapshot)
    assert result.status == STATUS_PROCEED
    assert [vt.selection.term_id for vt in result.terms] == [
        "body_slim",
        "pose_weight_shift",
        "view_front",
    ]
    assert result.reason_codes == []
    assert result.invalid_candidates == []
    # 미선택 역할은 unresolved로 남는다
    assert result.unresolved_roles == [Role.PERSPECTIVE, Role.LAYOUT]


def test_collapse_keeps_highest_confidence(card_factory):
    """역할당 최대 1개 — confidence 최대 후보만 유지 (EVAL-11 관점, 스키마 단독 방어)."""
    contrapposto = _sel("pose", "pose_contrapposto", confidence=0.5)
    weight_shift = _sel("pose", "pose_weight_shift", confidence=0.9)
    by_role = collapse_by_role(
        [
            ValidatedTerm(selection=contrapposto, card={}),
            ValidatedTerm(selection=weight_shift, card={}),
        ]
    )
    assert list(by_role)[0] == Role.POSE
    assert by_role[Role.POSE].selection.term_id == "pose_weight_shift"


def test_collapse_tie_keeps_first_seen(card_factory):
    first = _sel("pose", "pose_contrapposto", confidence=0.9)
    second = _sel("pose", "pose_weight_shift", confidence=0.9)
    by_role = collapse_by_role(
        [
            ValidatedTerm(selection=first, card={}),
            ValidatedTerm(selection=second, card={}),
        ]
    )
    assert by_role[Role.POSE].selection.term_id == "pose_contrapposto"


def test_invalid_candidate_dropped_while_valid_kept(snapshot_factory, card_factory):
    """EVAL-29 관점: 비활성/역할불일치 후보는 사용하지 않는다. 유효 후보는 유지."""
    snapshot = _normal_cards(card_factory, snapshot_factory)
    interp = _interpretation(
        selections=[_sel("body", "body_slim"), _sel("pose", "body_unknown")]
    )
    result = resolve(interp, snapshot)
    assert result.status == STATUS_PROCEED
    assert [vt.selection.term_id for vt in result.terms] == ["body_slim"]
    assert [c.term_id for c in result.invalid_candidates] == ["body_unknown"]


def test_role_mismatch_dropped(snapshot_factory, card_factory):
    snapshot = _normal_cards(card_factory, snapshot_factory)
    interp = _interpretation(
        selections=[_sel("body", "pose_weight_shift"), _sel("view", "view_front")]
    )
    result = resolve(interp, snapshot)
    assert result.status == STATUS_PROCEED
    assert [vt.selection.term_id for vt in result.terms] == ["view_front"]
    assert len(result.invalid_candidates) == 1


def test_all_candidates_invalid_marks_all_invalid(snapshot_factory, card_factory):
    snapshot = _normal_cards(card_factory, snapshot_factory)
    interp = _interpretation(selections=[_sel("pose", "body_unknown")])
    result = resolve(interp, snapshot)
    assert result.status == STATUS_ALL_INVALID
    assert result.terms == []


def test_clarify_maps_clarification_type_to_reason(snapshot_factory, card_factory):
    """EVAL-12: insufficient_visual_evidence → INSUFFICIENT_VISUAL_EVIDENCE."""
    snapshot = _normal_cards(card_factory, snapshot_factory)
    interp = _interpretation(
        state=InterpretationState.NEEDS_CLARIFICATION,
        unresolved_constraints=["바라는 포즈 축이 특정되지 않음"],
        clarifying_question="지지 다리 쪽인가요?",
        clarification_type=ClarificationType.INSUFFICIENT_VISUAL_EVIDENCE,
    )
    result = resolve(interp, snapshot)
    assert result.status == STATUS_CLARIFY
    assert result.reason_codes == [ReasonCode.INSUFFICIENT_VISUAL_EVIDENCE]
    assert result.clarifying_question == "지지 다리 쪽인가요?"


def test_clarify_conflicting_constraints(snapshot_factory, card_factory):
    """EVAL-15/16: conflicting_constraints → CONFLICTING_CONSTRAINTS."""
    snapshot = _normal_cards(card_factory, snapshot_factory)
    interp = _interpretation(
        state=InterpretationState.NEEDS_CLARIFICATION,
        unresolved_constraints=["모래시계형 비율과 역삼각형 실루엣 중 우선 순위"],
        clarifying_question="어느 쪽을 우선할까요?",
        clarification_type=ClarificationType.CONFLICTING_CONSTRAINTS,
    )
    result = resolve(interp, snapshot)
    assert result.status == STATUS_CLARIFY
    assert result.reason_codes == [ReasonCode.CONFLICTING_CONSTRAINTS]


def test_clarify_abstract_intent(snapshot_factory, card_factory):
    snapshot = _normal_cards(card_factory, snapshot_factory)
    interp = _interpretation(
        state=InterpretationState.NEEDS_CLARIFICATION,
        unresolved_constraints=["귀여운 포즈라는 추상 의도만 있음"],
        clarifying_question="어떤 축을 정할까요?",
        clarification_type=ClarificationType.ABSTRACT_INTENT,
    )
    result = resolve(interp, snapshot)
    assert result.status == STATUS_CLARIFY
    assert result.reason_codes == [ReasonCode.ABSTRACT_INTENT_ONLY]


def test_dsd_only_candidate_returns_clarify_without_url(snapshot_factory, card_factory):
    """term-card-catalog AC-04: 직접 검색 금지 카드만 후보면 URL·provider 없이 clarify."""
    snapshot = _normal_cards(card_factory, snapshot_factory)
    interp = _interpretation(selections=[_sel("pose", "pose_action")])
    result = resolve(interp, snapshot)
    assert result.status == STATUS_CLARIFY
    assert result.reason_codes == [ReasonCode.DIRECT_SEARCH_DISABLED]
    assert result.terms == []
    assert result.clarifying_question


def test_dsd_selection_ignored_when_searchable_exists(snapshot_factory, card_factory):
    snapshot = _normal_cards(card_factory, snapshot_factory)
    interp = _interpretation(
        selections=[_sel("body", "body_slim"), _sel("pose", "pose_action")]
    )
    result = resolve(interp, snapshot)
    assert result.status == STATUS_PROCEED
    assert [vt.selection.term_id for vt in result.terms] == ["body_slim"]