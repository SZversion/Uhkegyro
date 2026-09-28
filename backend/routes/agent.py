"""공개 API 라우터 — `docs/specs/api-contract.md`를 따른다.

이 라우터는 저장 계층의 내부 구조를 모른다. 세션 토큰과 job의 영속화는
`backend/services/session_store.py`가 맡고, 그 구현이 교체돼도 라우터 계약은
바뀌지 않는다.
"""
from __future__ import annotations

import json
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from backend.schemas import (
    AgentRequest,
    ApiError,
    ApiErrorCode,
    JobEnvelope,
    SubmissionResponse,
)
from backend.shared.auth import SESSION_COOKIE_NAME, set_session_cookie
from backend.shared.config import get_settings
from backend.services.session_store import (
    IdempotencyConflict,
    JobNotFound,
    SessionRequired,
    get_session_store,
)

router = APIRouter(tags=["agent"])

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


class ApiContractError(Exception):
    """`ApiError` 본문을 그대로 응답으로 내보내는 예외.

    `session_token`이 있으면 오류 응답에서도 세션 쿠키를 갱신한다. 유효 세션의
    활동이라면 결과가 404여도 90일 Max-Age를 다시 내보내야 하기 때문이다
    (`session-job-persistence.md:25`).
    """

    def __init__(self, code: ApiErrorCode, session_token: str | None = None) -> None:
        self.code = code
        self.status_code = STATUS_CODES[code]
        self.session_token = session_token
        self.error = ApiError(failure_code=code, user_message=MESSAGES[code], retryable=False)
        super().__init__(code.value)


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

    store = get_session_store()
    raw_cookie = request.cookies.get(SESSION_COOKIE_NAME)
    try:
        session_id = store.resolve_session(raw_cookie)
        token = raw_cookie
    except SessionRequired:
        token, session_id = store.issue_session()

    try:
        job, _created = store.submit(
            session_id=session_id,
            request_text=payload.request_text,
            idempotency_key=key,
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
    },
)
async def read_job(
    job_id: str,
    request: Request,
    response: Response,
) -> JobEnvelope:
    """소유 세션만 자신의 job을 읽는다. `api-contract.md` AC-06."""
    store = get_session_store()
    raw_cookie = request.cookies.get(SESSION_COOKIE_NAME)
    try:
        session_id = store.resolve_session(raw_cookie)
    except SessionRequired:
        raise ApiContractError(ApiErrorCode.SESSION_REQUIRED) from None

    # 조회가 성공하든 404여도 유효 세션의 활동이므로 쿠키를 갱신한다.
    set_session_cookie(response, raw_cookie, get_settings())

    try:
        return store.read_job(session_id=session_id, job_id=job_id)
    except JobNotFound:
        raise ApiContractError(
            ApiErrorCode.JOB_NOT_FOUND, session_token=raw_cookie
        ) from None
