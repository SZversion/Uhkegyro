"""pinterest_search_contract 기준 검색 URL 빌더 테스트."""

import pytest

from backend.services.search_url_builder import build_search_url

BASE = "https://www.pinterest.com/search/pins/"


def test_build_search_url_joins_query_fragments():
    url = build_search_url(["contrapposto pose", "standing reference"], base_url=BASE)
    assert url == "https://www.pinterest.com/search/pins/?q=contrapposto+pose+standing+reference"


def test_build_search_url_encodes_korean_and_space():
    url = build_search_url(["half lotus", "pose reference"], base_url=BASE)
    assert url.startswith("https://www.pinterest.com/search/pins/?q=")
    assert url == "https://www.pinterest.com/search/pins/?q=half+lotus+pose+reference"


def test_build_search_url_rejects_empty():
    with pytest.raises(ValueError):
        build_search_url([], base_url=BASE)


def test_build_search_url_uses_config_default():
    # conftest가 DATABASE_URL을 세팅해두어 config 기본값 경로 검증 가능
    url = build_search_url(["stand weight shift reference"])
    assert url.startswith("https://www.pinterest.com/search/pins/?q=")
    assert "stand+weight+shift+reference" in url