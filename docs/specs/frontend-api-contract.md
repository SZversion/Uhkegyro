# Illustration Reference 프론트-백엔드 연결 계약 (Frontend-API Contract)

## Why

- **사용자**: 자연어로 캐릭터 레퍼런스를 찾고, 같은 대화에서 결과를 유지하거나 실패한 요청을 직접 다시 시도하려는 일러스트 초보자.
- **상황**: 용어 해석·카드 검증·Pinterest 검색은 즉시 끝나지 않을 수 있다. 브라우저가 요청 연결을 계속 붙잡으면 timeout과 중단 상태를 구분하기 어렵다.
- **문제**: 세션 소유권, job 상태, polling 종료, 재시도 계약이 없으면 프론트와 백엔드가 서로 다른 결과 상태를 구현한다.
- **측정 지표**: 계약 평가 100건에서 endpoint·세션 소유권·job 상태 전이·응답 스키마 준수율 100%. 실제 측정값은 구현 후 `EVAL_REPORT.md`에 기록한다.

## Goal

- 서버 발급 `HttpOnly` 쿠키로 세션 소유권을 확인하고, 메시지 제출은 `202 Accepted`와 비동기 job으로 처리한다.
- 브라우저는 job의 실제 상태만 polling하여 종결 상태의 결과·실패·수동 재시도 가능 여부를 표시한다.
- 역할별 원격 썸네일은 현재 응답에서만 원본 Pin 링크로 표시하며, 이미지·썸네일 URL·Pin 메타데이터는 저장하거나 재게시하지 않는다.

## What

### Happy Path

1. 브라우저가 `POST /api/sessions`를 호출한다.
2. 서버가 `session_id`, 비식별 `anonymous_user_id`, 불투명 세션 토큰을 생성하고 토큰을 `HttpOnly` 쿠키로 설정한다.
3. 브라우저는 반환된 `session_id`를 현재 화면 상태에만 보관하고 `POST /api/sessions/{session_id}/messages`로 `request_text`를 보낸다.
4. 서버는 쿠키 소유권을 검증하고 message·job을 저장한 뒤 `202 Accepted`와 `job_id`를 반환한다.
5. 브라우저는 `GET /api/jobs/{job_id}`를 `poll_after_ms` 간격으로 조회한다.
6. `completed`면 결과를, `failed`면 실패 안내와 수동 재시도 동작을 표시한다.

### Edge Cases

| # | 상황 | 처리 방식 |
|---|---|---|
| EC-01 | 쿠키가 없거나 만료됨 | `401 SESSION_REQUIRED`; 새 세션 생성으로 이동 |
| EC-02 | 타인의 `session_id` 또는 `job_id` 조회 | 존재 여부를 노출하지 않는 `404` |
| EC-03 | 빈 입력 또는 500자 초과 | 메시지 생성 시 `422 INVALID_REQUEST_TEXT`; LLM·검색 미호출 |
| EC-04 | job이 `queued`~`rendering` | `result=null`; 실제 `job_status`와 `poll_after_ms`만 표시 |
| EC-05 | 용어 단서 부족 | job은 `completed`; `result.agent_status=needs_clarification`과 질문 하나 표시 |
| EC-06 | 역할별 검색 0건·삭제·검색 오류 | job은 `completed`; `partial_result`와 역할별 상태를 표시 |
| EC-07 | worker timeout·중단·처리 예외 | job은 `failed`; `failure_code`, `retryable`, 사용자 안내를 표시 |
| EC-08 | 네트워크 오류·JSON이 아닌 5xx | job 상태를 추측하지 않고 전송 실패 안내와 다시 조회/새 요청 동작을 표시 |

## How

### 1. Endpoint

