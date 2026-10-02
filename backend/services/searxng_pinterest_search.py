"""SearXNG Google Images 기반 Pinterest Pin 검색 provider."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
import logging
import re
from urllib.parse import urlparse

import httpx

from backend.schemas.enums import FailureCode, PinStatus, ReasonCode, Role
from backend.schemas.models import PinResult
from backend.services.failure_mapping import OperationalFailure, classify_failure
from backend.services.response_assembler import RoleSearchOutcome
from backend.services.search_url_builder import SEARCH_SUFFIXES

logger = logging.getLogger(__name__)

JsonLoader = Callable[[str, Mapping[str, str]], Awaitable[object]]
_PIN_PATH_PATTERN = re.compile(r"^/pin/(?P<pin_id>[0-9]+)/?$")
_CANONICAL_PIN_URL = "https://www.pinterest.com/pin/{pin_id}/"


class SearXNGPinterestSearchProvider:
    """SearXNG Google Images JSON 결과에서 Pin 링크만 반환한다."""

    def __init__(
        self,
        *,
        base_url: str,
        json_loader: JsonLoader | None = None,
        suffix: str = "drawing",
    ) -> None:
        if suffix not in SEARCH_SUFFIXES:
            raise ValueError("지원하지 않는 검색 접미사입니다")
        self._suffix = suffix
        self._base_url = base_url.rstrip("/")
        self._json_loader = json_loader or _load_search_json

    async def search(
        self, role: Role, query_fragments: tuple[str, ...]
    ) -> RoleSearchOutcome:
        if not query_fragments or any(not part.strip() for part in query_fragments):
            raise ValueError("활성 카드의 비어 있지 않은 query_fragments가 필요합니다")
        if not self._base_url:
            raise OperationalFailure(FailureCode.CONFIGURATION_ERROR)

        params = {
            "q": f"!goi {' '.join(query_fragments)} {self._suffix} site:pinterest.com/pin",
            "categories": "images",
            "format": "json",
            "language": "en",
        }
        try:
            payload = await self._json_loader(f"{self._base_url}/search", params)
        except Exception as error:
            code = classify_failure(error, context="search")
            if code is FailureCode.CONFIGURATION_ERROR:
                raise OperationalFailure(code) from None
            logger.warning("SearXNG search unavailable", extra={"failure_code": code.value})
            return RoleSearchOutcome(role=role, pins=[], code=ReasonCode.PIN_SEARCH_UNAVAILABLE)

        if not isinstance(payload, Mapping) or not isinstance(payload.get("results"), list):
            logger.warning(
                "SearXNG search unavailable",
                extra={"failure_code": FailureCode.SEARCH_UPSTREAM_UNAVAILABLE.value},
            )
            return RoleSearchOutcome(role=role, pins=[], code=ReasonCode.PIN_SEARCH_UNAVAILABLE)
        pins = parse_search_results(payload)
        engine_errors = payload.get("unresponsive_engines", [])
        google_images_unresponsive = isinstance(engine_errors, list) and any(
            isinstance(engine_error, (list, tuple))
            and engine_error
            and isinstance(engine_error[0], str)
            and engine_error[0].casefold() == "google images"
            for engine_error in engine_errors
        )
        if google_images_unresponsive:
            logger.warning(
                "SearXNG Google Images engine unavailable",
                extra={"failure_code": FailureCode.SEARCH_UPSTREAM_UNAVAILABLE.value},
            )
            return RoleSearchOutcome(
                role=role, pins=pins, code=ReasonCode.PIN_SEARCH_UNAVAILABLE
            )
        return RoleSearchOutcome(
            role=role,
            pins=pins,
            code=ReasonCode.PIN_RESULTS_EMPTY if not pins else None,
        )


def parse_search_results(payload: object, limit: int = 8) -> list[PinResult]:
    """SearXNG JSON에서 유효한 Pinterest Pin 결과를 최대 ``limit``개 정규화한다."""
    if limit < 1:
        raise ValueError("limit은 1 이상이어야 합니다")
    if not isinstance(payload, Mapping) or not isinstance(payload.get("results"), list):
        return []

    seen_pin_ids: set[str] = set()
    pins: list[PinResult] = []
    for result in payload["results"]:
        if not isinstance(result, Mapping) or not isinstance(result.get("url"), str):
            continue
        pin_id = _pin_id_from_url(result["url"])
        if pin_id is None or pin_id in seen_pin_ids:
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


def _pin_id_from_url(url: str) -> str | None:
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (host == "pinterest.com" or host.endswith(".pinterest.com")):
        return None
    match = _PIN_PATH_PATTERN.fullmatch(parsed.path)
    return match.group("pin_id") if match else None


async def _load_search_json(url: str, params: Mapping[str, str]) -> object:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()
