"""Getty AAT SPARQL client for vocabulary candidates only."""

from typing import Final

import httpx

from backend.app.schemas import GettyAatLookup, GettyAatTerm

GETTY_AAT_SPARQL_ENDPOINT: Final = "https://vocab.getty.edu/sparql"
GETTY_AAT_SOURCE_NAME: Final = "Getty AAT"
GETTY_AAT_TIMEOUT_SECONDS: Final = 5.0
MAX_GETTY_AAT_RESULTS: Final = 5


class GettyAatClient:
    """Query Getty AAT terms without retrieving images or web-page content."""

    def __init__(
        self,
        *,
        endpoint: str = GETTY_AAT_SPARQL_ENDPOINT,
        timeout_seconds: float = GETTY_AAT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def search_terms(self, query: str, *, limit: int = MAX_GETTY_AAT_RESULTS) -> GettyAatLookup:
        """Return up to five Getty AAT term candidates for a normalized phrase."""

        normalized_query = query.strip()
        if not normalized_query or len(normalized_query) > 80:
            raise ValueError("Getty AAT query must contain 1 to 80 non-whitespace characters")
        if not normalized_query.isprintable():
            raise ValueError("Getty AAT query must contain printable characters only")
        if not 1 <= limit <= MAX_GETTY_AAT_RESULTS:
            raise ValueError(f"Getty AAT limit must be between 1 and {MAX_GETTY_AAT_RESULTS}")

        try:
            with httpx.Client(
                transport=self._transport,
                timeout=self._timeout_seconds,
            ) as client:
                response = client.post(
                    self._endpoint,
                    data={"query": _build_aat_label_query(normalized_query, limit)},
                    headers={"Accept": "application/sparql-results+json"},
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError):
            return GettyAatLookup(
                status="unavailable",
                limitations=["getty_aat_unavailable"],
            )

        try:
            terms = _parse_aat_terms(payload)
        except (KeyError, TypeError, ValueError):
            return GettyAatLookup(
                status="unavailable",
                limitations=["getty_aat_unavailable"],
            )

        return GettyAatLookup(status="ok", terms=terms)


def _build_aat_label_query(query: str, limit: int) -> str:
    escaped_query = _escape_sparql_literal(query)
    return f'''\
PREFIX aat: <http://vocab.getty.edu/aat/>
PREFIX gvp: <http://vocab.getty.edu/ontology#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX xl: <http://www.w3.org/2008/05/skos-xl#>

SELECT DISTINCT ?subject ?label WHERE {{
  ?subject a gvp:Subject ;
    skos:inScheme aat: ;
    gvp:prefLabelGVP/xl:literalForm ?label .
  FILTER(CONTAINS(LCASE(STR(?label)), LCASE("{escaped_query}")))
}}
LIMIT {limit}
'''


def _parse_aat_terms(payload: object) -> list[GettyAatTerm]:
    bindings = payload["results"]["bindings"]
    terms: list[GettyAatTerm] = []
    for binding in bindings:
        subject_uri = binding["subject"]["value"]
        label = binding["label"]["value"]
        terms.append(
            GettyAatTerm(
                subject_uri=subject_uri,
                label=label,
                source_name=GETTY_AAT_SOURCE_NAME,
                source_url=subject_uri,
            )
        )
    return terms


def _escape_sparql_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
