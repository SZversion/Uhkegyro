"""서버 Playwright 기반 Pinterest 공개 검색 provider.

이 모듈은 검증된 TERM_CARD 검색 조각으로 공개 검색 HTML을 읽어 Pin ID와
원본 URL만 수집한다. widget 썸네일 조회와 worker 연결은 후속 작업의 책임이다.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from html.parser import HTMLParser
import re
from typing import Any
from urllib.parse import urlparse

from backend.schemas.enums import PinStatus, ReasonCode, Role
from backend.schemas.models import PinResult
from backend.services.response_assembler import RoleSearchOutcome
from backend.services.search_url_builder import build_search_url


HtmlLoader = Callable[[str], Awaitable[str]]
_PIN_PATH_PATTERN = re.compile(r"^/pin/(?P<pin_id>\d+)/?$")
_PINTEREST_HOSTS = {"pinterest.com", "www.pinterest.com"}
_CANONICAL_PIN_URL = "https://www.pinterest.com/pin/{pin_id}/"
_RENDERED_PIN_SELECTOR = '[data-test-id="pin"][data-test-pin-id]'
_LOOPBACK_CDP_HOSTS = {"127.0.0.1", "::1", "localhost"}


class PinterestPublicSearchProvider:
    """서버에서 공개 Pinterest 검색 HTML을 읽는 독립 provider."""

    def __init__(
        self,
        *,
        html_loader: HtmlLoader | None = None,
        cdp_endpoint: str | None = None,
        timeout_ms: int = 15_000,
    ) -> None:
        if timeout_ms <= 0:
            raise ValueError("timeout_ms는 0보다 커야 합니다")
        if html_loader is not None and cdp_endpoint is not None:
            raise ValueError("html_loader와 cdp_endpoint를 함께 지정할 수 없습니다")
        if cdp_endpoint is not None:
            _validate_loopback_cdp_endpoint(cdp_endpoint)
        self._html_loader = html_loader
        self._cdp_endpoint = cdp_endpoint
        self._timeout_ms = timeout_ms

    async def search(
        self, role: Role, query_fragments: tuple[str, ...]
    ) -> RoleSearchOutcome:
        """카드 검색 조각으로 최대 8개 Pin ID와 원본 URL을 수집한다."""
        if not query_fragments or any(not part.strip() for part in query_fragments):
            raise ValueError("활성 카드의 비어 있지 않은 query_fragments가 필요합니다")

        search_url = build_search_url(list(query_fragments))
        try:
            html = await self._load_html(search_url)
        except Exception:
            return RoleSearchOutcome(
                role=role,
                pins=[],
                code=ReasonCode.PIN_SEARCH_UNAVAILABLE,
            )

        pins = parse_public_search_html(html)
        return RoleSearchOutcome(
            role=role,
            pins=pins,
            code=ReasonCode.PIN_RESULTS_EMPTY if not pins else None,
        )

    async def _load_html(self, search_url: str) -> str:
        if self._html_loader is not None:
            return await self._html_loader(search_url)
        if self._cdp_endpoint is not None:
            return await _load_html_with_cdp(
                self._cdp_endpoint,
                search_url,
                self._timeout_ms,
            )
        return await _load_html_with_playwright(search_url, self._timeout_ms)


def parse_public_search_html(html: str, limit: int = 8) -> list[PinResult]:
    """공개 검색 HTML의 Pin 링크를 순서대로 최대 ``limit``개 정규화한다."""
    if limit < 1:
        raise ValueError("limit은 1 이상이어야 합니다")

    parser = _PinCandidateParser()
    parser.feed(html)
    parser.close()

    seen_pin_ids: set[str] = set()
    pins: list[PinResult] = []
    for pin_id in parser.pin_ids:
        if pin_id in seen_pin_ids:
            continue
        seen_pin_ids.add(pin_id)
        pins.append(
            PinResult(
                pin_id=pin_id,
                pin_url=_CANONICAL_PIN_URL.format(pin_id=pin_id),
                thumbnail_url=None,
                status=PinStatus.AVAILABLE,
            )
        )
        if len(pins) == limit:
            break
    return pins


class _PinCandidateParser(HTMLParser):
    """Pin 앵커와 렌더링된 Pin grid의 식별자를 등장 순서대로 수집한다."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.pin_ids: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "a":
            href = attributes.get("href")
            if href is not None:
                pin_id = _pin_id_from_href(href)
                if pin_id is not None:
                    self.pin_ids.append(pin_id)

        pin_id = attributes.get("data-test-pin-id")
        if attributes.get("data-test-id") == "pin" and pin_id is not None and pin_id.isdigit():
            self.pin_ids.append(pin_id)


def _pin_id_from_href(href: str) -> str | None:
    parsed = urlparse(href)
    if parsed.netloc and parsed.netloc.lower() not in _PINTEREST_HOSTS:
        return None
    match = _PIN_PATH_PATTERN.fullmatch(parsed.path)
    return match.group("pin_id") if match else None


def _validate_loopback_cdp_endpoint(cdp_endpoint: str) -> None:
    parsed = urlparse(cdp_endpoint)
    if parsed.scheme != "http" or parsed.hostname not in _LOOPBACK_CDP_HOSTS:
        raise ValueError("cdp_endpoint는 http loopback URL이어야 합니다")


async def _load_html_with_playwright(search_url: str, timeout_ms: int) -> str:
    """서버 Chromium으로 공개 검색 페이지 HTML을 읽고 모든 리소스를 닫는다."""
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page()
            return await _load_search_result_html(page, search_url, timeout_ms)
        finally:
            await browser.close()


async def _load_html_with_cdp(
    cdp_endpoint: str,
    search_url: str,
    timeout_ms: int,
) -> str:
    """로컬 Chromium CDP 연결의 임시 검색 Page에서 HTML을 읽는다."""
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        return await _load_html_from_cdp_browser(
            playwright,
            cdp_endpoint,
            search_url,
            timeout_ms,
        )


async def _load_html_from_cdp_browser(
    playwright: Any,
    cdp_endpoint: str,
    search_url: str,
    timeout_ms: int,
) -> str:
    """CDP browser의 기존 context를 보존하고 임시 Page만 닫는다."""
    browser = await playwright.chromium.connect_over_cdp(cdp_endpoint)
    page: Any | None = None
    try:
        if not browser.contexts:
            raise RuntimeError("CDP browser에 기본 context가 없습니다")
        page = await browser.contexts[0].new_page()
        return await _load_search_result_html(page, search_url, timeout_ms)
    finally:
        if page is not None:
            await page.close()
        await browser.close()


async def _load_search_result_html(page: Any, search_url: str, timeout_ms: int) -> str:
    """렌더링된 Pin grid가 붙은 뒤 현재 DOM HTML을 반환한다."""
    await page.goto(search_url, wait_until="domcontentloaded", timeout=timeout_ms)
    await page.wait_for_selector(
        _RENDERED_PIN_SELECTOR,
        state="attached",
        timeout=timeout_ms,
    )
    return await page.content()
