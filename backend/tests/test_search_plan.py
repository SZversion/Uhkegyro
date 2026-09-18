from urllib.parse import parse_qs, urlparse

from backend.app.schemas import Selection
from backend.app.services.search_plan import build_search_plan


def test_build_search_plan_orders_only_selected_roles_and_builds_urls() -> None:
    plan = build_search_plan(
        [
            Selection(
                axis="composition",
                kind="perspective",
                term_id="perspective_three_point",
                evidence=["높은 빌딩 사이에서 선이 위로 향해요."],
            ),
            Selection(
                axis="body",
                term_id="body_inverted_triangle",
                evidence=["어깨가 골반보다 넓어요."],
            ),
            Selection(
                axis="composition",
                kind="view",
                term_id="view_front",
                evidence=["정면에서 보이게 해요."],
            ),
        ]
    )

    assert [item.role for item in plan.reference_plan] == [
        "body",
        "view",
        "perspective",
    ]
    assert parse_qs(urlparse(plan.reference_plan[0].pinterest_search.url).query) == {
        "q": ["character inverted triangle body silhouette reference"]
    }
    assert parse_qs(urlparse(plan.combined_pinterest_search.url).query) == {
        "q": [
            "character inverted triangle body silhouette front view character "
            "three point perspective background reference"
        ]
    }
