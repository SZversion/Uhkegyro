# 실패 상태 정의 — 강사님 회의(2026-09-22) 접수·확정

**팀**: 4조 (UH케그려)
**작성일**: 2026-09-22
**작성자**: 윤태현 (YTH)
**상태**: 강사님 회의(2026-09-22) 반영 · **비동기 확정** · PR #12(`api-contract`) 승인 예정 반영
**근거 문서**:
- 머지됨 (PR #7): `docs/specs/illustration-reference-failure-state-contract.md` — 작성 오세창
- 승인 예정 (PR #12): `docs/specs/api-contract.md` — 작성 김호섭, 브랜치 `KHS03/docs/api-contract`

---

## 1. 한눈에 보기

| 구분 | 현재 상태 | 변경 예정 (PR #12 승인 시) |
| --- | --- | --- |
| 전송 방식 | 동기 `POST /api/agent` (200/422/503) | **비동기 `202` + `GET /api/jobs/{job_id}` 폴링** |
| 사용자 상태 | `status` 6종 (body 최상위) | `job_status` + `result.agent_status` 2층으로 이동 |
| 역할별 결과 | `search_plan` (링크 계획) | `roles[].search_status` (`active/no_results/search_error`) |
| 세션 인증 | 익명 UUID 헤더 | 서버 발급 세션 + **HttpOnly 쿠키 소유권 검증** |
| 실패 코드 | `FailureReasonCode` enum | `FailureReasonCode` + `failure_code`(`JOB_TIMEOUT` 등) |

> 원칙: **사용자 의미 상태 6종은 오세창 머지 스펙을 유지**하고, PR #12가 그 상태를 비동기 작업 봉투(job) 안으로 옮긴다. 실패 판정은 항상 한계(limitation) 사실에 근거하며, 서버가 실패를 지어내지 않는다.

---

## 2. 실패 상태의 3축 (통합 기준)

PR #12 이후 축이 겹치지 않도록 다음 세 축으로 분리한다.

| 축 | 의미 | 값 |
| --- | --- | --- |
| ① 작업 수명주기 `job_status` | 백엔드 내부 처리 진행 상태 | `queued → running → validating → searching → rendering → completed \| failed` |
| ② 사용자 의미 상태 (6종) | 사용자에게 보이는 최종 상태 | `success` / `needs_clarification` / `out_of_scope` / `unsafe_input` / `partial_result` / `service_unavailable` |
| ③ 역할별 결과 `search_status` | 역할 단위 검색 결과 | `active` / `no_results` / `search_error` |

- `completed`와 `failed`만 종결 상태다.
- `agent_status` 표현은 PR #12 초안 명칭이며, 확정 시 동기 스펙의 `status` 6종과 정합화한다.

---

## 3. 사용자 의미 상태 6종 (오세창 머지 스펙 유지)

| 상태 | HTTP | 대표 `reason_codes` | `result` | UI 행동 | 외부 도구 |
| --- | --- | --- | --- | --- | --- |
| `success` | 200 | 없음 또는 `GETTY_AAT_TERM_NOT_FOUND` | 필수 | 용어 설명·한계·Pinterest 외부 링크 | 필요한 용어 조회만 |
| `needs_clarification` | 200 | `ABSTRACT_INTENT_ONLY`, `INSUFFICIENT_BODY_POSE_VIEW_DETAIL`, `CONFLICTING_CONSTRAINTS` | null | 질문 한 개만 표시 | 호출 안 함 |
| `out_of_scope` | 200 | `IMAGE_GENERATION_REQUEST`, `IMAGE_ANALYSIS_REQUEST`, `STYLE_REPLICATION_REQUEST`, `PIN_COLLECTION_REQUEST`, `UNSUPPORTED_SUBJECT` | null | 거절 이유 + 텍스트 범위 안내 | 호출 안 함 |
| `unsafe_input` | 200 | `PROMPT_INJECTION_ATTEMPT`, `SECRET_EXTRACTION_ATTEMPT`, `HARMFUL_OR_ILLICIT_REQUEST` | null | 안전 범위 안내 (원문 반복 금지) | 호출 안 함 |
| `partial_result` | 200 | `GETTY_AAT_UNAVAILABLE`, `TEAM_TERM_CARD_UNAVAILABLE`, `STATIC_CARD_STORE_UNAVAILABLE`, `LLM_FALLBACK_USED`, `PINTEREST_RESULTS_UNAVAILABLE` | 필수 | 사용 가능 결과 + 빠진 부분·원인 표시 | 폴백 경로만 |
| `service_unavailable` | 503 | `TEAM_TERM_CARD_UNAVAILABLE`, `STATIC_CARD_STORE_UNAVAILABLE`, `REFERENCE_PLAN_UNAVAILABLE`, `LLM_RESPONSE_UNAVAILABLE` | null | 결과·링크 지어내지 않고 재시도 안내 | 중단 |

- 형식 오류(빈 입력·500자 초과)는 `422` — 위 6종 enum에 포함하지 않고 LLM·도구를 호출하지 않는다.
- `GETTY_AAT_TERM_NOT_FOUND`는 장애가 아니라 정상 조회 결과(후보 없음)이며, 승인 카드가 있으면 `success`로 유지한다.

---

## 4. PR #12(비동기) 추가 계약

### 4-1. 엔드포인트 4종

| 엔드포인트 | 메서드 | 성공 응답 | 용도 |
| --- | --- | --- | --- |
| `/health` | GET | `200 {"status":"ok"}` | 상태 점검 (쿠키 불필요) |
| `/api/sessions` | POST | `201` + `Set-Cookie` + `{session_id, expires_at}` | 새 대화 시작 |
| `/api/sessions/{id}/messages` | POST | `202 {message_id, job_id, job_status}` | Agent 작업 생성 |
| `/api/jobs/{id}` | GET | `200` (폴링, 본문에 상태 포함) | 작업 조회 |
| `/api/jobs/{id}/retry` | POST | `202 {job_id, retry_of_job_id, job_status}` | 실패 작업 명시적 재시도 |

### 4-2. 오류 상태 코드 (HTTP)

| HTTP | 코드 | 조건 |
| --- | --- | --- |
| `401` | `SESSION_REQUIRED` | 쿠키 없음·만료 |
| `404` | `SESSION_NOT_FOUND` / `JOB_NOT_FOUND` | 소유하지 않은/존재하지 않는 세션·작업 (타인 접근도 `404`, 존재 여부 미노출) |
| `409` | `JOB_NOT_RETRYABLE` | 재시도할 수 없는 작업에 retry 요청 |
| `422` | `INVALID_REQUEST_TEXT` | 공백만 or 1~500자 제약 위반 |

### 4-3. 실패 코드 3종 (`failure_code` — job 실패 시)

| 코드 | 의미 |
| --- | --- |
| `JOB_TIMEOUT` | 작업 시간 초과 |
| `INSTANCE_INTERRUPTED` | Cloud Run 인스턴스 종료·중단 |
| `PROCESSING_ERROR` | 처리 중 일반 예외 |

> 내부 오류 원문·비밀값은 `failure_code`·`user_message`에 포함하지 않는다.

### 4-4. 역할별 결과 상태

- `search_status`: `active` / `no_results` / `search_error`
- Pin `render_status`: `active` / `deleted` (삭제됨 Pin은 URL 이력만 반환, `embedPin` 미생성)
- 역할별 `pins` 최대 8개

### 4-5. 세션 보안 계약

- 쿠키: `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`
- `session_id`·`job_id`는 서버 생성 불투명 UUID — 클라이언트가 만들지 않음
- 클라이언트가 전송할 수 있는 값은 `request_text`뿐 (`role`, `term_id`, 검색어, Pin URL 결정·전송 금지)
- 세션 소유권 검증 실패 시 쿠키 없음 → 새 세션 생성 흐름으로 유도

---

## 5. 실패 시나리오별 최종 상태 (통합)

| 시나리오 | 뒤처리 순서 | `job_status` | 최종 사용자 상태 | HTTP | 예시 `reason_codes` | retryable |
| --- | --- | --- | --- | --- | --- | --- |
| 형식 오류 (빈 입력·500자 초과) | 요청 검증에서 차단 | 생성 안 함 | (미생성) | 422 | `INVALID_REQUEST_TEXT` | — |
| 안전 거부 입력 | 사전 안전 검사에서 차단 | `completed` | `unsafe_input` | 200 | `PROMPT_INJECTION_ATTEMPT` | false |
| 단서 부족·모호 | 기본 LLM 해석 후 | `completed` | `needs_clarification` | 200 | `ABSTRACT_INTENT_ONLY` | false |
| MVP 범위 밖 | 기본 LLM 해석 후 | `completed` | `out_of_scope` | 200 | `STYLE_REPLICATION_REQUEST` | false |
| Getty 장애 + 승인 카드 존재 | Getty 폴백 | `completed` | `partial_result` | 200 | `GETTY_AAT_UNAVAILABLE` | false |
| 카드·저장소 불능 + 검증된 임시 후보 | 3rd LLM 폴백 성공 | `completed` | `partial_result` | 200 | `TEAM_TERM_CARD_UNAVAILABLE`, `LLM_FALLBACK_USED` | false |
| 카드·저장소 불능 + 후보 없음 | 3rd LLM 실패(`not_resolved`) | `failed` | `service_unavailable` | 503 | `REFERENCE_PLAN_UNAVAILABLE` | true |
| LLM 구조화 1회 재시도 실패 | — | `failed` | `service_unavailable` | 503 | `LLM_RESPONSE_UNAVAILABLE` | true |
| Cloud Run 중단·timeout·예외 | 작업 종결 | `failed` | `service_unavailable` | 503 | `failure_code`(`JOB_TIMEOUT` 등) | 원인별 |

- 3축 조합 규칙: `search_status=no_results`·`search_error`는 `completed` + 의미 상태 `success`/`partial_result` 영역에서 발생. `failed`는 작업 단위 최종 실패다.

---

## 6. 재시도 정책

### 6-1. LLM·도구 재시도 (오세창 머지 스펙 §8)

| 실패 유형 | 추가 시도 | 백오프 | 최종 상태 |
| --- | --- | --- | --- |
| 요청 Pydantic 위반 | 0회 | 0ms | HTTP 422 |
| 안전 거부 입력 | 0회 | 0ms | `unsafe_input` |
| LLM 구조화 출력/Pydantic 위반 | 1회 | 0ms | 질문 가능 시 `needs_clarification`, 아니면 `service_unavailable` |
| 팀 카드 없음·저장소 장애 | 0회 (3rd LLM 폴백 1회 호출) | 0ms | 후보 검증 시 `partial_result`, 아니면 `service_unavailable` |
| Getty timeout | 1회 | 300ms | 카드 있으면 `partial_result`, 없으면 `service_unavailable` |
| Getty 5xx·비정상 JSON | 1회 | 500ms | 동일 |
| Getty 429 | 0회 (즉시 카드 폴백) | 0ms | 동일 |
| Pinterest Partner Search 장애(향후) | 0회 (링크 폴백) | 0ms | `partial_result` |

- SDK 기본 재시도와 중복되지 않도록 `max_retries=0` 명시.

### 6-2. 작업 재시도 (PR #12)

- 자동 재시도 금지. 사용자가 명시적으로 `POST /api/jobs/{id}/retry` 요청할 때만 새 작업 생성.
- `max_attempts=3`. timeout·인스턴스 중단 등 재시도 가능한 실패는 기본 `retryable=true`, 3회 도달 시 `retryable=false`로 종결.
- 재시도 시 원래 작업의 입력·실패 원인(`retry_of_job_id`)을 연결해 기록.

---

## 7. LLM 출력 계약 (상태 결정 원칙)

기본 LLM은 ①허용 `term_id`만 선택하고, ②최종 상태·`reason_codes`·역할 순서·Pinterest URL을 만들지 않는다. 상태 결정과 URL 생성을 담당하는 건 결정론 코드(서버)다.

**InterpretationOutput** (`llm.py`의 기본 LLM 출력):
```
interpretation_state: resolved | needs_clarification | out_of_scope | unsafe_input
selections: [{role: body|pose|view|perspective|layout, term_id: 활성만, evidence, confidence}]
unresolved_constraints: [] / clarifying_question / out_of_scope_code / safety_reason_code
```

**FallbackTermOutput** (3rd LLM 폴백 — 카드·Getty 모두 불가일 때만):
```
fallback_state: candidate | not_resolved
role / term_id(항상 null) / term_label_ko / term_label_en / search_token(1~5단어) / evidence
```
- 검증된 임시 후보 → `source_type=llm_fallback`, `temporary=true`, `requires_human_review=true`, `source_label_ko="임시 용어 후보"`, `source_notice_ko="검증된 팀 카드 또는 Getty 출처가 아닌 임시 후보입니다."` → `partial_result`
- 임시 후보는 카드·Skill·DB에 자동 저장하지 않는다.

**Pydantic 모델**: `InterpretationOutput`, `FallbackTermOutput`, `AgentResponseStatus`, `FailureReasonCode`, `AgentResponse`
- `success`·`partial_result` → `result` 필수 / 나머지 → `result=null`
- `service_unavailable`만 `retryable=true` 허용 (`retry_after_ms` 기본 1000, 나머지 null)

---

## 8. 회의 확정 사항

1. **동기 vs 비동기**: **비동기 확정** (PR #12 방향) → 머지된 `frontend-api-contract.md`·`failure-state-contract.md` 정합화(동기 전제 문구 수정)
2. **envelope/payload 위치**: `agent_status`를 `result` 안으로 (`result.agent_status`) — 완료 payload에 위치, 미완료는 `result=null`
3. **`reason_codes` 위치**: `result` 내부
4. **`failure_code`별 `retryable` 매핑 갱신**: `JOB_TIMEOUT`·`INSTANCE_INTERRUPTED`·`PROCESSING_ERROR` 각각 true/false (안건 ①과 연동)
5. **`unsafe_input`/`out_of_scope` 시점**: 작업 완료 후 폴링 결과 200으로 표시 (형식 오류만 422)

---

## 9. Next Task

1. 실패 상태 3축 + 스키마 표 1장을 `api-contract.md` 확정 안으로 정리 → PR #12 머지 반영
2. `frontend-api-contract.md`·`failure-state-contract.md`를 비동기 모델로 정합화 (PR)
3. `backend/services/llm.py` 구현: `InterpretationOutput`/`FallbackTermOutput` + 재시도/폴백 + Langfuse (`uhkegryo-interpreter-v1`)
4. 결정론 코드: 카드 resolver + 역할 순서 + URL builder + `search_status` 반영
5. 평가셋 30건 반영: 정상·경계·실패 유도 케이스 포함 (9/23 마일스톤)