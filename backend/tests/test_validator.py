import pytest

from backend.app.schemas import Selection
from backend.app.services.validator import validate_selection


def test_validate_selection_rejects_a_term_id_on_the_wrong_axis() -> None:
    selection = Selection(
        axis="pose",
        term_id="body_inverted_triangle",
        evidence=["어깨가 넓어요."],
    )

    with pytest.raises(ValueError, match="axis"):
        validate_selection(selection)


def test_validate_selection_rejects_an_unknown_term_id() -> None:
    selection = Selection(
        axis="pose",
        term_id="pose_not_a_real_term",
        evidence=["서 있어요."],
    )

    with pytest.raises(ValueError, match="Unknown term_id"):
        validate_selection(selection)


def test_validate_selection_requires_the_matching_composition_kind() -> None:
    selection = Selection(
        axis="composition",
        kind="layout",
        term_id="view_front",
        evidence=["정면에서 봐요."],
    )

    with pytest.raises(ValueError, match="composition kind"):
        validate_selection(selection)
