from backend.app.schemas import GettyAatLookup, GettyAatTerm
from mcp_server import server


def test_getty_mcp_tool_returns_the_client_lookup_result(monkeypatch) -> None:
    expected = GettyAatLookup(
        status="ok",
        terms=[
            GettyAatTerm(
                subject_uri="http://vocab.getty.edu/aat/300123456",
                label="contrapposto",
                source_url="http://vocab.getty.edu/aat/300123456",
            )
        ],
    )

    class FakeGettyAatClient:
        def search_terms(self, query: str, *, limit: int) -> GettyAatLookup:
            assert query == "contrapposto"
            assert limit == 3
            return expected

    monkeypatch.setattr(
        server,
        "getty_aat_client",
        FakeGettyAatClient(),
        raising=False,
    )

    result = server.getty_aat_lookup("contrapposto", limit=3)

    assert result == expected.model_dump()
