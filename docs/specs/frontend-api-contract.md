# Illustration Reference 프론트-백엔드 연결 계약 (Frontend-API Contract)

## Why

- **페르소나**: 체형/소체, 포즈, 구도 전문 용어가 낯선 캐주얼 캐릭터 일러스트 초보자
- **상황**: 브라우저 UI는 사용자의 일상어 설명을 받아 `POST /api/agent`로 보내고, 응답의 용어 해석·한계·Pinterest 외부 탐색 링크를 카드로 표시한다.
- **문제**: 응답 스키마만 정해져 있고, 요청 형식·엔드포인트·환경변수·CORS·브라우저 식별자·UI 상태 매핑이 계약으로 고정되지 않아 백엔드와 프론트가 서로 다른 가정으로 구현할 위험이 있다.
- **측정 지표**: 요청·응답 필드가 이 계약과 100% 일치하는지 계약 평가 100건으로 확인한다. 브라우저에서 `POST /api/agent` 호출과 오류 상태 표시가 정상·실패 경로 모두 동작한다.

## Goal

- 백엔드 FastAPI와 프론트 Next.js 사이의 **연결 계약**(요청·응답 전송, 식별자, 환경변수, CORS, 오류 처리, UI 상태 매핑)을 고정한다.
- 응답 스키마의 상세 정의는 **`illustration-reference-current-failure-state-contract.md`를 참조**하여 중복하지 않는다. 이 문서는 전송·연결 계층만 다룬다.
- 성공 기준:
  - 브라우저는 `/mcp`, LLM SDK, 비밀값을 직접 호출하지 않는다.
  - 요청에 `request_text`, `anonymous_user_id`, `session_id`를 항상 포함한다.
  - 상태 코드·응답 본문 필드는 참조 스펙의 계약과 모순되지 않는다.
  - 오류 상태는 사용자에게 참조 스펙의 UI 행동 기준대로 표시한다.
- **Out of Scope**:
  - 응답 스키마(`status`, `reason_codes`, `result` 등)의 재정의 또는 세부 예시 작성 (참조 스펙이 담당)
  - 백엔드·프론트 실제 구현 코드, CORS 미들웨어 설정값 최종 결정
  - 배포 인프라 구축, 실제 도메인 URL 확보

## What

**Happy Path**
1. 사용자가 텍스트 입력창에 1~500자 설명을 입력하고 요청을 보낸다.
2. 프론트가 `anonymous_user_id`(로컬스토리지)와 `session_id`(탭당 신규)를 채워 `POST /api/agent`로 전송한다.
3. 백엔드가 해석 계획을 만들고 `AgentResponse`를 반환한다.
4. 프론트가 상태별로 성공 카드 또는 안내 화면을 표시한다.
5. 사용자는 역할별 용어 설명과 Pinterest 외부 탐색 링크로 레퍼런스를 확인한다.

**Edge Cases** (최소 5개 + 처리 방식)

| # | 상황 | 처리 방식 |
|---|---|---|
| EC-01 | 빈 입력 또는 500자 초과 전송 | 백엔드가 `422` 반환, 프론트는 입력 검증도 선행 수행 (1~500자 안내) |
| EC-02 | API 호출 중 네트워크 오류·브라우저 timeout·JSON이 아닌 5xx | `AgentResponse`로 해석하지 않고 일반 전송 실패 안내와 새 요청 버튼을 표시 |
| EC-03 | `status=needs_clarification` | 결과 카드를 숨기고 한 개의 `clarifying_question`을 질문 화면으로 표시 |
| EC-04 | `status=partial_result` | 사용 가능한 결과와 실패 원인(`reason_codes`)을 함께 표시 |
| EC-05 | `status=unsafe_input` / `out_of_scope` | 입력 원문을 되풀이하지 않고 안전한 범위 안내만 표시 |
| EC-06 | 로컬스토리지 비활성(시크릿 등) | `anonymous_user_id`를 탭 생존 UUID로 대체 (탭마다 추적 분리됨을 인지) |

## How

### 1. 엔드포인트

| 엔드포인트 | 메서드 | 용도 |
|---|---|---|
| `/health` | `GET` | 서비스 상태 확인 (응답 `{"status":"ok"}`) |
| `/api/agent` | `POST` | 사용자 레퍼런스 해석 요청 (메인 기능) |

### 2. 요청 계약

`POST /api/agent` 요청 본문은 다음 필드를 가진다. 모든 필드는 필수다.

```json
{
  "request_text": "한쪽 다리에 힘을 주고 아래에서 보이는 캐릭터",
  "anonymous_user_id": "anonymous-user-id",
  "session_id": "tab-session-id"
}
```

