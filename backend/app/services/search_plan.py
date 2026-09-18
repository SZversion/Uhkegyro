"""Deterministic Pinterest search URL construction with no network access."""

from urllib.parse import urlencode

from backend.app.schemas import PinterestSearch, ReferencePlanItem, SearchPlan, Selection
from backend.app.services.validator import validate_selection

PINTEREST_SEARCH_URL = "https://www.pinterest.com/search/pins/"
ROLE_ORDER = {"body": 0, "pose": 1, "view": 2, "perspective": 3, "layout": 4}


def build_search_plan(selections: list[Selection]) -> SearchPlan:
    """Create role-specific and combined browser search links from selections."""

    cards = [(selection, validate_selection(selection)) for selection in selections]
    cards.sort(key=lambda pair: ROLE_ORDER[pair[1].role])

    roles = [card.role for _, card in cards]
    if len(roles) != len(set(roles)):
        raise ValueError("Only one primary selection is allowed per role")

    reference_plan = [
        ReferencePlanItem(
            role=card.role,
            term_id=card.term_id,
            label=card.label,
            look_for=card.look_for,
            pinterest_search=_build_pinterest_search(
                f"character {card.query_fragment} reference"
            ),
        )
        for _, card in cards
    ]

    combined_pinterest_search = None
    if cards:
        fragments = " ".join(card.query_fragment for _, card in cards)
        combined_pinterest_search = _build_pinterest_search(
            f"character {fragments} reference"
        )

    return SearchPlan(
        combined_pinterest_search=combined_pinterest_search,
        reference_plan=reference_plan,
    )


def _build_pinterest_search(query: str) -> PinterestSearch:
    return PinterestSearch(
        query=query,
        url=f"{PINTEREST_SEARCH_URL}?{urlencode({'q': query})}",
    )
