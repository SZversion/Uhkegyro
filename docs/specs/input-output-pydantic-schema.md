# 입출력 Pydantic 스키마 — 강사님 회의(2026-09-22) 접수·확정

**팀**: 4조 (UH케그려)
**작성일**: 2026-09-22
**작성자**: 윤태현 (YTH)
**상태**: 강사님 회의(2026-09-22) 반영 · **비동기(`202` + 폴링) 확정** · PR #12(`api-contract` `KHS03/docs/api-contract`) 승인 예정 반영
**근거 문서**:
- 머지 스펙: `docs/specs/illustration-reference-failure-state-contract.md` (작성 오세창, PR #7) — LLM 출력·enum·검증 규칙
- 승인 예정 초안: `docs/specs/api-contract.md` (작성 김호섭, PR #12) — 비동기 envelope·엔드포인트
- `docs/SDD.md` §3 — 내부 LLM 출력 규칙(`needs_clarification` boolean 표현)

---

## 1. 한눈에 보기

| 구분 | 모델 | 내용 |
| --- | --- | --- |
| 요청 | `AgentMessageRequest` | `request_text` 1~500자 단일 필드 |
| 응답 봉투 (공통) | `JobEnvelope` | `job_id` · `session_id` · `job_status` · `retryable` · `result` |
| 완료 결과 | `AgentResultPayload` | `agent_status`(6종) · `reason_codes` · `clarifying_question` · `roles[]` |
| 역할별 결과 | `RoleResult` | `role` · `term_id` · 카드 정보 · `search_status` · `pins[]`(최대 8) |
| LLM 기본 출력 | `InterpretationOutput` | 해석 상태 4종 + 활성 `term_id`만 선택 |
| LLM 폴백 출력 | `FallbackTermOutput` | 카드·Getty 모두 불가 시 임시 후보 |

> 브라우저가 전송하는 결정 값은 `request_text`뿐. `role`·`term_id`·검색어·Pin URL은 백엔드만 결정한다.

---

## 2. 요청 스키마

### 2-1. `POST /api/sessions` (본문 없음)

```json
// 201 Created + Set-Cookie (HttpOnly, Secure, SameSite=Lax, Path=/)
{ "session_id": "<uuid>", "expires_at": "2026-10-21T12:00:00Z" }
```

### 2-2. `POST /api/sessions/{session_id}/messages` — AgentMessageRequest

```json
{ "request_text": "한쪽 다리에 힘을 주고 아래에서 보이는 캐릭터" }
```

| 필드 | 타입 | 제약 |
| --- | --- | --- |
| `request_text` | string | 1~500자, 공백만·추가 필드 → `422 INVALID_REQUEST_TEXT` (LLM·도구 미호출) |

성공 응답 `202 Accepted`:

```json
{ "message_id": "<uuid>", "job_id": "<uuid>", "job_status": "queued" }
```

---

## 3. 응답 봉투 — JobEnvelope (공통)

`GET /api/jobs/{job_id}` 내내 같은 봉투. 상태는 HTTP가 아니라 **본문**으로만 표현한다. 조회는 항상 `200 OK`.

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `job_id` | uuid (서버 생성) | 작업 식별자 |
| `session_id` | uuid (서버 생성) | 소유 세션 |
| `job_status` | enum | `queued → running → validating → searching → rendering → completed \| failed` |
| `retryable` | bool | 재시도 가능 여부 (자동 재시도는 없음) |
| `result` | object \| null | 진행 중·실패 시 `null`, 완료 시 payload |
| `failure_code` | enum \| null | `failed`일 때만 `JOB_TIMEOUT` / `INSTANCE_INTERRUPTED` / `PROCESSING_ERROR` |
| `user_message` | string \| null | 사용자 안내 (내부 원문·비밀값 금지) |

- **진행 중**: `{job_status: "searching", retryable: false, result: null}`
- **실패**: `{job_status: "failed", result: null, failure_code, user_message, retryable}`
- **완료**: `result`에 `AgentResultPayload`

---

## 4. 완료 결과 — AgentResultPayload

```json
{
  "agent_status": "success",
  "reason_codes": [],
  "clarifying_question": null,
  "roles": [
    {
      "role": "pose",
      "term_id": "pose_contrapposto",
      "label_ko": "콘트라포스토",
      "feedback_ko": "한쪽 다리에 무게를 싣는 자세입니다.",
      "getty_aat": null,
      "search_status": "active",
      "pins": [
        { "pin_url": "https://www.pinterest.com/pin/<id>/", "render_status": "active" }
      ]
    }
  ]
}
```

### 4-1. 필드 정의

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `agent_status` | enum (6종) | `success` / `needs_clarification` / `out_of_scope` / `unsafe_input` / `partial_result` / `service_unavailable` — 머지 스펙 `status` 값 승계 |
| `reason_codes` | list[`FailureReasonCode`] | 허용 enum만, 실패 시 실제 도구 코드 ≥1 |
| `clarifying_question` | string \| null | `needs_clarification` 시 한 개 |
| `roles` | list[`RoleResult`] | 선택된 역할만, `body→pose→view→perspective→layout` 순서 |

### 4-2. RoleResult

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `role` | enum | `body` / `pose` / `view` / `perspective` / `layout` |
| `term_id` | string | 현재 활성 카드만 (`runtime_eligible=true` && `mvp_status=active_in_current_contract`) |
| `label_ko` | string | 초보자용 용어 이름 |
| `feedback_ko` | string | 카드 원문 피드백 |
| `getty_aat` | object \| null | `{uri, label, attribution}` (카드 기록값만, 외부 보강 금지) |
| `search_status` | enum | `active` / `no_results` / `search_error` |
| `pins` | list[`PinResult`] | 최대 8개, `no_results`·`search_error`면 빈 배열 |

### 4-3. PinResult

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `pin_url` | string | Pinterest 공식 Pin URL (이미지 저장 없음) |
| `render_status` | enum | `active` / `deleted` (삭제됨 → URL 이력만 반환, `embedPin` 미생성) |

---

## 5. LLM 출력 스키마

### 5-1. InterpretationOutput (기본 LLM — `llm.py`)

LLM이 최종 상태·`reason_codes`·역할 순서·Pinterest URL을 만들지 않는다.

```json
{
  "interpretation_state": "resolved",
  "selections": [
    { "role": "body", "term_id": "body_inverted_triangle",
      "evidence": ["어깨가 넓고 골반이 좁은 체형"], "confidence": "high" }
  ],
  "unresolved_constraints": [],
  "clarifying_question": null,
  "out_of_scope_code": null,
  "safety_reason_code": null
}
```

| 필드 | 타입 | 제약 |
| --- | --- | --- |
| `interpretation_state` | enum | `resolved` / `needs_clarification` / `out_of_scope` / `unsafe_input` |
| `selections` | list | 역할당 최대 1개, 활성 `term_id`만, 언급된 역할만 |
| `unresolved_constraints` | list | `{role, evidence[], reason_code}` |
| `clarifying_question` | string \| null | `needs_clarification` 시 한 개 |
| `out_of_scope_code` | enum \| null | `IMAGE_GENERATION_REQUEST` 등 허용 enum만 |
| `safety_reason_code` | enum \| null | `PROMPT_INJECTION_ATTEMPT` 등 |

### 5-2. FallbackTermOutput (3rd LLM 폴백 — 카드·Getty 모두 불가 시에만)

| 필드 | 타입 | 제약 |
| --- | --- | --- |
| `fallback_state` | enum | `candidate` / `not_resolved` |
| `role` | enum | 역할 축 |
| `term_id` | null | **항상 null** (활성 term ID를 만들지 않음) |
| `term_label_ko`/`term_label_en` | string \| null | `candidate`일 때만 |
| `search_token` | string \| null | 1~5개 짧은 표준 용어 (URL·문장 금지) |
| `plain_meaning_ko` | string \| null | 초보자용 뜻풀이 |
| `evidence` | list[string] | 사용자 문장의 짧은 근거 |
| `confidence` | "low" | 고정 |
| `limitation_codes` | list[`FailureReasonCode`] | `TEAM_TERM_CARD_UNAVAILABLE` 등 |

검증되면 서버가 `source_type=llm_fallback`, `temporary=true`, `requires_human_review=true`, `source_label_ko="임시 용어 후보"`를 붙이고 `partial_result`로 반환한다. 자동 저장 금지.

### 5-3. Enum 정의 (하나씩)

| Enum | 값 |
| --- | --- |
| `JobStatus` | `queued` `running` `validating` `searching` `rendering` `completed` `failed` |
| `FailureCode` | `JOB_TIMEOUT` `INSTANCE_INTERRUPTED` `PROCESSING_ERROR` |
| `AgentStatus` (승계 대상) | `success` `needs_clarification` `out_of_scope` `unsafe_input` `partial_result` `service_unavailable` |
| `SearchStatus` | `active` `no_results` `search_error` |
| `PinRenderStatus` | `active` `deleted` |
| `FailureReasonCode` (일부) | `ABSTRACT_INTENT_ONLY` `CONFLICTING_CONSTRAINTS` `IMAGE_GENERATION_REQUEST` `STYLE_REPLICATION_REQUEST` `PROMPT_INJECTION_ATTEMPT` `SECRET_EXTRACTION_ATTEMPT` `GETTY_AAT_UNAVAILABLE` `TEAM_TERM_CARD_UNAVAILABLE` `STATIC_CARD_STORE_UNAVAILABLE` `LLM_FALLBACK_USED` `REFERENCE_PLAN_UNAVAILABLE` `LLM_RESPONSE_UNAVAILABLE` `GETTY_AAT_TERM_NOT_FOUND` 등 |

---

## 6. 검증 규칙 (머지 스펙 §5 "구현 모델 경계" — 그대로 확정 가능)

- `success`·`partial_result` → 검증된 결과 존재. `partial_result`의 `reason_codes`에는 실제 실패 도구 코드 ≥1.
- `needs_clarification` → `clarifying_question` 한 개, 임의 링크·용어 생성 금지.
- `out_of_scope`·`unsafe_input` → 결과·링크 없음 (채택 전에는 도구 호출 금지).
- `service_unavailable`만 `retryable=true` 허용, `retry_after_ms` 기본 `1000`.
- 선택되지 않은 역할은 빈 링크·빈 카드·기본 검색어를 만들지 않는다.
- 브라우저는 `/mcp`·LLM SDK·비밀값을 직접 호출하지 않는다.

---

## 7. 회의 확정 사항 (스키마 작성 블로커 해소)

| # | 결정 포인트 | 결과 (2026-09-22 회의 기준) |
| --- | --- | --- |
| 1 | 사용자 상태 위치 | **`result.agent_status`** (PR #12 방향) — 완료 payload에 위치, 미완료는 `result=null`로 구분 |
| 2 | `reason_codes` 위치 | `result` 안 (상태와 함께 도착) |
| 3 | `needs_clarification` 표현 | **`agent_status` 6종 통합** — boolean과 이중 표현 금지 |
| 4 | `failure_code`별 `retryable` 매핑 | `JOB_TIMEOUT` true · `INSTANCE_INTERRUPTED` true · `PROCESSING_ERROR` false (제안) |
| 5 | `retry_after_ms` 유지 여부 | 폴링+retry 엔드포인트로 대체, 필드 제거 검토 |
| 6 | `user_message` 관리 | 동기 `AgentResponse.user_message` 승계 (오류·거절 문구 최소 기준표 활용) |

확정 후 `docs/specs/api-contract.md`의 Pydantic 필드 표 1장으로 고정하고, `failure-state-contract.md`의 동기 응답 예시를 envelope 내부로 정합화하면 스키마 작성이 완료된다.

---

## 8. Next Task

1. 위 확정 6건 → `api-contract.md`에 Pydantic 모델(`JobEnvelope`·`AgentResultPayload`·`RoleResult`·`AgentMessageRequest`·`InterpretationOutput`·`FallbackTermOutput`) 표 1장 작성
2. 머지 2개 스펙(`failure-state-contract`·`frontend-api-contract`) 비동기 정합화 PR
3. `backend/services/llm.py`에서 위 모델로 Pydantic 스키마 구현 + 재시도/폴백 + Langfuse (`uhkegryo-interpreter-v1`)
4. 평가셋 30건에 완료/진행/실패·6종 상태 응답 형식 검증 케이스 포함 (9/23 마일스톤)