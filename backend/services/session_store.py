"""세션·job 저장 계층 — 현재는 인메모리 구현이다.

**교체 지점.** KHS의 `PR #33`(anonymous session boundary)이 세션 토큰 발급·저장
규칙을 확정하면 이 모듈만 Neon PostgreSQL + `asyncpg` 구현으로 갈아끼운다.
라우터(`backend/routes/agent.py`)와 스키마(`backend/schemas/`)는 이 모듈의 내부
구조에 의존하지 않으므로 계약은 바뀌지 않는다. `session-job-persistence.md`가
이 계층의 단일 기준이다.

이 구현이 지키는 것:

- 쿠키 값은 불투명한 토큰이고 DB에는 SHA-256 해시만 남긴다(`:24`).
- 세션 활동마다 90일 쿠키를 갱신한다(`:25`).
- `Idempotency-Key`는 UUID 헤더이며, 같은 세션·같은 키·10분 이내·같은
  `request_text_hash`면 기존 job을 반환한다. 같은 키에 다른 원문이면 충돌이다
  (`:19`).
- `GET /api/jobs/{job_id}`는 소유 세션만 읽을 수 있고, 소유하지 않으면
  `JOB_NOT_FOUND`를 반환한다(`:29`).

이 구현이 하지 않는 것(미착수):

- Neon PostgreSQL 연결, migration, session 행의 3개월 정리(`:26`).
- session별 advisory lock을 통한 idempotency 직렬화(`:27`).
- worker의 lease·재시도 전이(`postgres-job-worker.md`).

여기서 만들어진 job은 mock 결과로 즉시 종결된다. `attempt`는 worker가 한 번 집어
갔다고 보고 1부터 시작한다. `session-job-persistence.md:15`의 `attempt=0`은 아직
worker가 집어가지 않은 DB 행의 초기값이고, `JobEnvelope.attempt`가 요구하는 1 이상
은 worker가 집은 뒤의 값이라 두 층이 맞는다.
"""
from __future__ import annotations

import hashlib
import secrets
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Callable

from backend.schemas.enums import AgentStatus, JobStatus, ReasonCode
from backend.schemas.models import (
    PROGRESS_POLL_AFTER_MS,
    RETRY_COUNT_MAX,
    AgentResult,
    JobEnvelope,
)

SESSION_COOKIE_NAME = "session_id"
SESSION_MAX_AGE_SECONDS = 90 * 24 * 60 * 60
IDEMPOTENCY_TTL_SECONDS = 10 * 60

#: mock 종결 결과. T14 LLM 어댑터 → T17 resolver → assembler 경로가 이 자리를
#: 대체하며, 그때 `AgentResult`는 `success`와 `reference_plan`을 갖게 된다.
MOCK_CLARIFYING_QUESTION = "구도와 시점을 함께 정하시나요, 한쪽만 정하시나요?"
MOCK_USER_MESSAGE = "구도나 시점이 아직 모호합니다. 어느 쪽을 먼저 정할지 알려주시면 용어를 골라드리겠습니다."


class IdempotencyConflict(Exception):
    """같은 세션·같은 키에 10분 이내 다른 원문이 들어왔을 때."""


class JobNotFound(Exception):
    """job이 없거나, 현재 세션이 그 job의 소유자가 아닐 때."""


class SessionRequired(Exception):
    """유효한 세션 쿠키가 없을 때."""


