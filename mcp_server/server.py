"""MCP server for Getty AAT vocabulary candidates."""

from mcp.server.fastmcp import FastMCP

from backend.app.services.getty_aat import GettyAatClient

mcp = FastMCP("illustration-reference-getty")
getty_aat_client = GettyAatClient()


def getty_aat_lookup(query: str, *, limit: int = 5) -> dict:
    """Return Getty AAT vocabulary candidates without requesting image data."""

    return getty_aat_client.search_terms(query, limit=limit).model_dump()


@mcp.tool()
def search_getty_aat_terms(query: str, limit: int = 5) -> dict:
    """Look up Getty AAT term candidates for human vocabulary review.

    Args:
        query: A normalized English vocabulary phrase, not a Pinterest URL or image request.
        limit: Number of candidates from 1 to 5.
    """
    return getty_aat_lookup(query, limit=limit)


if __name__ == "__main__":
    mcp.run()