| Endpoint | Method | 용도 | 성공 응답 |
|---|---|---|---|
| `/health` | `GET` | 프로세스 상태 확인 | `200 {"status":"ok"}` |
| `/api/sessions` | `POST` | 새 서버 세션 발급 | `201` + `Set-Cookie` |
| `/api/sessions/{session_id}/messages` | `POST` | 메시지와 비동기 job 생성 | `202` |
| `/api/jobs/{job_id}` | `GET` | 소유 job 상태·결과 조회 | `200` |
| `/api/jobs/{job_id}/retry` | `POST` | 사용자가 실패 job을 수동 재시도 | `202` |

`GET /health` 외 모든 `/api/*` endpoint는 세션 쿠키를 검증한다. 브라우저는 `role`, `term_id`, 검색어, Pin URL, 인증 토큰, `anonymous_user_id`를 만들거나 전송하지 않는다.

### 2. 세션과 메시지 생성

`POST /api/sessions`는 요청 본문 없이 새 세션을 만든다. 서버는 세션 토큰을 `HttpOnly`, `SameSite=Lax`, `Path=/` 쿠키로 설정하고, 배포 환경에서는 반드시 `Secure=true`를 사용한다. 로컬 HTTP 개발에서만 명시적 local 설정으로 `Secure=false`를 허용하며, 이 값은 배포 환경에 사용하지 않는다. DB에는 토큰 원문이 아닌 해시만 저장한다. `anonymous_user_id`는 서버가 생성해 세션과 연결하고 로그·trace에는 해시만 기록한다.

```json
{
  "session_id": "server-issued-uuid",
  "expires_at": "2026-10-22T00:00:00Z"
}
```

`POST /api/sessions/{session_id}/messages`의 요청 본문은 `request_text`만 허용한다.

```json
{ "request_text": "한쪽 다리에 힘을 주고 아래에서 보이는 캐릭터" }
```

성공 시 HTTP `202`를 반환한다.

```json
{
  "message_id": "server-issued-uuid",
  "job_id": "server-issued-uuid",
  "job_status": "queued",
  "poll_after_ms": 1000
}
```

오류는 `401 SESSION_REQUIRED`, `404 SESSION_NOT_FOUND`(타인 세션 포함), `422 INVALID_REQUEST_TEXT`만 반환한다.

### 3. Job 조회와 결과

job 상태는 `queued`, `running`, `validating`, `searching`, `rendering`, `completed`, `failed`다. `completed`와 `failed`만 종결 상태다. 진행 상태에서는 브라우저가 `poll_after_ms=1000`으로 polling하며, 종결 상태에서는 polling을 멈춘다. UI는 job 상태 이외의 진행률이나 완료 예정 시간을 만들지 않는다.

```json
{
  "job_id": "server-issued-uuid",
  "session_id": "server-issued-uuid",
  "request_id": "opaque-request-id",
  "job_status": "searching",
  "attempt": 1,
  "max_attempts": 3,
  "poll_after_ms": 1000,
  "retryable": false,
  "result": null,
  "failure": null
}
```

`completed` 응답의 `result`는 [현행 비동기 실패 상태 계약](./illustration-reference-current-failure-state-contract.md)의 `AgentResult`다. 이 결과에는 역할별 최대 8개의 `{pin_url, thumbnail_url, status}`가 포함될 수 있다. `thumbnail_url`은 응답 전용 원격 표시 URL이고, UI는 이를 원본 `pin_url`의 클릭 대상으로 표시한다.

`failed` 응답은 `result=null`과 아래 `failure`를 가진다.

```json
{
  "failure": {
    "failure_code": "JOB_TIMEOUT | INSTANCE_INTERRUPTED | PROCESSING_ERROR",
    "user_message": "요청을 완료하지 못했습니다. 다시 시도해 주세요.",
    "retryable": true
  }
}
```

`GET /api/jobs/{job_id}`의 조회 오류는 `401 SESSION_REQUIRED` 또는 `404 JOB_NOT_FOUND`다. 타인 job도 `404`로 처리한다.

### 4. 수동 재시도

