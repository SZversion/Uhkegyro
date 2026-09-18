from backend.app.schemas import GettyAatTerm
from backend.app.services.term_review import create_term_card_review_draft


def test_low_confidence_with_a_limitation_creates_a_pending_review_draft() -> None:
    candidate = GettyAatTerm(
        subject_uri="http://vocab.getty.edu/aat/300123456",
        label="contrapposto",
        source_url="http://vocab.getty.edu/aat/300123456",
    )

    draft = create_term_card_review_draft(
        confidence="low",
        candidate_phrase="contrapposto-like standing pose",
        limitations=["unmapped_visual_term"],
        getty_candidates=[candidate],
    )

    assert draft is not None
    assert draft.status == "pending_human_review"
    assert draft.confidence == "low"
    assert draft.candidate_phrase == "contrapposto-like standing pose"
    assert draft.getty_candidates == [candidate]


def test_medium_confidence_does_not_create_a_review_draft() -> None:
    draft = create_term_card_review_draft(
        confidence="medium",
        candidate_phrase="uncertain standing pose",
        limitations=["unmapped_visual_term"],
        getty_candidates=[],
    )

    assert draft is None


def test_low_confidence_without_limitations_does_not_create_a_review_draft() -> None:
    draft = create_term_card_review_draft(
        confidence="low",
        candidate_phrase="uncertain standing pose",
        limitations=[],
        getty_candidates=[],
    )

    assert draft is None
