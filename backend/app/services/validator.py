"""Validation that constrains future LLM output to approved term cards."""

from backend.app.domain.term_cards import TERM_CARDS, TermCard
from backend.app.schemas import Selection


def validate_selection(selection: Selection) -> TermCard:
    """Return the matching term card or reject an invalid axis/kind combination."""

    card = TERM_CARDS.get(selection.term_id)
    if card is None:
        raise ValueError(f"Unknown term_id: {selection.term_id}")
    if card.axis != selection.axis:
        raise ValueError("term_id does not match the selection axis")
    if selection.axis == "composition" and card.kind != selection.kind:
        raise ValueError("term_id does not match the composition kind")
    if selection.axis != "composition" and selection.kind is not None:
        raise ValueError("body and pose selections must not include a kind")
    return card
