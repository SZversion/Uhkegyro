# Agent 공개 API 계약 초안 — 보류

> 이 파일은 API 명세서가 아니다. 공개 API 경로·필드·상태·인증 계약은 아직 작성되지 않았으며, 구현자는 이 문서의 예시를 사용하면 안 된다. 제품·설계 기준은 `docs/PRD.md`와 `docs/SDD.md`이고, 별도 API 명세서가 승인될 때까지 해당 문서의 “API 미정” 원칙을 따른다. 아래 내용은 논의 중인 참고안으로만 보존한다.

## Why

- **페르소나**: 자연어로 캐릭터 레퍼런스를 찾고, 같은 대화 안에서 결과를 유지하거나 실패한 요청을 다시 시도하려는 일러스트 초보자.
- **상황**: 브라우저는 세션을 시작하고 메시지를 보내며, 백엔드는 장시간 실행될 수 있는 해석·검색 작업을 비동기로 처리한다.
- **문제**: 세션 소유권, 작업 진행 상태, 실패·재시도, 역할별 Pin 결과의 공개 계약이 없으면 프론트와 백엔드가 서로 다른 상태 전이와 인증 방식을 구현할 수 있다.
- **측정 지표**: 정상·경계·실패 유도 요청을 포함한 계약 평가 30건에서 HTTP 상태, 작업 상태, 응답 스키마 및 세션 소유권 검증 통과율 100%.

## Goal

- 서버가 발급한 `HttpOnly` 쿠키로 세션 소유권을 검증하고, 한 세션에 대화·작업·검색 결과를 누적한다.
- 메시지 제출은 비동기 작업을 만들고, 브라우저는 작업 조회로 최종 결과 또는 실패·재시도 가능 여부를 확인한다.
- 역할별로 최대 8개의 Pin URL과 렌더링 상태를 반환하여 프론트가 `pinit.js` `embedPin`으로 표시할 수 있게 한다.

**성공 기준**

- 브라우저는 `role`, `term_id`, 검색어, Pin URL, 인증 토큰을 결정하거나 전송하지 않는다.
- 다른 세션의 메시지·작업·결과는 유효한 쿠키가 있어도 조회·변경할 수 없다.
- Cloud Run 중단·timeout·처리 예외는 작업을 `failed`로 종결하고, 사용자에게 재시도 가능 여부를 제공한다.

**Out of Scope**

- MCP 도구 이름·입력·출력·전송 방식과 Pinterest 검색 제공자 계약. 이는 별도 MCP Spec에서 확정한다.
- 이미지 바이너리·썸네일 저장, Pinterest Pin 재게시, 이미지 생성·편집·업로드 이미지 분석.
- 무제한 재시도. 재시도 가능한 실패는 최대 3회(`max_attempts=3`)까지만 처리한다.

## What

### Happy Path

1. 브라우저가 `POST /api/sessions`를 호출한다.
2. 백엔드는 새 `session_id`와 불투명 세션 토큰을 만들고, 토큰을 `HttpOnly` 쿠키로 설정한다.
3. 브라우저가 `POST /api/sessions/{session_id}/messages`에 1~500자 `request_text`를 보낸다.
4. 백엔드는 쿠키 소유권을 확인하고 메시지와 `job_id`를 저장한 뒤 `202 Accepted`를 반환한다.
5. 브라우저가 `GET /api/jobs/{job_id}`를 polling한다.
6. 완료된 작업은 활성 카드 기반의 역할별 결과와 최대 8개 Pin URL을 반환한다. 프론트는 URL만 `pinit.js` `embedPin`으로 렌더링한다.

### Edge Cases

| 상황 | 처리 |
| --- | --- |
| 쿠키가 없거나 만료됨 | `401`과 `SESSION_REQUIRED`; 브라우저는 새 세션 생성 흐름으로 이동 |
| 다른 세션의 `session_id` 또는 `job_id` 접근 | 존재 여부를 노출하지 않는 `404` 반환 |
| 빈 입력 또는 500자 초과 | `422`; LLM·MCP·검색을 호출하지 않음 |
| 카드로 해석할 단서가 부족함 | 작업 결과에 `agent_status=needs_clarification`과 질문 하나를 담음. 구체 응답 형식은 향후 API 명세서에서 확정 |
| 역할별 검색 결과가 없음 | 작업 `completed`; 해당 역할 `no_results`와 `검색 결과가 없습니다` 반환 |
| Pin 삭제 확인 | URL 이력은 저장하고 `deleted`; 렌더링 대상에서는 제외 |
| 검색 시스템 오류 | 작업 `completed`; 해당 역할 `search_error`와 재시도 안내 반환 |
| Cloud Run 중단·timeout·처리 예외 | 작업 `failed`; `retryable=true`이면 사용자가 재시도 가능 |

