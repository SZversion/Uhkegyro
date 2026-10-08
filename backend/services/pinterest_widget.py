"""Server-only Pinterest Widget lookup; thumbnails exist only in returned models."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from urllib.parse import urlparse

import httpx

from backend.schemas.enums import JobStatus, PinStatus, Role
from backend.schemas.models import JobEnvelope, PinResult
from backend.services.pinterest_provider import PinterestProvider
from backend.services.response_assembler import RoleSearchOutcome

WIDGET_URL = "https://widgets.pinterest.com/v3/pidgets/pins/info/?pin_ids={pin_id}"
JsonLoader = Callable[[str], Awaitable[object]]


class PinterestWidgetProvider:
    """Decorate a search provider while keeping its role/fragment contract."""

    def __init__(self, source: PinterestProvider, widget: "PinterestWidgetClient") -> None:
        self._source = source
        self._widget = widget

    async def search(self, role: Role, query_fragments: tuple[str, ...]) -> RoleSearchOutcome:
        return await self._widget.enrich_outcome(await self._source.search(role, query_fragments))


class PinterestWidgetClient:
    def __init__(self, *, json_loader: JsonLoader | None = None,
                 http_client: httpx.AsyncClient | None = None) -> None:
        self._json_loader = json_loader
        self._http_client = http_client
        self._owns_http_client = False
        if json_loader is None and http_client is None:
            self._http_client = httpx.AsyncClient(timeout=10.0)
            self._owns_http_client = True

    async def aclose(self) -> None:
        if self._owns_http_client and self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def enrich_outcome(self, outcome: RoleSearchOutcome) -> RoleSearchOutcome:
        """Return at most eight Pins in their original order without changing the input."""
        semaphore = asyncio.Semaphore(8)
        pins = await asyncio.gather(
            *(self._lookup(pin, semaphore) for pin in outcome.pins[:8])
        )
        return RoleSearchOutcome(role=outcome.role, pins=pins, code=outcome.code)

    async def enrich_job(self, envelope: JobEnvelope) -> JobEnvelope:
        """Re-query persisted Pin IDs for one completed API response."""
        return await self._enrich_job(envelope, asyncio.Semaphore(8))

    async def enrich_jobs(self, envelopes: list[JobEnvelope]) -> list[JobEnvelope]:
        """Re-query a batch of completed jobs with one shared concurrency limit."""
        semaphore = asyncio.Semaphore(8)
        return await asyncio.gather(*(self._enrich_job(envelope, semaphore) for envelope in envelopes))

    async def _enrich_job(self, envelope: JobEnvelope, semaphore: asyncio.Semaphore) -> JobEnvelope:
        if envelope.job_status is not JobStatus.COMPLETED or envelope.result is None:
            return envelope
        result = envelope.model_copy(deep=True)
        if result.result is None or result.result.reference_plan is None:
            return result
        terms = result.result.reference_plan.terms
        locations = [(term, index, pin) for term in terms for index, pin in enumerate(term.pins)]
        enriched = await asyncio.gather(
            *(self._lookup(pin, semaphore) for _, _, pin in locations)
        )
        for (term, index, _), pin in zip(locations, enriched):
            term.pins[index] = pin
        return result

    async def _lookup(self, pin: PinResult, semaphore: asyncio.Semaphore) -> PinResult:
        url = None
        if pin.pin_id.isascii() and pin.pin_id.isdigit():
            try:
                async with semaphore:
                    widget_url = WIDGET_URL.format(pin_id=pin.pin_id)
                    if self._json_loader is not None:
                        payload = await self._json_loader(widget_url)
                    else:
                        response = await self._http_client.get(widget_url)
                        response.raise_for_status()
                        payload = response.json()
                url = _largest_image(payload, pin.pin_id)
            except Exception:
                pass
        return PinResult(
            pin_id=pin.pin_id,
            pin_url=pin.pin_url,
            thumbnail_url=url,
            status=PinStatus.AVAILABLE if url else PinStatus.DELETED,
        )


_shared_widget_client: PinterestWidgetClient | None = None


def get_shared_widget_client() -> PinterestWidgetClient:
    global _shared_widget_client
    if _shared_widget_client is None:
        _shared_widget_client = PinterestWidgetClient()
    return _shared_widget_client


async def close_shared_widget_client() -> None:
    global _shared_widget_client
    client, _shared_widget_client = _shared_widget_client, None
    if client is not None:
        await client.aclose()


def _largest_image(payload: object, pin_id: str) -> str | None:
    if not isinstance(payload, Mapping) or not isinstance(payload.get("data"), list):
        return None
    for item in payload["data"]:
        if not isinstance(item, Mapping) or str(item.get("id")) != pin_id:
            continue
        images = item.get("images")
        if not isinstance(images, Mapping):
            return None
        best_url, best_area = None, 0
        for image in images.values():
            if not isinstance(image, Mapping):
                continue
            url, width, height = image.get("url"), image.get("width"), image.get("height")
            if not isinstance(url, str):
                continue
            parsed_url = urlparse(url)
            if parsed_url.scheme != "https" or not parsed_url.netloc:
                continue
            if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
                continue
            area = width * height
            if area > best_area:
                best_url, best_area = url, area
        return best_url
    return None