| 필드 | 타입 | 제약 | 의미 |
|---|---|---|---|
| `request_text` | string | 1~500자 | 사용자 일상어 설명 |
| `anonymous_user_id` | string (UUID) | 1회 발급, 재사용 | 브라우저 단위 식별자, 로컬스토리지 보관 |
| `session_id` | string (UUID) | 탭 단위 신규 발급 | 세션·추적 단위 식별자 |

참고: `anonymous_user_id`는 로컬스토리지 키 `illustration-reference-anonymous-user-id`에 보관한다. `session_id`는 탭을 열 때마다 `crypto.randomUUID()`로 새로 만든다. 둘 다 사용자 입력·개인 식별자가 아니다.

### 3. 응답 계약

응답 본문은 상태 코드와 함께 **`illustration-reference-current-failure-state-contract.md`의 `AgentResponse` 계약을 그대로 따르고, 이 문서는 재정의하지 않는다.**

- 정상 및 의미 상태: HTTP `200` (예: `success`, `needs_clarification`, `partial_result`)
- 재시도 필요: 유효한 `AgentResponse`를 포함한 HTTP `503` (`service_unavailable`만 해당)
- 형식 오류: HTTP `422` (빈 입력·500자 초과, `AgentResponse` 계약의 `status` enum에 없음)
- 응답 필드(`request_id`, `status`, `reason_codes`, `result`, `clarifying_question`, `user_message`, `next_action`, `retryable`, `retry_after_ms`)와 `result` 내부의 역할·Pin 구조는 전부 참조 스펙의 정의와 검증 규칙에 따른다.
- Cloud Run 종료·게이트웨이 timeout·브라우저 연결 단절의 HTTP/네트워크 실패는 `AgentResponse`가 아닐 수 있다. 이때는 JSON 파싱이나 `status` 분기를 시도하지 않고 전송 실패 UI를 표시한다.

### 4. 환경변수

`.env` / 배포 환경에 다음 변수를 쓴다. 브라우저 UI는 `NEXT_PUBLIC_API_BASE_URL`만 접근하고, 그 외 키는 서버 환경에만 둔다.

| 변수 | 위치 | 용도 |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | 프론트 (브라우저 노출 가능) | `POST /api/agent`, `GET /health` 호출 base URL |
| `OPENAI_API_KEY`, `LANGFUSE_*`, `MCP_BASE_URL` | 백엔드·MCP (비노출) | LLM·추적·MCP 연결 |

### 5. CORS·브라우저 접근 경계

- 브라우저 UI는 **`/mcp`를 직접 호출하지 않는다.** MCP는 백엔드가 서버 간(서버 대 서버)으로만 사용한다.
- 브라우저 UI는 **LLM SDK 또는 비밀값을 직접 호출하지 않는다.** 모든 LLM·검색은 `POST /api/agent`를 통해서만 이루어진다.
- 백엔드는 프론트 오리진만 허용하도록 CORS를 구성하고, 별도 인증 토큰은 현재 계약에 포함하지 않는다.

### 6. 프론트 호출 패턴 예시

```tsx
// frontend/lib/api.ts
function getAnonymousUserId(): string {
  const key = "illustration-reference-anonymous-user-id";
  const stored = window.localStorage.getItem(key);
  if (stored) return stored;
  const created = crypto.randomUUID();
  window.localStorage.setItem(key, created);
  return created;
}

export async function requestReferencePlan(requestText: string) {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  let response: Response;
  try {
    response = await fetch(
      apiBaseUrl + "/api/agent",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          request_text: requestText,
          anonymous_user_id: getAnonymousUserId(),
          session_id: crypto.randomUUID(),
        }),
      },
    );
  } catch {
    throw new TransportError(null);
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    if (response.status === 422) {
      throw new InputValidationError(body);
    }
    if (response.status === 503 && isAgentResponse(body)) {
      throw new AgentApiError(response.status, body);
    }
    // 422는 입력 형식 안내, JSON이 아닌 5xx는 전송 실패 안내
    throw new TransportError(response.status);
  }
  return response.json();
}
```

`isAgentResponse`는 참조 스펙의 필수 필드와 허용 enum을 확인하는 런타임 schema guard다. 응답 본문이 이를 통과하지 못하면 `status`·`reason_codes`를 읽지 않는다.

### 7. UI 상태 매핑

응답은 참조 스펙의 상태별 UI 행동을 그대로 따른다. 이 계약은 연결층에서 아래 요약만 유지한다.

