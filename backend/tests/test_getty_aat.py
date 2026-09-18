from urllib.parse import parse_qs

import httpx
import pytest

from backend.app.services.getty_aat import GettyAatClient


def test_getty_aat_client_returns_term_candidates_without_image_data() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url == "https://vocab.getty.edu/sparql"
        submitted_query = parse_qs(request.content.decode())["query"][0]
        assert "contrapposto" in submitted_query
        assert "skos:inScheme aat:" in submitted_query
        return httpx.Response(
            200,
            json={
                "head": {"vars": ["subject", "label"]},
                "results": {
                    "bindings": [
                        {
                            "subject": {
                                "type": "uri",
                                "value": "http://vocab.getty.edu/aat/300123456",
                            },
                            "label": {"type": "literal", "value": "contrapposto"},
                        }
                    ]
                },
            },
        )

    client = GettyAatClient(transport=httpx.MockTransport(handler))

    result = client.search_terms("contrapposto")

    assert result.status == "ok"
    assert result.limitations == []
    assert result.terms[0].subject_uri == "http://vocab.getty.edu/aat/300123456"
    assert result.terms[0].label == "contrapposto"
    assert result.terms[0].source_name == "Getty AAT"


def test_getty_aat_client_returns_unavailable_on_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Getty timed out", request=request)

    client = GettyAatClient(transport=httpx.MockTransport(handler))

    result = client.search_terms("contrapposto")

    assert result.status == "unavailable"
    assert result.terms == []
    assert result.limitations == ["getty_aat_unavailable"]


def test_getty_aat_client_rejects_control_characters_before_a_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("A malformed query must not reach Getty")

    client = GettyAatClient(transport=httpx.MockTransport(handler))

    with pytest.raises(ValueError, match="printable"):
        client.search_terms("contrapposto\nDROP")
