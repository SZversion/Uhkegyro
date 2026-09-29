"""공개 API 라우터 — `docs/specs/api-contract.md`를 따른다.

세션과 job의 영속화는 PostgreSQL repositories가 맡는다.
"""
from __future__ import annotations

import json
import uuid
from typing import Annotated, Any

import asyncpg
from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from backend.schemas import (
    AgentRequest,
    ApiError,
    ApiErrorCode,
    Failure,
    FailureCode,
    JobEnvelope,
    SubmissionResponse,
)
from backend.shared.auth import SESSION_COOKIE_NAME, create_session_token, set_session_cookie
from backend.shared.config import get_settings
from backend.shared.database import close_pool, create_pool
from backend.services.job_repository import (
    IdempotencyConflict,
    JobNotFound,
)
from backend.services.job_repository import JobRepository
from backend.services.session_repository import SessionRepository

router = APIRouter(tags=["agent"])
_pool: Any | None = None


async def get_repositories() -> tuple[SessionRepository, JobRepository]:
    """Return PostgreSQL repositories backed by the process pool."""
    global _pool
    if _pool is None:
        _pool = await create_pool(get_settings())
    return SessionRepository(_pool), JobRepository(_pool)


@router.on_event("shutdown")
async def close_database_pool() -> None:
    global _pool
    if _pool is not None:
        await close_pool(_pool)
        _pool = None

IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"

MESSAGES = {
    ApiErrorCode.INVALID_REQUEST_TEXT: "1~500자의 설명을 보내 주세요. 공백만으로는 접수할 수 없습니다.",
    ApiErrorCode.IDEMPOTENCY_KEY_CONFLICT: "같은 요청 번호로 다른 내용을 보냈습니다. 처음 요청의 결과를 확인해 주세요.",
    ApiErrorCode.SESSION_REQUIRED: "이 브라우저에서 시작한 요청의 세션이 없습니다. 처음부터 다시 시도해 주세요.",
    ApiErrorCode.JOB_NOT_FOUND: "요청한 작업을 찾을 수 없습니다.",
}

STATUS_CODES = {
    ApiErrorCode.INVALID_REQUEST_TEXT: 422,
    ApiErrorCode.IDEMPOTENCY_KEY_CONFLICT: 409,
    ApiErrorCode.SESSION_REQUIRED: 401,
    ApiErrorCode.JOB_NOT_FOUND: 404,
}

DATABASE_ERROR_STATUS = 503
DATABASE_ERROR_MESSAGE = "현재 요청을 처리하지 못했습니다. 잠시 후 새 메시지로 다시 시도해 주세요."
DATABASE_CONNECTION_ERRORS = (
    asyncpg.PostgresConnectionError,
    asyncpg.InterfaceError,
    OSError,
    TimeoutError,
)


class ApiContractError(Exception):
    """`ApiError` 본문을 그대로 응답으로 내보내는 예외.

    `session_token`이 있으면 오류 응답에서도 세션 쿠키를 갱신한다. 유효 세션의
    활동이라면 결과가 404여도 90일 Max-Age를 다시 내보내야 하기 때문이다
    (`session-job-persistence.md:25`).
    """

    def __init__(
        self,
        code: ApiErrorCode | FailureCode,
        session_token: str | None = None,
    ) -> None:
        self.code = code
        self.session_token = session_token
        if code is FailureCode.DATABASE_UNAVAILABLE:
            self.status_code = DATABASE_ERROR_STATUS
            self.error = Failure(
                failure_code=code,
                user_message=DATABASE_ERROR_MESSAGE,
                retryable=False,
            )
        else:
            self.status_code = STATUS_CODES[code]
            self.error = ApiError(
                failure_code=code,
                user_message=MESSAGES[code],
                retryable=False,
            )
        super().__init__(code.value)


async def _database_call(operation: Any) -> Any:
    try:
        return await operation
    except DATABASE_CONNECTION_ERRORS:
        raise ApiContractError(FailureCode.DATABASE_UNAVAILABLE) from None


async def _parse_agent_request(request: Request) -> AgentRequest:
    """요청 본문을 `AgentRequest`로 검증한다.

    FastAPI의 기본 422 본문(`{"detail": ...}`)을 쓰지 않고 계약에 맞는
    `ApiError`를 내보내기 위해 직접 검증한다. `extra="forbid"` 덕에 허용하지 않은
    추가 필드도 여기서 함께 거절된다.
    """
    body = await request.body()
    if not body:
        raise ApiContractError(ApiErrorCode.INVALID_REQUEST_TEXT)
    try:
        payload: Any = json.loads(body)
        return AgentRequest.model_validate(payload)
    except (ValidationError, ValueError):
        raise ApiContractError(ApiErrorCode.INVALID_REQUEST_TEXT) from None


