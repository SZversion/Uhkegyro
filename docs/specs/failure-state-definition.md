# 실패/상태 정의 — 강사님 회의(2026-09-22) 접수·확정 (PR #15 정합)

**팀**: 4조 (UH케그려)
**작성일**: 2026-09-22
**작성자**: 윤태현 (YTH)
**상태**: 강사님 회의(2026-09-22) 반영 · **비동기 확정** · PR #15(`OSC04/docs/self-managed-term-card-db`) 계약 정합 반영
**근거 문서**:
- 현행 계약(PR #15): `docs/specs/illustration-reference-current-failure-state-contract.md` — job 상태·사용자 의미 상태·failure enum·재시도
- 현행 계약(PR #15): `docs/specs/frontend-api-contract.md` — endpoint·세션·폴링·retry
- `docs/SDD.md` §3~5 — 자체 TERM_CARD DB·job 상태 전이·실패·폴백

---

## 1. 한눈에 보기

| 구분 | 현재 상태 (PR #15 정합) |
| --- | --- |
| 전송 방식 | **비동기 `202` + `GET /api/jobs/{job_id}` 폴링** (동기 `POST /api/agent` 제거) |
| 사용자 의미 상태 | `result.agent_status` **5종** — 완료 job payload에 위치, 미완료는 `result=null` |
| 작업 실패 | `failed` job + `failure`(`JobFailure`) — 동기 HTTP 오류 아님 |
| 역할별 결과 | `reference_plan.terms[].pins[].status` (`available/thumbnail_unavailable/deleted`) |
| 세션 인증 | 서버 발급 세션 + **HttpOnly 쿠키 소유권 검증** |
| 용어 원본 | **자체 TERM_CARD DB 단일** — Getty·외부 어휘 API·폴백 LLM 사용 안 함 |

> 원칙: **사용자 의미 상태 5종은 `AgentResult`로, 실행 실패는 `failed` job의 `failure`로 분리**한다. 실패 판정은 항상 한계(limitation) 사실에 근거하며, 서버가 실패를 지어내지 않는다.

---

## 2. 상태의 3축 (통합 기준)

PR #15 이후 축이 겹치지 않도록 다음 세 축으로 분리한다.

| 축 | 의미 | 값 |
| --- | --- | --- |
| ① 작업 수명주기 `job_status` | 백엔드 내부 처리 진행 상태 | `queued → running → validating → searching → rendering → completed \| failed` |
| ② 사용자 의미 상태 (5종) | 사용자에게 보이는 최종 상태 | `success` / `needs_clarification` / `out_of_scope` / `unsafe_input` / `partial_result` |
| ③ Pin 상태 `status` | 스토어 정책과 다른 Pin 단위 표시 상태 | `available` / `thumbnail_unavailable` / `deleted` |

- `completed`와 `failed`만 종결 상태다. 종결 뒤 상태는 바뀌지 않는다.
- 작업 실패(`failed`)는 동기 HTTP 오류가 아니라 polling에서 받는 job `failure`다. 브라우저는 `job_status`를 추측하지 않으며, worker 실패는 `failure_code`만으로 표시한다.

---

## 3. 사용자 의미 상태 5종 (PR #15 현행 계약)

| 상태 | `reference_plan` | 대표 `reason_codes` | 화면 행동 | 외부 도구 |
| --- | --- | --- | --- | --- |
| `success` | 필수 | 없음 | 용어 설명·확인 지점·검색 결과 표시 | 검증된 카드의 검색만 |
| `needs_clarification` | null | `ABSTRACT_INTENT_ONLY`, `INSUFFICIENT_VISUAL_EVIDENCE`, `CONFLICTING_CONSTRAINTS`, `TEAM_TERM_CARD_UNAVAILABLE` | 질문 한 개만 표시 | 호출 안 함 |
| `out_of_scope` | null | `IMAGE_GENERATION_REQUEST`, `IMAGE_ANALYSIS_REQUEST`, `STYLE_REPLICATION_REQUEST`, `PIN_COLLECTION_REQUEST`, `UNSUPPORTED_SUBJECT` | 텍스트 기반 해석 범위 안내 | 호출 안 함 |
| `unsafe_input` | null | `PROMPT_INJECTION_ATTEMPT`, `SECRET_EXTRACTION_ATTEMPT`, `HARMFUL_OR_ILLICIT_REQUEST` | 안전 범위 안내 (원문 반복 금지) | 호출 안 함 |
| `partial_result` | 필수 | `PIN_RESULTS_EMPTY`, `PIN_DELETED`, `PIN_THUMBNAIL_UNAVAILABLE`, `PIN_SEARCH_UNAVAILABLE`, `SEARCH_URL_BUILD_FAILED` | 사용 가능한 결과 + 빠진 이유 표시 | 검색 provider만 |

- 형식 오류(빈 입력·1~500자 위반)는 `422 INVALID_REQUEST_TEXT` — 위 5종 enum에 포함하지 않고 LLM·도구를 호출하지 않는다.

---

## 4. 비동기 작업 계약 (PR #15)

### 4-1. 엔드포인트 5종

| 엔드포인트 | 메서드 | 성공 응답 | 용도 |
| --- | --- | --- | --- |
| `/health` | GET | `200 {"status":"ok"}` | 상태 점검 (쿠키 불필요) |
| `/api/sessions` | POST | `201` + `Set-Cookie` + `{session_id, expires_at}` | 새 대화 시작 |
| `/api/sessions/{id}/messages` | POST | `202 {message_id, job_id, job_status, poll_after_ms}` | Agent 작업 생성 |
| `/api/jobs/{id}` | GET | `200` (폴링, 본문 `JobEnvelope`에 상태 포함) | 작업 조회 |
| `/api/jobs/{id}/retry` | POST | `202 {job_id, retry_of_job_id, job_status, poll_after_ms}` | 실패 작업 명시적 재시도 |

### 4-2. 오류 상태 코드 (HTTP)

| HTTP | 코드 | 조건 |
| --- | --- | --- |
| `401` | `SESSION_REQUIRED` | 쿠키 없음·만료 |
| `404` | `SESSION_NOT_FOUND` / `JOB_NOT_FOUND` | 소유하지 않은/존재하지 않는 세션·작업 (타인 접근도 `404`, 존재 여부 미노출) |
| `409` | `JOB_NOT_RETRYABLE` | 재시도할 수 없는 작업에 retry 요청 |
| `422` | `INVALID_REQUEST_TEXT` | 공백만 or 1~500자 제약 위반 |

### 4-3. 작업 실패 코드 3종 (`failure.failure_code` — job 실패 시)

| 코드 | 확정 조건 | `retryable` |
| --- | --- | --- |
| `JOB_TIMEOUT` | worker가 앱 관리 job 제한 시간을 넘기기 전에 중단 처리함 | `attempt < max_attempts`(3)일 때 `true` |
| `INSTANCE_INTERRUPTED` | worker lease 만료 → recovery가 실행 중단 job을 `failed`로 종결 | `attempt < max_attempts`(3)일 때 `true` |
| `PROCESSING_ERROR` | DB·LLM·Pydantic·resolver의 처리 예외를 안전하게 분류하지 못함 | `attempt < max_attempts`(3)일 때 `true` |

> 내부 오류 원문·비밀값은 `failure_code`·`failure.user_message`·`reason_codes`에 포함하지 않는다.

### 4-4. 역할별 결과 상태 (reference_plan)

- `reference_plan.terms[].pins[].status`: `available` / `thumbnail_unavailable` / `deleted`
- `thumbnail_url`은 응답 전용 원격 표시 URL — UI는 원본 `pin_url`을 클릭 대상으로 사용
- `deleted` Pin은 링크·썸네일 미표시, `thumbnail_unavailable`은 원본 링크만 표시
- 역할당 `pins` 최대 8개. 이미지 바이트·썸네일 URL·Pin 메타데이터는 저장·재게시 금지

### 4-5. 세션 보안 계약

- 쿠키: `HttpOnly`, `Secure`(배포), `SameSite=Lax`, `Path=/`
- `session_id`·`job_id`·`request_id`는 서버 생성 불투명 UUID — 클라이언트가 만들지 않음
- 클라이언트가 전송할 수 있는 값은 `request_text`뿐 (`role`, `term_id`, 검색어, Pin URL 결정·전송 금지)
- 세션 소유권 검증 실패 시 쿠키 없음 → 새 세션 생성 흐름으로 유도

---

## 5. 시나리오별 최종 상태 (통합)

| 시나리오 | 뒤처리 순서 | `job_status` | 최종 사용자 상태 | HTTP | 예시 `reason_codes` / `failure_code` | retryable |
| --- | --- | --- | --- | --- | --- | --- |
| 형식 오류 (빈 입력·500자 초과) | 요청 검증에서 차단 | 생성 안 함 | (미생성) | 422 | `INVALID_REQUEST_TEXT` | — |
| 안전 거부 입력 | 사전 안전 검사에서 차단 | `completed` | `unsafe_input` | 200 | `PROMPT_INJECTION_ATTEMPT` | false |
| 단서 부족·모호 | 기본 LLM 해석 후 | `completed` | `needs_clarification` | 200 | `ABSTRACT_INTENT_ONLY` | false |
| MVP 범위 밖 | 기본 LLM 해석 후 | `completed` | `out_of_scope` | 200 | `STYLE_REPLICATION_REQUEST` | false |
| 검색 0건·썸네일 부재·Pin 삭제 | provider 결과 반환 | `completed` | `partial_result` | 200 | `PIN_RESULTS_EMPTY` 등 | false |
| 자체 DB 미연결·미적재 | 실행 실패 | `failed` | — | 200 (failure) | `PROCESSING_ERROR` (운영 로그 `TERM_CARD_STORE_UNAVAILABLE`) | attempt<3 true |
| LLM 구조화 위반·5xx·429 | worker 종결 | `failed` | — | 200 (failure) | `PROCESSING_ERROR` | attempt<3 true |
| LLM timeout | worker 종결 | `failed` | — | 200 (failure) | `JOB_TIMEOUT` | attempt<3 true |
| Cloud Run 중단(lease 만료) | recovery 종결 | `failed` | — | 200 (failure) | `INSTANCE_INTERRUPTED` | attempt<3 true |

- 3축 조합 규칙: `completed` job 안에서만 의미 상태 5종이 결정된다. `failed`는 작업 단위 최종 실패다.
- Pinterest 검색 오류여도 유효 카드가 하나 이상 있으면 `partial_result`로 `completed`한다. 안전하게 조립할 수 없는 처리 실패만 `failed` + `PROCESSING_ERROR`.

---

## 6. 재시도 정책

### 6-1. 실행 재시도 (worker) — 자동 재시도 없음

| 실패 유형 | 자동 추가 시도 | 최종 처리 | 백오프 |
| --- | ---: | --- | --- |
| LLM 구조화 출력/Pydantic 위반 | 0회 | 현재 job을 `PROCESSING_ERROR`로 종결 | 없음 |
| LLM timeout | 0회 | 현재 job을 `JOB_TIMEOUT`로 종결 | 없음 |
| LLM 5xx·429·미완료 | 0회 | 현재 job을 `PROCESSING_ERROR`로 종결 | 없음 |
| 검색 provider 오류 | 0회 | 유효 카드 있으면 `partial_result`, 없으면 `PROCESSING_ERROR` | 없음 |
| worker lease 만료 | 0회 | recovery가 `INSTANCE_INTERRUPTED`로 종결 | 없음 |

- SDK 기본 재시도와 중복되지 않도록 `max_retries=0` 명시.

### 6-2. 작업 재시도 (사용자)

- 자동 재시도 금지. 사용자가 명시적으로 `POST /api/jobs/{id}/retry` 요청할 때만 새 job 생성.
- `max_attempts=3`. `attempt < max_attempts`이면 `retryable=true`, 3회 도달 시 `retryable=false`로 종결.
- 재시도 시 원래 작업의 입력·실패 원인(`retry_of_job_id`)을 연결해 기록.

---

## 7. LLM 출력 계약 (상태 결정 원칙)

기본 LLM은 ①허용 `term_id`만 선택하고, ②최종 상태·`reason_codes`·역할 순서·Pinterest URL을 만들지 않는다. 상태 결정과 URL 생성을 담당하는 건 결정론 코드(서버)다.

**InterpretationOutput** (`llm.py`의 기본 LLM 출력):
```
interpretation_state: resolved | needs_clarification | out_of_scope | unsafe_input
selections: [{role: body|pose|view|perspective|layout, term_id: 활성만, evidence, confidence}]
unresolved_constraints: [] / clarifying_question
```

**Pydantic 모델**: `JobEnvelope`, `AgentResult`, `ReferencePlan`, `TermResult`, `PinResult`, `InterpretationOutput`
- `success`·`partial_result` → `result.reference_plan` 필수 / 나머지 → `reference_plan=null`
- `failed` job → `result=null` + `failure`만

---

## 8. 회의 확정 사항

1. **동기 vs 비동기**: **비동기 확정** → 현행 `frontend-api-contract.md`·`current-failure-state-contract.md` 기준으로 정합
2. **envelope/payload 위치**: `agent_status`를 `result` 안으로 (`result.agent_status`) — 완료 payload에 위치, 미완료는 `result=null`
3. **`reason_codes` 위치**: `result` 내부
4. **`failure` 재시도 매핑**: `JOB_TIMEOUT`·`INSTANCE_INTERRUPTED`·`PROCESSING_ERROR` 모두 `attempt < max_attempts`(3)일 때 `retryable=true`
5. **`unsafe_input`/`out_of_scope` 시점**: 작업 완료 후 폴링 결과 200으로 표시 (형식 오류만 422)
6. **용어 원본**: 자체 TERM_CARD DB 단일 — Getty·외부 어휘 API·폴백 LLM 사용 안 함

---

## 9. Next Task

1. 실패 상태 3축 + 스키마 표를 현행 계약(`current-failure-state-contract`)에 정합화 (PR #15 병합 시점 이후)
2. `backend/services/` job executor·recovery·자체 TERM_CARD DB repository 구현 (SDD §3~5)
3. `backend/services/llm.py` 구현: `InterpretationOutput` + Langfuse (`uhkegryo-interpreter-v1`)
4. 결정론 코드: 카드 resolver + 역할 순서 + URL builder + Pin `status` 반영
5. 평가셋 30건 반영: 정상·경계·실패 유도 케이스 포함 (9/23 마일스톤)