"""SearXNG Google Images provider contract tests."""

import asyncio
import pytest

from backend.schemas.enums import PinStatus, ReasonCode, Role
from backend.services.searxng_pinterest_search import (
    SearXNGPinterestSearchProvider,
    parse_search_results,
)
from backend.services.failure_mapping import OperationalFailure
from backend.schemas.enums import FailureCode


def test_parse_search_results_keeps_only_unique_pin_urls_in_order():
    pins = parse_search_results({"results": [
        {"url": "https://www.pinterest.com/pin/111/"},
        {"url": "https://example.com/pin/222/"},
        {"url": "https://kr.pinterest.com/pin/333?x=1"},
        {"url": "https://pinterest.com/pin/111"},
        {"url": "https://pinterest.com/pin/idea/444"},
        {"url": "http://pinterest.com/pin/555/"},
        {"url": "https://[invalid/pin/666/"},
    ]})

    assert [(pin.pin_id, pin.pin_url, pin.status) for pin in pins] == [
        ("111", "https://www.pinterest.com/pin/111/", PinStatus.AVAILABLE),
        ("333", "https://www.pinterest.com/pin/333/", PinStatus.AVAILABLE),
    ]


def test_parse_search_results_limits_to_first_eight_unique_pins():
    payload = {"results": [{"url": f"https://pinterest.com/pin/{pin_id}/"}
                            for pin_id in range(1, 11)]}
    assert [pin.pin_id for pin in parse_search_results(payload)] == [str(i) for i in range(1, 9)]


def test_provider_sends_only_google_images_and_card_query():
    received = []

    async def load(url, params):
        received.append((url, params))
        return {"results": [{"url": "https://pinterest.com/pin/123/"}]}

    outcome = asyncio.run(SearXNGPinterestSearchProvider(
        base_url="http://searxng:8080/", json_loader=load,
    ).search(Role.POSE, ("standing pose", "weight shift reference")))

    assert received == [("http://searxng:8080/search", {
        "q": "!goi standing pose weight shift reference drawing site:pinterest.com/pin",
        "categories": "images",
        "format": "json",
        "language": "en",
    })]
    assert outcome.role is Role.POSE
    assert [pin.pin_id for pin in outcome.pins] == ["123"]
    assert outcome.code is None


def test_provider_marks_successful_empty_search():
    async def load(url, params):
        return {"results": []}

    outcome = asyncio.run(SearXNGPinterestSearchProvider(
        base_url="http://searxng:8080", json_loader=load,
    ).search(Role.VIEW, ("low angle",)))
    assert outcome.pins == []
    assert outcome.code is ReasonCode.PIN_RESULTS_EMPTY


def test_provider_marks_missing_endpoint_unavailable():
    with pytest.raises(OperationalFailure) as error:
        asyncio.run(SearXNGPinterestSearchProvider(base_url="").search(
            Role.BODY, ("slim body",)
        ))
    assert error.value.failure_code is FailureCode.CONFIGURATION_ERROR


def test_provider_marks_invalid_json_shape_unavailable():
    async def load(url, params):
        return {"unexpected": []}

    outcome = asyncio.run(SearXNGPinterestSearchProvider(
        base_url="http://searxng:8080", json_loader=load,
    ).search(Role.POSE, ("standing",)))
    assert outcome.pins == []
    assert outcome.code is ReasonCode.PIN_SEARCH_UNAVAILABLE