def _parse_idempotency_key(raw: str | None) -> str:
    """`Idempotency-Key`는 UUID 헤더다(`api-contract.md:23`).

    없거나 UUID 형식이 아니면 잘못된 요청으로 다룬다.
    """
    if not raw:
        raise ApiContractError(ApiErrorCode.INVALID_REQUEST_TEXT)
    try:
        return str(uuid.UUID(raw))
    except ValueError:
        raise ApiContractError(ApiErrorCode.INVALID_REQUEST_TEXT) from None


@router.post(
    "/api/agent",
    response_model=SubmissionResponse,
    status_code=202,
    summary="해석 요청을 접수하고 비동기 job을 만든다",
    responses={
        409: {"model": ApiError, "description": "같은 요청 번호에 다른 원문"},
        422: {"model": ApiError, "description": "형식이 잘못된 본문 또는 Idempotency-Key"},
        503: {"model": Failure, "description": "데이터 저장소를 사용할 수 없음"},
    },
)
async def submit_agent(
    request: Request,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias=IDEMPOTENCY_KEY_HEADER)] = None,
) -> SubmissionResponse:
    """새 세션을 발급하거나 기존 세션을 재사용하고 `202`와 queued job을 돌려준다.

    `api-contract.md` AC-01. 재전송이면 새 job을 만들지 않고 기존 job을 돌려준다
    (`session-job-persistence.md:19`).
    """
    payload = await _parse_agent_request(request)
    key = _parse_idempotency_key(idempotency_key)

    sessions, jobs = await _database_call(get_repositories())
    raw_cookie = request.cookies.get(SESSION_COOKIE_NAME)
    session_id = (
        await _database_call(sessions.resolve_session(raw_cookie)) if raw_cookie else None
    )
    token = raw_cookie if session_id is not None else create_session_token()

    try:
        if session_id is None:
            job, _created = await _database_call(
                jobs.submit_new_session(
                    session_token=token,
                    request_text=payload.request_text,
                    idempotency_key=key,
                )
            )
        else:
            job, _created = await _database_call(
                jobs.submit(
                    session_id=session_id,
                    request_text=payload.request_text,
                    idempotency_key=key,
                )
            )
    except IdempotencyConflict:
        raise ApiContractError(
            ApiErrorCode.IDEMPOTENCY_KEY_CONFLICT, session_token=token
        ) from None

    # 신규 발급이든 재사용이든 세션 활동이므로 90일로 갱신한다. 재사용할 때는
    # 토큰을 그대로 내보내 식별자가 바뀌지 않는다(`session-job-persistence.md:25`).
    set_session_cookie(response, token, get_settings())

    return SubmissionResponse(job_id=job.job_id)


@router.get(
    "/api/jobs/{job_id}",
    response_model=JobEnvelope,
    summary="job 상태와 종결 결과를 반환한다",
    responses={
        401: {"model": ApiError, "description": "유효한 세션 쿠키 없음"},
        404: {"model": ApiError, "description": "job이 없거나 소유 세션이 아님"},
        503: {"model": Failure, "description": "데이터 저장소를 사용할 수 없음"},
    },
)
async def read_job(
    job_id: str,
    request: Request,
    response: Response,
) -> JobEnvelope:
    """소유 세션만 자신의 job을 읽는다. `api-contract.md` AC-06."""
    raw_cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw_cookie:
        raise ApiContractError(ApiErrorCode.SESSION_REQUIRED) from None

    sessions, jobs = await _database_call(get_repositories())
    session_id = await _database_call(sessions.resolve_session(raw_cookie))
    if session_id is None:
        raise ApiContractError(ApiErrorCode.SESSION_REQUIRED) from None

    # 조회가 성공하든 404여도 유효 세션의 활동이므로 쿠키를 갱신한다.
    set_session_cookie(response, raw_cookie, get_settings())

    try:
        return await _database_call(jobs.get(session_id=session_id, job_id=job_id))
    except JobNotFound:
        raise ApiContractError(
            ApiErrorCode.JOB_NOT_FOUND, session_token=raw_cookie
        ) from None
