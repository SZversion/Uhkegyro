"""서버 공개 검색 provider의 HTML fixture 계약 테스트."""

import asyncio
from pathlib import Path

from backend.schemas.enums import PinStatus, ReasonCode, Role
from backend.services.pinterest_public_search import (
    PinterestPublicSearchProvider,
    parse_public_search_html,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "pinterest_public_search.html"


def _fixture_html() -> str:
    return FIXTURE_PATH.read_text(encoding="utf-8")


def test_parse_public_search_html_keeps_unique_canonical_pins_in_first_seen_order():
    pins = parse_public_search_html(_fixture_html())

    assert [(pin.pin_id, pin.pin_url, pin.status) for pin in pins] == [
        ("111", "https://www.pinterest.com/pin/111/", PinStatus.AVAILABLE),
        ("222", "https://www.pinterest.com/pin/222/", PinStatus.AVAILABLE),
    ]
    assert all(pin.thumbnail_url is None for pin in pins)


def test_parse_public_search_html_limits_results_to_first_eight_unique_pins():
    html = "".join(f'<a href="/pin/{pin_id}/">pin</a>' for pin_id in range(1, 10))

    pins = parse_public_search_html(html)

    assert [pin.pin_id for pin in pins] == [str(pin_id) for pin_id in range(1, 9)]


def test_provider_builds_card_only_search_url_and_returns_parsed_results():
    received_urls: list[str] = []

    async def fixture_loader(url: str) -> str:
        received_urls.append(url)
        return _fixture_html()

    provider = PinterestPublicSearchProvider(html_loader=fixture_loader)

    outcome = asyncio.run(
        provider.search(Role.POSE, ("gesture drawing", "action line reference"))
    )

    assert received_urls == [
        "https://www.pinterest.com/search/pins/?q=gesture+drawing+action+line+reference+drawing"
    ]
    assert outcome.role is Role.POSE
    assert [pin.pin_id for pin in outcome.pins] == ["111", "222"]
    assert outcome.code is None


def test_provider_marks_successful_empty_search_as_pin_results_empty():
    async def empty_loader(_: str) -> str:
        return '<a href="/idea-pin/333/">not a pin result</a>'

    outcome = asyncio.run(
        PinterestPublicSearchProvider(html_loader=empty_loader).search(
            Role.VIEW, ("low angle",)
        )
    )

    assert outcome.role is Role.VIEW
    assert outcome.pins == []
    assert outcome.code is ReasonCode.PIN_RESULTS_EMPTY


def test_provider_marks_loader_timeout_as_pin_search_unavailable():
    async def timeout_loader(_: str) -> str:
        raise TimeoutError("timed out")

    outcome = asyncio.run(
        PinterestPublicSearchProvider(html_loader=timeout_loader).search(
            Role.BODY, ("slim body",)
        )
    )

    assert outcome.role is Role.BODY
    assert outcome.pins == []
    assert outcome.code is ReasonCode.PIN_SEARCH_UNAVAILABLE