`POST /api/jobs/{job_id}/retry`는 `job_status=failed`이고 `retryable=true`인 경우만 새 message·새 job을 만든다. 자동 재시도는 하지 않는다. 전체 시도 한도는 원 작업을 포함해 `max_attempts=3`이며, 한도에 도달하면 `retryable=false`다. 성공 시 `202`와 새 `job_id`, `retry_of_job_id`, `job_status=queued`, `poll_after_ms=1000`을 반환한다. 오류는 `401 SESSION_REQUIRED`, `404 JOB_NOT_FOUND`, `409 JOB_NOT_RETRYABLE`이다.

### 5. 프론트 요청 규칙

모든 API 호출은 쿠키 전송을 위해 `credentials: "include"`를 사용한다. 브라우저는 새 화면 진입 시 세션을 만들고, 현재 화면의 `session_id`·`job_id`만 React state에 둔다. 세션 토큰·`anonymous_user_id`를 로컬스토리지·URL·로그에 저장하지 않는다.

```ts
const session = await fetch(apiBaseUrl + "/api/sessions", {
  method: "POST",
  credentials: "include",
}).then(readJsonOrThrow);

const accepted = await fetch(
  apiBaseUrl + `/api/sessions/${session.session_id}/messages`,
  {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ request_text: requestText }),
  },
).then(readJsonOrThrow);
```

`fetch` 자체가 실패하거나 JSON이 아닌 5xx를 받으면 `AgentResult`·`job_status`를 지어내지 않는다. 사용자는 같은 `job_id`를 다시 조회하거나 새 요청을 시작할 수 있다.

### 6. 환경·보안 경계

| 변수 | 접근 계층 | 용도 |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | 프론트 | 같은 origin API base URL; 프로덕션은 빈 상대 경로, 개발은 Vite proxy 경로 |
| `OPENAI_API_KEY`, `LANGFUSE_*`, `MCP_BASE_URL` | 백엔드·MCP | LLM·관측·MCP 연결 |

브라우저는 LLM SDK·MCP·비밀값을 직접 호출하지 않는다. `SameSite=Lax` 세션 쿠키를 사용하는 MVP는 UI와 API를 같은 origin으로 제공한다. 개발 환경은 Vite proxy로 같은 origin처럼 호출한다. Vercel UI에서 별도 Cloud Run API를 직접 호출하는 교차 사이트 cookie 배포는 MVP 범위 밖이며, 필요하면 이후 BFF 또는 별도 쿠키 정책을 설계한다. `Access-Control-Allow-Origin: *`와 credential 쿠키는 함께 사용하지 않는다.

## AC

**AC-01 · 서버 세션 발급**
- GIVEN: 신규 브라우저 화면 진입
- WHEN: `POST /api/sessions`를 호출한다.
- THEN: `201`, 서버 생성 `session_id`, 만료 시각, `HttpOnly` 세션 쿠키를 받는다.

**AC-02 · 비동기 job 생성**
- GIVEN: 유효한 세션과 1~500자 `request_text`
- WHEN: 메시지를 제출한다.
- THEN: 서버는 `202`와 `job_id`, `job_status=queued`, `poll_after_ms=1000`을 반환한다.

**AC-03 · 실제 상태만 polling**
- GIVEN: 종결되지 않은 소유 job
- WHEN: `GET /api/jobs/{job_id}`를 호출한다.
- THEN: 프론트는 반환된 `job_status`만 표시하고 `completed` 또는 `failed`에서 polling을 멈춘다.

**AC-04 · 실패와 수동 재시도**
- GIVEN: `failed`, `retryable=true`, `attempt < max_attempts`인 job
- WHEN: 사용자가 재시도를 누른다.
- THEN: `202`와 새 `job_id`를 받고 원 job을 자동 재시도하지 않는다.

**AC-05 · 소유권과 전송 실패**
- GIVEN: 쿠키가 없거나 타인의 session/job을 요청하거나 JSON 응답을 받지 못했다.
- WHEN: 프론트가 응답을 처리한다.
- THEN: 각각 새 세션, `404`, 일반 전송 실패 안내로 처리하고 다른 세션의 정보·가짜 job 결과를 표시하지 않는다.
