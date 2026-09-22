# 입출력 Pydantic 스키마 — 강사님 회의(2026-09-22) 접수·확정 (PR #15 정합)

**팀**: 4조 (UH케그려)
**작성일**: 2026-09-22
**작성자**: 윤태현 (YTH)
**상태**: 강사님 회의(2026-09-22) 반영 · **비동기(`202` + 폴링) 확정** · PR #15(`OSC04/docs/self-managed-term-card-db`) 계약 정합 반영
**근거 문서**:
- `docs/PRD.md` — 제품 원칙·용어 단일 원본·상태 정의 기준
- 현행 계약(PR #15): `docs/specs/frontend-api-contract.md` — 비동기 endpoint·세션·폴링·재시도
- 현행 계약(PR #15): `docs/specs/illustration-reference-current-failure-state-contract.md` — `JobEnvelope`·`AgentResult`·`reference_plan`·`JobFailure`·LLM JSON 계약
- `docs/SDD.md` §3 — 자체 TERM_CARD DB·job executor·재시도 계약

---

## 0. Why · Goal · What · How · AC

### Why

- **페르소나**: 프런트(김호섭)·백엔드(윤태현)·MCP 구현자, 평가자
- **상황**: 요청·응답·실패·LLM 출력이 각자 다른 형식으로 구현되면 인증·검증·응답 형식이 제각각이 된다.
- **문제**: (1) HTTP 오류와 job 실패가 섞이면 프런트 폴링이 추측하게 됨 (2) 응답의 화면 설명 필드가 카드 JSON과 어긋나면 LLM이 없는 설명을 지어냄
- **측정 지표**: 계약 준수율(스키마 통과율), 평가셋 30건의 응답 형식 검증 통과

### Goal

- **해결 목표**: 모든 응답이 `JobEnvelope` 봉투를 통과하고, 카드 설명 필드가 74개 카드 실데이터(`active_term_feedback` 20개 / `source_answer_draft`+`look_for` 54개)와 정합된다.
- **성공 기준**: Pydantic 모델 하나로 프런트·백엔드·trace 검증이 동작하고, 없는 피드백을 생성하는 케이스가 평가셋에서 실패로 잡힌다.
- **Out of Scope**: 실제 저장소/DB 스키마(별도), MCP 도구 입출력 스키마(별도 MCP Spec)

### What

- 요청(`AgentMessageRequest`·세션), 응답 봉투(`JobEnvelope`), 완료 결과(`AgentResult`), `ReferencePlan`·`TermResult`·`PinResult`, 실패(`JobFailure`), LLM 출력(`InterpretationOutput`), enum·검증 규칙
- **카드 설명 필드**: 20개 피드백 카드는 index.json `active_term_feedback`의 7필드, 54개는 `source_answer_draft`·`look_for`만 — 카드 JSON에 공통 설명 필드가 없음

### How

- `backend/services/llm.py`가 이 모델을 import하고, resolver·응답 조립이 실데이터에서 필드를 조립한다.
- `illustration-reference-current-failure-state-contract.md`의 Pydantic 필드 표와 함께 정합화한다.

### AC

**AC-01 · 피드백 없는 카드의 설명 필드**
- GIVEN: `active_term_feedback`이 없는 54개 승인 카드가 선택됐을 때
- WHEN: `TermResult`를 조립하면
- THEN: `label_ko`·`label_en`·`source_answer_draft`·`look_for`만 채우고, 피드백 필드는 `null`이며 LLM이 쉬운 설명·질문을 만들지 않는다.

**AC-02 · 피드백 있는 카드의 설명 필드**
- GIVEN: `active_term_feedback`을 가진 20개 카드(예: `pose_contrapposto`)가 선택됐을 때
- WHEN: `TermResult`를 조립하면
- THEN: `plain_meaning_ko` 등 index.json과 동일 키의 초보자 피드백이 채워지고, `source_answer_draft`는 `null`이다.

**AC-03 · 상태별 스키마 규칙**
- GIVEN: 완료 job을 받을 때
- WHEN: 응답을 검증하면
- THEN: `success`·`partial_result`는 `reference_plan` 필수, 나머지 3종은 `reference_plan=null`, `failed` job은 `result=null`+`JobFailure`만 가진다.

---

## 1. 한눈에 보기

| 구분 | 모델 | 내용 |
| --- | --- | --- |
| 요청 | `AgentMessageRequest` | `request_text` 1~500자 단일 필드 |
| 응답 봉투 (공통) | `JobEnvelope` | `job_id` · `session_id` · `request_id` · `job_status` · `attempt` · `max_attempts` · `poll_after_ms` · `retryable` · `result` · `failure` |
| 완료 결과 | `AgentResult` | `agent_status`(5종) · `reason_codes` · `reference_plan` · `clarifying_question` · `user_message` |
| 레퍼런스 플랜 | `ReferencePlan` | `terms[]`(역할당 1) · `unresolved_roles[]` |
| 역할별 결과 | `TermResult` | `role` · `term_id` · 카드 설명(`feedback` or `source_answer_draft`) · `evidence` · `look_for` · `search_url` · `pins[]`(최대 8) |
| Pin 결과 | `PinResult` | `pin_url` · `thumbnail_url` · `status` |
| 실패 봉투 | `JobFailure` | `failure_code`(3종) · `user_message` · `retryable` |
| LLM 기본 출력 | `InterpretationOutput` | 해석 상태 4종 + 활성 `term_id` 후보만 선택 |

> 브라우저가 전송하는 결정 값은 `request_text`뿐. `role`·`term_id`·검색어·Pin URL은 백엔드만 결정한다. 자체 TERM_CARD DB만 용어 단일 원본이며, Getty·외부 어휘 API·폴백 LLM을 사용하지 않는다.

---

## 2. 요청 스키마

### 2-1. `POST /api/sessions` (본문 없음)

```json
// 201 Created + Set-Cookie (HttpOnly, Secure, SameSite=Lax, Path=/)
{ "session_id": "<uuid>", "expires_at": "2026-10-22T00:00:00Z" }
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
{ "message_id": "<uuid>", "job_id": "<uuid>", "job_status": "queued", "poll_after_ms": 1000 }
```

---

## 3. 응답 봉투 — JobEnvelope (공통)

`GET /api/jobs/{job_id}` 내내 같은 봉투. 상태는 HTTP가 아니라 **본문**으로만 표현한다. 조회는 항상 `200 OK`.

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `job_id` | uuid (서버 생성) | 작업 식별자 |
| `session_id` | uuid (서버 생성) | 소유 세션 |
| `request_id` | uuid (서버 생성) | trace 요청 식별자 |
| `job_status` | enum | `queued → running → validating → searching → rendering → completed \| failed` |
| `attempt` | int | 최초 1부터 증가 |
| `max_attempts` | int | `3` (전체 시도 한도) |
| `poll_after_ms` | int \| null | 진행 중 `1000`, 종결 `null` |
| `retryable` | bool | 재시도 가능 여부 (자동 재시도는 없음) |
| `result` | object \| null | 진행 중·실패 시 `null`, 완료 시 `AgentResult` |
| `failure` | object \| null | `failed`일 때만 `JobFailure` |

- **진행 중**: `{job_status: "searching", attempt: 1, max_attempts: 3, poll_after_ms: 1000, retryable: false, result: null, failure: null}`
- **실패**: `{job_status: "failed", result: null, failure: {failure_code, user_message, retryable}}`
- **완료**: `result`에 `AgentResult`

---

## 4. 완료 결과 — AgentResult

```json
{
  "agent_status": "success",
  "reason_codes": [],
  "reference_plan": {
    "terms": [
      {
        "role": "pose",
        "term_id": "pose_contrapposto",
        "label_ko": "콘트라포스토",
        "label_en": "contrapposto",
        "feedback": {
          "plain_meaning_ko": "한쪽 다리에 체중을 실어 골반과 어깨가 서로 반대 방향으로 기우는 서 있는 자세입니다.",
          "selection_reason_template_ko": "입력에 한쪽 다리 지지와 골반·어깨의 기울기가 함께 확인될 때 '콘트라포스토'로 해석합니다.",
          "pinterest_search_notice_ko": "Pinterest에서는 'contrapposto pose'라는 표준 검색 조각으로 찾습니다.",
          "reference_checkpoints_ko": [
            "체중을 받는 지지 다리",
            "골반과 어깨의 반대 기울기"
          ],
          "common_confusion_ko": [
            "몸을 단순히 S자로 휘는 것만으로는 콘트라포스토가 아닙니다."
          ],
          "clarifying_question_ko": "양발에 고르게 서 있나요, 아니면 한쪽 다리에 몸을 기대고 있나요?"
        },
        "evidence": ["한쪽 다리에 힘을 주는 그림"],
        "look_for": ["무게 중심이 실린 다리"],
        "search_url": "https://www.pinterest.com/search/pins/?q=...",
        "pins": [
          { "pin_url": "https://www.pinterest.com/pin/<id>/", "thumbnail_url": "https://provider-returned-thumbnail/...", "status": "available" }
        ]
      }
    ],
    "unresolved_roles": []
  },
  "clarifying_question": null,
  "user_message": "선택된 역할의 용어·확인 지점·검색 결과를 표시합니다."
}
```

> 위 예시의 `pose_contrapposto`는 20개 `active_term_feedback` 카드 중 하나이므로 초보자 피드백 필드를 가진다. 피드백이 없는 54개 승인 카드는 §4-3의 피드백 필드를 모두 `null`로 두고, `source_answer_draft`·`look_for`만 표시한다. 두 경우 모두 카드·index에 없는 쉬운 설명·질문을 LLM이 만들지 않는다.

### 4-1. 필드 정의

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `agent_status` | enum (5종) | `success` / `needs_clarification` / `out_of_scope` / `unsafe_input` / `partial_result` — PR #15 현행 계약 값 승계 |
| `reason_codes` | list[`FailureReasonCode`] | 허용 enum만, 실패 시 실제 도구 코드 ≥1 |
| `reference_plan` | object \| null | `success`·`partial_result`는 필수, `needs_clarification`·`out_of_scope`·`unsafe_input`는 `null` |
| `clarifying_question` | string \| null | `needs_clarification` 시 한 개 |
| `user_message` | string \| null | 사용자에게 보여 줄 짧은 안내 (오류 원문·비밀값 금지) |

### 4-2. ReferencePlan

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `terms` | list[`TermResult`] | `body→pose→view→perspective→layout` 순서, 역할당 최대 1개 검증된 활성 카드 |
| `unresolved_roles` | list[enum] | 결과를 만들지 못한 역할 (`body` / `pose` / `view` / `perspective` / `layout`) |

### 4-3. TermResult

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `role` | enum | `body` / `pose` / `view` / `perspective` / `layout` |
| `term_id` | string | 현재 활성 카드만 (`runtime_eligible=true` && `mvp_status=active_in_current_contract`) |
| `label_ko` / `label_en` | string | 팀 검수 용어 (모든 승인 카드 — 카드 JSON `label_ko`·`label_en`) |
| `feedback` | object \| null | **20개 `active_term_feedback` 카드 전용** — index.json의 `active_term_feedback.{term_id}`와 동일 키: `plain_meaning_ko`·`selection_reason_template_ko`·`pinterest_search_notice_ko`·`reference_checkpoints_ko`·`common_confusion_ko`·`clarifying_question_ko`. 피드백이 없는 54개 카드는 `null` |
| `source_answer_draft` | string \| null | **54개 승인 카드 전용** — 카드 JSON의 검수된 용어 설명. 20개 피드백 카드는 `null` |
| `evidence` | list[string] | 사용자 입력의 짧은 근거 |
| `look_for` | list[string] | 레퍼런스에서 확인할 지점 (카드 JSON `look_for`) |
| `search_url` | string | 자체 DB 카드의 `query_fragments`로 조립한 Pinterest 검색 URL |
| `pins` | list[`PinResult`] | 최대 8개, 0건·검색 오류 시 빈 배열 |

- 카드 설명 조립 규칙: **`reference_plan.terms[].feedback`와 `source_answer_draft` 중 하나만 채운다.** 20개 피드백 카드는 `feedback`을, 나머지 54개는 `source_answer_draft`를 표시하고, 어느 쪽도 없으면 화면 설명을 만들지 않는다 — LLM·결정론 코드 모두 지어내지 않는다 (`index.json` `feedback_fallback_rule` 준수).

### 4-4. PinResult

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `pin_url` | string | Pinterest 공식 Pin URL (이미지 저장 없음) |
| `thumbnail_url` | string \| null | 검색 provider가 반환한 응답 전용 원격 표시 URL. `null`이면 원본 링크만 표시 |
| `status` | enum | `available` / `thumbnail_unavailable` / `deleted` — `deleted`는 링크·썸네일 미표시 |

- 이미지 바이트·썸네일 URL·Pin 메타데이터는 DB·세션·로그에 저장하거나 재게시하지 않는다. `pin_url`과 상태만 1개월 세션 이력에 저장한다.

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
  "clarifying_question": null
}
```

| 필드 | 타입 | 제약 |
| --- | --- | --- |
| `interpretation_state` | enum | `resolved` / `needs_clarification` / `out_of_scope` / `unsafe_input` |
| `selections` | list | 역할당 최대 1개, 활성 `term_id`만, 언급된 역할만 |
| `unresolved_constraints` | list | `{role, evidence[]}` |
| `clarifying_question` | string \| null | `needs_clarification` 시 한 개 |

- LLM은 활성 카드 ID만 출력하도록 프롬프트와 structured-output enum으로 제한한다. 출력 후에도 resolver가 자체 TERM_CARD DB를 기준으로 독립 검증한다.
- `needs_clarification=true` 또는 ID 검증 실패이면 용어·링크 조립을 중단하고 질문 경로로 전환한다.
- `pending_human_review`는 응답 enum이 아니라 **사람 검토 게이트**다. DB에 없는 표현은 `needs_clarification` 질문으로 처리하고, 검토가 필요한 사례는 별도 게이트 로그만 남긴다 — LLM이 임시 용어·URL을 만들지 않는다.

### 5-2. Enum 정의 (하나씩)

| Enum | 값 |
| --- | --- |
| `JobStatus` | `queued` `running` `validating` `searching` `rendering` `completed` `failed` |
| `AgentStatus` (PR #15 승계) | `success` `needs_clarification` `out_of_scope` `unsafe_input` `partial_result` |
| `FailureCode` | `JOB_TIMEOUT` `INSTANCE_INTERRUPTED` `PROCESSING_ERROR` |
| `PinStatus` | `available` `thumbnail_unavailable` `deleted` |
| `FailureReasonCode` (일부) | `ABSTRACT_INTENT_ONLY` `INSUFFICIENT_VISUAL_EVIDENCE` `CONFLICTING_CONSTRAINTS` `TEAM_TERM_CARD_UNAVAILABLE` `IMAGE_GENERATION_REQUEST` `IMAGE_ANALYSIS_REQUEST` `STYLE_REPLICATION_REQUEST` `PIN_COLLECTION_REQUEST` `UNSUPPORTED_SUBJECT` `PROMPT_INJECTION_ATTEMPT` `SECRET_EXTRACTION_ATTEMPT` `HARMFUL_OR_ILLICIT_REQUEST` `PIN_RESULTS_EMPTY` `PIN_DELETED` `PIN_THUMBNAIL_UNAVAILABLE` `PIN_SEARCH_UNAVAILABLE` `SEARCH_URL_BUILD_FAILED` |

> Getty·외부 어휘·LLM 폴백 관련 코드(`GETTY_AAT_*`, `STATIC_CARD_STORE_UNAVAILABLE`, `LLM_FALLBACK_USED`, `REFERENCE_PLAN_UNAVAILABLE`, `LLM_RESPONSE_UNAVAILABLE`)는 PR #15 계약에서 제거되어 승계하지 않는다. 저장소 전체 불능은 `failed` job의 `TERM_CARD_STORE_UNAVAILABLE` 운영자 오류로 기록한다(응답 enum 아님).

---

## 6. 검증 규칙 (현행 계약 정합)

- `success`·`partial_result` → `reference_plan` 필수. `partial_result`의 `reason_codes`에는 실제 실패 도구 코드 ≥1.
- `needs_clarification` → `reference_plan=null`, `clarifying_question` 한 개, 임의 링크·용어 생성 금지.
- `out_of_scope`·`unsafe_input` → `reference_plan=null`, 처리할 도구를 호출하지 않는다.
- `failed` job은 `result=null` + `JobFailure`만 가진다. `job_status`와 `failure_code`의 매핑만 아래 조건으로 고정한다:
  - worker가 앱 관리 job 제한 시간 초과 전에 중단 처리 → `JOB_TIMEOUT`
  - worker lease 만료로 recovery가 실행 중단 job을 종결 → `INSTANCE_INTERRUPTED`
  - DB·LLM·Pydantic·resolver의 안전하지 않은 처리 예외 → `PROCESSING_ERROR`
  - 각각 `attempt < max_attempts`(3)일 때 `retryable=true`
- 자동 재시도는 없다. 사용자가 `POST /api/jobs/{job_id}/retry`로 새 job을 만들 때만 재시도한다.
- 작업 실패는 동기 HTTP 오류가 아니라 `failed` job의 `failure`로 기록하며, 브라우저는 polling으로만 확인한다.
- 선택되지 않은 역할은 빈 링크·빈 카드·기본 검색어를 만들지 않는다.
- 브라우저는 `/mcp`·LLM SDK·비밀값을 직접 호출하지 않는다.

---

## 7. 회의 확정 사항 (스키마 작성 블로커 해소)

| # | 결정 포인트 | 결과 (2026-09-22 회의 기준 · PR #15 정합) |
| --- | --- | --- |
| 1 | 사용자 상태 위치 | **`result.agent_status`** — 완료 payload에 위치, 미완료는 `result=null`로 구분 |
| 2 | `reason_codes` 위치 | `result` 안 (상태와 함께 도착) |
| 3 | `needs_clarification` 표현 | **`agent_status` 5종 통합** — boolean과 이중 표현 금지 |
| 4 | `failure_code`별 `retryable` 매핑 | `JOB_TIMEOUT` 전환 시·`INSTANCE_INTERRUPTED`(lease 만료)·`PROCESSING_ERROR` 모두 `attempt < max_attempts`(3)일 때 `true` |
| 5 | `retry_after_ms`·`retryable` 논리 | 폴링 `poll_after_ms` + `POST /api/jobs/{id}/retry`로 대체, `retry_after_ms` 필드 미사용 |
| 6 | `user_message` 관리 | `AgentResult.user_message`·`JobFailure.user_message` — 오류·거절 문구 최소 기준표 활용 |
| 7 | 용어 단일 원본 | **자체 TERM_CARD DB** — Getty·외부 어휘 API·폴백 LLM 사용 안 함 |

확정 후 `docs/specs/illustration-reference-current-failure-state-contract.md`의 Pydantic 필드 표와 정합화해 스키마 작성이 완료된다.

---

## 8. Next Task

1. 위 확정 7건 → 현행 계약(`frontend-api-contract`·`current-failure-state-contract`)에 Pydantic 모델(`JobEnvelope`·`AgentResult`·`ReferencePlan`·`TermResult`·`PinResult`·`AgentMessageRequest`·`InterpretationOutput`) 표 1장 반영 (PR #15 병합 시점 이후)
2. `backend/services/llm.py`에서 위 모델로 Pydantic 스키마 구현 + Langfuse (`uhkegryo-interpreter-v1`)
3. `backend/services/` 의 job executor·recovery·자체 TERM_CARD DB repository 구현 (SDD §3·§4 기준)
4. 평가셋 30건에 완료/진행/실패·5종 상태 응답 형식 검증 케이스 포함 (9/23 마일스톤)