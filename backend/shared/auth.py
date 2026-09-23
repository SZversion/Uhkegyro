"""공통 인증: 세션 쿠키 파싱 (메인 API용).
MCP 인증은 Cloud Run IAM으로 처리하므로 별도 JWT 불필요.
"""
from fastapi import Cookie, HTTPException, Request


def get_session_id(session_id: str | None = Cookie(default=None, alias="session_id")) -> str | None:
    """세션 쿠키에서 session_id 추출 (없으면 None)."""
    return session_id


async def get_current_user(request: Request) -> dict:
    """FastAPI 의존성: 세션 쿠키로 사용자 식별 (메인 API용)."""
    session_id = request.cookies.get("session_id")
    if session_id:
        return {"session_id": session_id, "source": "cookie"}
    raise HTTPException(status_code=401, detail="Authentication required")