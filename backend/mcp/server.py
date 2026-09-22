"""MCP 서버: FastMCP(v1.x) 기반 도구 노출.
FastAPI 앱에 마운트되어 `/mcp` 경로로 서비스됨.
"""
from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
from backend.shared.config import get_settings

settings = get_settings()

mcp = FastMCP("illustration-reference-mcp")


@mcp.tool()
async def search_pinterest_pins(query: str, limit: int = 10) -> list[dict]:
    """Pinterest에서 핀 검색 (추후 구현)."""
    return [{"id": "placeholder", "url": f"https://pinterest.com/pin/{query}", "description": f"Search result for: {query}"}]


@mcp.tool()
async def get_term_card(term_id: str) -> dict | None:
    """용어 카드 상세 조회 (추후 DB 연동)."""
    return {"term_id": term_id, "name": term_id.replace("_", " ").title(), "description": "TODO: DB에서 조회"}


@mcp.tool()
async def list_term_cards(category: str | None = None) -> list[dict]:
    """용어 카드 목록 조회 (카테고리 필터 옵션)."""
    return [{"term_id": "body_hourglass", "category": "body"}, {"term_id": "pose_contrapposto", "category": "pose"}]


def create_mcp_app() -> FastAPI:
    """FastMCP를 FastAPI 앱에 마운트하여 반환."""
    mcp_app = FastAPI(title="MCP Server")
    
    @mcp_app.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "mcp"}
    
    mcp_app.mount("/", mcp.streamable_http_app())
    return mcp_app


app = create_mcp_app()