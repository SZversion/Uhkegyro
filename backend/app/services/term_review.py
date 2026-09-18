"""Create human-review-only drafts for unresolved vocabulary candidates."""

from backend.app.schemas import Confidence, GettyAatTerm, TermCardReviewDraft


def create_term_card_review_draft(
    *,
    confidence: Confidence,
    candidate_phrase: str,
    limitations: list[str],
    getty_candidates: list[GettyAatTerm],
) -> TermCardReviewDraft | None:
    """Return a draft only for low-confidence interpretations with limitations."""

    if confidence != "low" or not limitations:
        return None

    return TermCardReviewDraft(
        candidate_phrase=candidate_phrase.strip(),
        limitations=limitations,
        getty_candidates=getty_candidates,
    )