| 상태 (HTTP) | 카드 표시 | 안내 형태 |
|---|---|---|
| `success` (200) | 용어 설명·한계·원격 썸네일·Pinterest 원본 링크 | 정상 결과 |
| `needs_clarification` (200) | 결과 카드 표시 안 함 | 질문 하나 표시 |
| `out_of_scope` (200) | 결과 카드 표시 안 함 | 지원 범위 안내 |
| `unsafe_input` (200) | 결과 카드 표시 안 함 | 안전 범위 안내 (원문 재출력 금지) |
| `partial_result` (200) | 가능한 용어·원격 썸네일·원본 링크 + 빠진 이유(`reason_codes`) | 부분 안내 |
| `service_unavailable` (503) | 결과·링크 미표시 | 재시도 안내 |
| 네트워크 오류·JSON이 아닌 5xx | 결과·링크 미표시 | 전송 실패 안내와 새 요청 버튼 |

- 결과 카드에는 검색 provider가 반환한 `thumbnail_url`을 원격 썸네일로만 표시하고, 클릭하면 `pin_url` 원본 Pin을 연다. `thumbnail_url=null`이면 원본 링크만 표시한다. 이미지 바이트·썸네일 URL·Pin 메타데이터는 브라우저 저장소·세션 DB에 저장하거나 재게시하지 않는다.
- `retryable=true`와 `retry_after_ms`를 받으면 해당 안내에 재시도 동작을 맞춘다.

## AC

**AC-01 · 요청 필드 항상 포함**
- GIVEN: 사용자가 설명을 입력하고 요청을 보낸다.
- WHEN: 프론트가 `POST /api/agent`를 호출한다.
- THEN: `request_text`, `anonymous_user_id`, `session_id` 세 필드를 모두 포함한다.
- AND THEN: `anonymous_user_id`는 로컬스토리지 키에서 읽거나 새로 발급해 저장하고, `session_id`는 탭마다 새로 발급한다.

**AC-02 · 형식 오류는 422로 차단**
- GIVEN: 요청 본문이 비었거나 `request_text`가 1~500자 제약을 위반한다.
- WHEN: 백엔드가 요청을 검증한다.
- THEN: HTTP `422`를 반환하고 `AgentResponse`의 `status` enum을 만들지 않는다.
- AND THEN: LLM·Pinterest·런타임 외부 어휘 도구를 호출하지 않으며, 프론트는 입력 형식 안내를 표시한다. 자체 TERM_CARD DB 조회는 브라우저가 아니라 서버 내부에서만 수행한다.

**AC-03 · 서비스 불가 시 503**
- GIVEN: 서버가 응답 작성 전에 앱 내부 서비스 오류 또는 앱 관리 처리 제한 시간 초과를 감지했다.
- WHEN: 백엔드가 최종 상태를 결정한다.
- THEN: HTTP `503`과 `status=service_unavailable`(참조 스펙 구조)을 반환한다.
- AND THEN: 프론트는 결과·링크를 지어내지 않고 재시도 안내를 표시한다.

**AC-04 · 전송 실패는 AgentResponse로 가정하지 않음**
- GIVEN: Cloud Run 종료·게이트웨이 timeout·브라우저 연결 단절로 JSON 응답을 받지 못했다.
- WHEN: 프론트가 응답을 처리한다.
- THEN: `AgentResponse.status`나 `reason_codes`를 지어내지 않고 전송 실패 안내와 새 요청 버튼을 표시한다.

**AC-05 · 브라우저는 비공개 계층 미접근**
- GIVEN: 요청을 실행한다.
- WHEN: MCP·LLM 비밀값이 필요한 처리가 발생한다.
- THEN: 브라우저는 `/mcp`나 LLM SDK를 직접 호출하지 않는다.
- AND THEN: `NEXT_PUBLIC_` 이외의 키는 브라우저 번들에 포함되지 않는다.

**AC-05 · 부분 결과는 상태 표시 유지**
- GIVEN: `status=partial_result`를 받는다.
- WHEN: 프론트가 응답을 렌더링한다.
- THEN: 사용 가능한 용어·근거·원격 썸네일·원본 Pin 링크와 함께 빠진 부분과 `reason_codes`를 표시한다.
- AND THEN: 실패 원인을 성공으로 속여 표시하지 않는다.

**AC-06 · 응답 스키마는 참조 스펙과 중복 정의하지 않는다**
- GIVEN: 이 문서와 참조 스펙을 대조한다.
- WHEN: 응답 필드 구조·검증 규칙을 확인한다.
- THEN: 이 문서는 전송·연결 계약만 정의하고 `AgentResponse` 세부는 `illustration-reference-current-failure-state-contract.md`를 참조한다.
- AND THEN: 두 문서의 상태·HTTP 코드·UI 행동이 모순되지 않는다.
