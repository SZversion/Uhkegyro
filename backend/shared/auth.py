"""공통 인증: JWT 검증·세션 쿠키 파싱."""
import os
from fastapi import Cookie, Depends, HTTPException, Request
from jose import jwt, JWTError
from backend.shared.config import get_settings


settings = get_settings()

SECRET_KEY = os.getenv("SESSION_SECRET", "dev-secret-change-in-prod")
ALGORITHM = "HS256"


def get_session_id(session_id: str | None = Cookie(default=None, alias="session_id")) -> str | None:
    """세션 쿠키에서 session_id 추출 (없으면 None)."""
    return session_id


def verify_token(authorization: str | None = None) -> dict:
    """Bearer 토큰 검증 (MCP 서비스 간 호출용)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def create_token(data: dict) -> str:
    """내부 서비스 호출용 토큰 생성."""
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(request: Request) -> dict:
    """FastAPI 의존성: 세션 쿠키 또는 Bearer 토큰으로 사용자 식별."""
    session_id = request.cookies.get("session_id")
    auth_header = request.headers.get("Authorization")
    if session_id:
        return {"session_id": session_id, "source": "cookie"}
    if auth_header and auth_header.startswith("Bearer "):
        payload = verify_token(auth_header)
        return {"session_id": payload.get("session_id"), "source": "bearer", **payload}
    raise HTTPException(status_code=401, detail="Authentication required")