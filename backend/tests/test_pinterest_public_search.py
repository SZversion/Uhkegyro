"""서버 공개 검색 provider의 HTML fixture 계약 테스트."""

import asyncio
from pathlib import Path

import pytest

from backend.schemas.enums import PinStatus, ReasonCode, Role
from backend.services import pinterest_public_search
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


def test_parse_public_search_html_reads_rendered_pin_data_attributes():
    html = """
    <div data-test-id="pin" data-test-pin-id="1344049888485695"></div>
    <div data-test-id="pin" data-test-pin-id="1344049888485695"></div>
    <div data-test-id="pin" data-test-pin-id="2468013579246801"></div>
    <div data-grid-item-id="not-a-pin"></div>
    """

    pins = parse_public_search_html(html)

    assert [(pin.pin_id, pin.pin_url) for pin in pins] == [
        ("1344049888485695", "https://www.pinterest.com/pin/1344049888485695/"),
        ("2468013579246801", "https://www.pinterest.com/pin/2468013579246801/"),
    ]


def test_load_search_result_html_waits_for_rendered_pin_selector():
    class FakePage:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        async def goto(self, url: str, **kwargs: object) -> None:
            self.calls.append(("goto", url, kwargs))

        async def wait_for_selector(self, selector: str, **kwargs: object) -> None:
            self.calls.append(("wait_for_selector", selector, kwargs))

        async def content(self) -> str:
            self.calls.append(("content",))
            return '<div data-test-id="pin" data-test-pin-id="1344049888485695"></div>'

    page = FakePage()

    html = asyncio.run(pinterest_public_search._load_search_result_html(
        page,
        "https://www.pinterest.com/search/pins/?q=gesture+drawing",
        15_000,
    ))

    assert html.startswith('<div data-test-id="pin"')
    assert page.calls == [
        ("goto", "https://www.pinterest.com/search/pins/?q=gesture+drawing", {
            "wait_until": "domcontentloaded", "timeout": 15_000,
        }),
        ("wait_for_selector", '[data-test-id="pin"][data-test-pin-id]', {
            "state": "attached", "timeout": 15_000,
        }),
        ("content",),
    ]


def test_load_public_search_html_returns_content_without_waiting_for_pin_selector():
    class FakePage:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        async def goto(self, url: str, **kwargs: object) -> None:
            self.calls.append(("goto", url, kwargs))

        async def content(self) -> str:
            self.calls.append(("content",))
            return "<main>no matching Pins</main>"

    page = FakePage()

    html = asyncio.run(pinterest_public_search._load_public_search_html(
        page,
        "https://www.pinterest.com/search/pins/?q=contrapposto",
        15_000,
    ))

    assert html == "<main>no matching Pins</main>"
    assert page.calls == [
        ("goto", "https://www.pinterest.com/search/pins/?q=contrapposto", {
            "wait_until": "domcontentloaded", "timeout": 15_000,
        }),
        ("content",),
    ]


def test_provider_uses_cdp_loader_when_endpoint_is_given(monkeypatch):
    received: list[tuple[str, int, str]] = []

    async def cdp_loader(cdp_endpoint: str, search_url: str, timeout_ms: int) -> str:
        received.append((cdp_endpoint, search_url, timeout_ms))
        return _fixture_html()

    monkeypatch.setattr(
        pinterest_public_search,
        "_load_html_with_cdp",
        cdp_loader,
        raising=False,
    )

    outcome = asyncio.run(
        PinterestPublicSearchProvider(
            cdp_endpoint="http://127.0.0.1:9222",
        ).search(Role.POSE, ("contrapposto pose", "standing reference"))
    )

    assert received == [(
        "http://127.0.0.1:9222",
        "https://www.pinterest.com/search/pins/?q="
        "contrapposto+pose+standing+reference+drawing",
        15_000,
    )]
    assert [pin.pin_id for pin in outcome.pins] == ["111", "222"]


def test_cdp_loader_closes_only_its_temporary_page_and_disconnects():
    class FakePage:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        async def goto(self, url: str, **kwargs: object) -> None:
            self.calls.append(("goto", url, kwargs))

        async def wait_for_selector(self, selector: str, **kwargs: object) -> None:
            self.calls.append(("wait_for_selector", selector, kwargs))

        async def content(self) -> str:
            self.calls.append(("content",))
            return '<div data-test-id="pin" data-test-pin-id="1344049888485695"></div>'

        async def close(self) -> None:
            self.calls.append(("close",))

    class FakeContext:
        def __init__(self, page: FakePage) -> None:
            self.page = page
            self.calls: list[tuple] = []

        async def new_page(self) -> FakePage:
            self.calls.append(("new_page",))
            return self.page

    class FakeBrowser:
        def __init__(self, context: FakeContext) -> None:
            self.contexts = [context]
            self.calls: list[tuple] = []

        async def close(self) -> None:
            self.calls.append(("close",))

    class FakeChromium:
        def __init__(self, browser: FakeBrowser) -> None:
            self.browser = browser
            self.calls: list[tuple] = []

        async def connect_over_cdp(self, endpoint: str) -> FakeBrowser:
            self.calls.append(("connect_over_cdp", endpoint))
            return self.browser

    class FakePlaywright:
        def __init__(self, chromium: FakeChromium) -> None:
            self.chromium = chromium

    page = FakePage()
    context = FakeContext(page)
    browser = FakeBrowser(context)
    chromium = FakeChromium(browser)

    html = asyncio.run(pinterest_public_search._load_html_from_cdp_browser(
        FakePlaywright(chromium),
        "http://127.0.0.1:9222",
        "https://www.pinterest.com/search/pins/?q=contrapposto",
        15_000,
    ))

    assert html.startswith('<div data-test-id="pin"')
    assert chromium.calls == [("connect_over_cdp", "http://127.0.0.1:9222")]
    assert context.calls == [("new_page",)]
    assert page.calls[-1] == ("close",)
    assert browser.calls == [("close",)]


def test_provider_rejects_html_loader_and_cdp_endpoint_together():
    async def loader(_: str) -> str:
        return _fixture_html()

    with pytest.raises(ValueError, match="html_loader와 cdp_endpoint"):
        PinterestPublicSearchProvider(
            html_loader=loader,
            cdp_endpoint="http://127.0.0.1:9222",
        )


def test_provider_rejects_non_loopback_cdp_endpoint():
    with pytest.raises(ValueError, match="loopback"):
        PinterestPublicSearchProvider(cdp_endpoint="http://example.com:9222")


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