## How

### 공통 규칙

- 모든 `/api/*` 경로는 서버가 설정한 세션 쿠키를 검증한다. 운영 쿠키는 `HttpOnly`, `Secure=true`, `SameSite=Lax`, `Path=/` 속성을 가진다. localhost HTTP 개발에서는 `Secure=false`를 사용하고 localhost origin만 CORS에 허용한다.
- `session_id`와 `job_id`는 서버가 생성한 불투명 UUID다. 클라이언트는 새 값을 만들지 않는다.
- `GET /health`를 제외한 요청·응답은 JSON UTF-8을 사용한다.
- 공개 요청 본문에서 허용하는 사용자 결정 값은 `request_text`뿐이다. 역할·용어·검색어·Pin URL은 백엔드만 결정한다.
- 작업 상태는 `queued`, `running`, `validating`, `searching`, `rendering`, `completed`, `failed`다. `completed`와 `failed`만 종결 상태다.

### 1. `GET /health`

서비스 프로세스 상태만 점검하며 세션 쿠키가 필요 없다.

```http
GET /health
```

```json
{"status":"ok"}
```

응답은 `200 OK`만 사용한다.

### 2. `POST /api/sessions`

새 대화 시작 시 호출한다. 기존 세션을 재사용하거나 갱신하지 않는다.

```http
POST /api/sessions
```

성공 시 `201 Created`와 `Set-Cookie`를 반환한다.

```json
{
  "session_id": "7b3bf331-2b76-4c32-b60c-4b82a6fdd2c7",
  "expires_at": "2026-10-21T12:00:00Z"
}
```

### 3. `POST /api/sessions/{session_id}/messages`

세션 소유자가 새 Agent 작업을 생성한다.

```http
POST /api/sessions/{session_id}/messages
Content-Type: application/json

{"request_text":"한쪽 다리에 힘을 주고 아래에서 보이는 캐릭터"}
```

성공 시 `202 Accepted`:

```json
{
  "message_id": "a99c6ccb-e5e4-4a75-b131-999e1570a8e1",
  "job_id": "f6419067-7af2-457f-9b2f-8eea7bdce09a",
  "job_status": "queued"
}
```

오류:

| HTTP | 코드 | 조건 |
| --- | --- | --- |
| `401` | `SESSION_REQUIRED` | 쿠키 없음·만료 |
| `404` | `SESSION_NOT_FOUND` | 소유하지 않은 세션 또는 존재하지 않는 세션 |
| `422` | `INVALID_REQUEST_TEXT` | 공백만 있거나 1~500자 제약 위반 |

### 4. `GET /api/jobs/{job_id}`

세션 소유자가 작업을 조회한다. polling 중에도 HTTP 응답은 `200 OK`이며, 실제 처리 실패는 본문의 `job_status=failed`로 표현한다.

```http
GET /api/jobs/{job_id}
```

진행 중 응답:

```json
{
  "job_id": "f6419067-7af2-457f-9b2f-8eea7bdce09a",
  "session_id": "7b3bf331-2b76-4c32-b60c-4b82a6fdd2c7",
  "job_status": "searching",
  "retryable": false,
  "result": null
}
```

완료 응답의 `result`:

```json
{
  "job_id": "f6419067-7af2-457f-9b2f-8eea7bdce09a",
  "session_id": "7b3bf331-2b76-4c32-b60c-4b82a6fdd2c7",
  "job_status": "completed",
  "retryable": false,
  "result": {
    "agent_status": "success",
    "reason_codes": [],
    "clarifying_question": null,
    "roles": [
      {
        "role": "pose",
        "term_id": "pose_contrapposto",
        "label_ko": "콘트라포스토",
        "feedback_ko": "한쪽 다리에 무게를 싣는 자세입니다.",
        "search_status": "active",
        "pins": [
          {"pin_url":"https://www.pinterest.com/pin/example/","render_status":"active"}
        ]
      }
    ]
  }
}
```

