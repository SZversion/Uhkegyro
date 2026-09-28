"""FastAPI 진입점 (공개 API 전용).

LLM 호출은 여기가 아니라 services/ 아래 한곳에 모으세요.
3차 프로젝트에서 그 자리에 RAG 그래프가 들어옵니다 — 호출부가 흩어져 있으면 그때 전부 뜯어야 합니다.

MCP는 별도 서비스(backend/mcp/main.py)로 분리되어 배포됩니다.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend.routes.agent import ApiContractError, router as agent_router
from backend.shared.auth import set_session_cookie
from backend.services.catalog_repository import CatalogLoadError, load_catalog
from backend.shared.config import get_settings, resolve_term_cards_dir

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        app.state.catalog = load_catalog(resolve_term_cards_dir(settings))
    except CatalogLoadError as error:
        raise RuntimeError(f"CATALOG_INVALID_AT_STARTUP: {error}") from error
    yield

app = FastAPI(title="2차 프로젝트 API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.allowed_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ApiContractError)
async def handle_api_contract_error(request: FastAPI, exc: ApiContractError) -> JSONResponse:
    """계약이 정한 오류 본문(`ApiError`)을 그대로 내보낸다.

    기본 FastAPI 오류는 `{"detail": ...}`이라 프론트가 두 모양을 다뤄야 한다.
    오류 응답은 라우터가 만든 새 응답이라 쿠키 갱신이 함께 실려 있다.
    """
    response = JSONResponse(status_code=exc.status_code, content=exc.error.model_dump())
    if exc.session_token:
        set_session_cookie(response, exc.session_token, settings)
    return response


app.include_router(agent_router)


@app.get("/health")
def health() -> dict:
    """채점자와 배포 환경이 서비스 상태를 확인하는 곳."""
    return {"status": "ok"}


# 남은 도메인 엔드포인트:
#   - T19 영속화(`backend/services/session_store.py`의 인메모리 구현을 Neon
#     PostgreSQL로 교체)와 worker의 lease·재시도 전이가 남았다.
#   - PinterestCrawlerProvider와 해석 파이프라인(LLM 어댑터 → resolver →
#     assembler)은 이 라우터의 `submit_agent`가 만든 job을 처리하는 위치에 붙는다.
#   - 요청 ID·사용 모델·토큰 수·지연 시간을 로그에 남깁니다 (축 ③ 구조화 로그)