def hash_opaque(value: str) -> str:
    """쿠키 토큰과 idempotency 키는 해시해서만 보관한다."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass
class _Session:
    session_id: str
    token_hash: str
    last_activity_at: float


@dataclass
class _Job:
    job_id: str
    session_id: str
    request_text: str
    request_text_hash: str
    idempotency_key_hash: str
    idempotency_expires_at: float
    attempt: int
    max_attempts: int
    status: JobStatus
    result: AgentResult | None = None


def build_mock_result() -> AgentResult:
    """mock 종결 결과.

    `needs_clarification`을 고른 이유: `success`는 `reference_plan`을 강제하고
    `partial_result`는 `PIN_*` reason code를 강제하므로 둘 다 카탈로그나 검색
    provider가 필요하다. 이 슬라이스의 목표는 요청·응답 계약이므로, 카탈로그 없이
    성립하고 reason code 규칙까지 지킨 `needs_clarification`을 쓴다.
    """
    return AgentResult(
        agent_status=AgentStatus.NEEDS_CLARIFICATION,
        reason_codes=[ReasonCode.INSUFFICIENT_VISUAL_EVIDENCE],
        reference_plan=None,
        clarifying_question=MOCK_CLARIFYING_QUESTION,
        user_message=MOCK_USER_MESSAGE,
    )


class InMemorySessionStore:
    """프로세스 안에만 사는 세션·job 저장소. 재시작하면 전부 사라진다."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._sessions: dict[str, _Session] = {}  # token_hash -> session
        self._jobs: dict[str, _Job] = {}  # job_id -> job
        self._idempotency: dict[tuple[str, str], str] = {}  # (session_id, key_hash) -> job_id

    def issue_session(self) -> tuple[str, str]:
        """새 익명 세션을 만들고 `(원문 토큰, session_id)`를 돌려준다.

        원문 토큰은 여기서만 존재하고, 저장소 안에는 해시만 남는다.
        """
        token = secrets.token_urlsafe(32)
        session = _Session(
            session_id=str(uuid.uuid4()),
            token_hash=hash_opaque(token),
            last_activity_at=self._clock(),
        )
        with self._lock:
            self._sessions[session.token_hash] = session
        return token, session.session_id

    def resolve_session(self, token: str | None) -> str:
        """쿠키 토큰을 `session_id`로 바꾼다. 활동 시각도 함께 갱신한다.

        유효한 토큰이 아니면 `SessionRequired`를 던진다.
        """
        if not token:
            raise SessionRequired
        with self._lock:
            session = self._sessions.get(hash_opaque(token))
            if session is None:
                raise SessionRequired
            session.last_activity_at = self._clock()
            return session.session_id

    def submit(
        self,
        *,
        session_id: str,
        request_text: str,
        idempotency_key: str,
    ) -> tuple[_Job, bool]:
        """job을 만들거나 같은 요청이면 기존 job을 돌려준다.

        반환값은 `(job, 새로 만들었는지)`다. 재전송이면 `False`가 나온다.
        """
        key_hash = hash_opaque(idempotency_key)
        text_hash = hash_opaque(request_text)
        now = self._clock()

        with self._lock:
            index = (session_id, key_hash)
            existing_id = self._idempotency.get(index)
            if existing_id is not None:
                existing = self._jobs[existing_id]
                if existing.idempotency_expires_at > now:
                    if existing.request_text_hash == text_hash:
                        return existing, False
                    raise IdempotencyConflict

            job = _Job(
                job_id=str(uuid.uuid4()),
                session_id=session_id,
                request_text=request_text,
                request_text_hash=text_hash,
                idempotency_key_hash=key_hash,
                idempotency_expires_at=now + IDEMPOTENCY_TTL_SECONDS,
                attempt=1,
                max_attempts=RETRY_COUNT_MAX,
                status=JobStatus.COMPLETED,
                result=build_mock_result(),
            )
            self._jobs[job.job_id] = job
            self._idempotency[index] = job.job_id
            return job, True

    def read_job(self, *, session_id: str, job_id: str) -> JobEnvelope:
        """소유 세션만 job을 읽는다. 소유자가 아니면 없는 job과 같은 응답을 준다."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.session_id != session_id:
                raise JobNotFound
            return job_to_envelope(job)


def job_to_envelope(job: _Job) -> JobEnvelope:
    """종결 여부에 따라 `poll_after_ms`를 정해 `JobEnvelope`를 만든다(AC-06)."""
    terminal = job.status in (JobStatus.COMPLETED, JobStatus.FAILED)
    return JobEnvelope(
        job_id=job.job_id,
        session_id=job.session_id,
        job_status=job.status,
        attempt=job.attempt,
        max_attempts=job.max_attempts,
        poll_after_ms=None if terminal else PROGRESS_POLL_AFTER_MS,
        result=job.result,
        failure=None,
    )


_store: InMemorySessionStore | None = None


def get_session_store() -> InMemorySessionStore:
    """프로세스 단위 저장소를 돌려준다.

    테스트는 `reset_session_store()`로 비운다. 실제 구현에서는 이 자리가 Neon
    PostgreSQL connection pool이 된다.
    """
    global _store
    if _store is None:
        _store = InMemorySessionStore()
    return _store


def reset_session_store() -> None:
    """테스트 간 상태를 초기화한다."""
    global _store
    _store = None