- `agent_status`는 `success`, `needs_clarification`, `partial_result`, `out_of_scope`, `unsafe_input`, `service_unavailable` 중 하나다. 별도 `needs_clarification` boolean 필드는 사용하지 않는다.
- `agent_status=needs_clarification`이면 `roles`는 빈 배열이고 `clarifying_question`은 하나의 문자열이어야 한다.
- 역할별 `pins`는 최대 8개다. Pin의 `render_status`는 `active` 또는 `deleted`다. 역할의 `search_status`는 `active`, `no_results`, `search_error` 중 하나다.
- `deleted` Pin은 URL 이력으로만 반환하고 프론트는 `embedPin`을 만들지 않는다. `no_results`와 `search_error`는 빈 `pins` 및 역할 상태·사용자 안내로 반환한다.
- `job_status=failed`는 envelope 상태이며 `result=null`, `failure_code`, `user_message`, `retryable`을 가진다. `agent_status`는 결과 payload에만 존재하고 작업 실패 envelope에는 존재하지 않는다.

실패 응답은 `job_status=failed`, `result=null`, `failure_code`, `user_message`, `retryable`을 포함한다. `failure_code`는 `JOB_TIMEOUT`, `INSTANCE_INTERRUPTED`, `PROCESSING_ERROR` 중 하나이며, 내부 오류 원문·비밀값은 포함하지 않는다.

실패 매핑 확정안:

| failure_code | retryable |
| --- | --- |
| `JOB_TIMEOUT` | `true` |
| `INSTANCE_INTERRUPTED` | `true` |
| `PROCESSING_ERROR` | `false` |

`attempt=3`에 도달하면 모든 failure code의 `retryable`을 `false`로 전환한다.

조회 오류는 `401 SESSION_REQUIRED` 또는 `404 JOB_NOT_FOUND`다. 소유하지 않은 작업도 `404`로 처리한다.

### 5. `POST /api/jobs/{job_id}/retry`

`failed`이고 `retryable=true`인 작업만 재시도한다. 재시도 가능한 실패는 기본 `retryable=true`이며 `attempt`가 3회에 도달하면 `retryable=false`로 종결한다. 백엔드는 원래 입력과 실패 원인을 연결한 새 메시지·새 작업을 만든다.

성공 시 `202 Accepted`:

```json
{
  "job_id": "new-job-id",
  "retry_of_job_id": "f6419067-7af2-457f-9b2f-8eea7bdce09a",
  "job_status": "queued"
}
```

`401 SESSION_REQUIRED`, `404 JOB_NOT_FOUND`(타인 작업 접근 포함), 또는 재시도할 수 없는 작업의 `409 JOB_NOT_RETRYABLE`을 반환한다.

### 내부 의존성 경계

백엔드는 카드 저장소와 향후 MCP 검색 도구를 호출할 수 있으나, 해당 도구의 경로·도구 이름·입출력 스키마는 이 공개 API 계약에 포함하지 않는다. 내부 도구 오류는 외부에 원문 오류나 비밀값을 노출하지 않고 역할별 `search_error` 또는 작업 `failed`로 변환한다.

### 저장과 보안

- 세션에는 토큰 해시, 생성·마지막 활동·만료 시각, 상태, 최근 대화 요약을 저장한다.
- 메시지에는 사용자 메시지, 구조화 JSON, 검증 결과, 모델명·프롬프트 버전, 생성 시각을 저장한다.
- 검색 결과에는 메시지·역할·`term_id`·Pin URL·`active|deleted|no_results|search_error` 상태·생성 시각을 저장한다.
- 세션·대화·구조화 결과·Pin URL은 1개월 보관하고 하루 한 번 만료 데이터를 삭제한다. 이미지 바이너리·썸네일·LLM 원문 응답은 저장하지 않는다.

## 향후 API 명세서에서 확정할 항목

- 공개 endpoint·request/response 필드·HTTP 상태·오류 코드
- polling 간격, 작업 상태 조회 종료 조건, timeout 기준
- 메시지·역할별 결과 pagination과 정렬 규칙
- 세션 조회·종료 메서드와 세션 목록 범위
- `agent_status`와 `job_status`의 envelope/payload 위치
- `failure_code`별 `retryable` 규칙과 `attempt`, `max_attempts` 계약

비동기 재시도 참고 정책은 `max_attempts=3`이다. timeout·인스턴스 중단 등 재시도 가능한 실패는 기본 `retryable=true`로 시작하고, 시도 횟수가 3회에 도달하면 `retryable=false`로 종결한다. `job_status=failed`인 envelope는 `result=null`과 `failure_code`, `user_message`, `retryable`을 가지며, `agent_status`는 결과 payload가 존재할 때만 사용한다.


