# Agent 공개 API 계약

## Why

자연어 해석과 검색은 오래 걸리거나 일시적으로 실패할 수 있다. 세션 소유권, 비동기 job, 결과 상태, 자동 재시도 규칙을 하나의 공개 계약으로 고정한다.

## Goal

- 서버 세션 쿠키와 job polling으로 요청을 처리한다.
- LLM·검색 provider의 회복 가능한 오류는 사용자에게 노출하지 않고 최대 3회 자동 재시도한다.
- 사용자에게는 검증된 결과, 질문, 부분 결과 또는 일반 실패 안내만 보여 준다.

## What

| Endpoint | Method | 성공 | 오류 |
| --- | --- | --- |
| `/health` | GET | `200 {"status":"ok"}` | — |
| `/api/sessions` | POST | `201`, `session_id`, `expires_at`, HttpOnly cookie | — |
| `/api/sessions/{session_id}/messages` | POST | `202 {message_id, job_id, job_status:"queued", poll_after_ms:1000}` | `401 SESSION_REQUIRED`, `404 SESSION_NOT_FOUND`, `422 INVALID_REQUEST_TEXT` |
| `/api/jobs/{job_id}` | GET | `200 JobEnvelope` | `401 SESSION_REQUIRED`, `404 JOB_NOT_FOUND` |

`POST /api/jobs/{job_id}/retry`는 없다. 사용자의 후속 메시지는 새 job이다.

`AgentMessageRequest`는 공백만으로 이루어지지 않은 `request_text` 1~500자만 가진다. 허용하지 않은 추가 필드는 거부한다. 브라우저는 `role`, `term_id`, 검색어, Pin URL, 세션 토큰, `anonymous_user_id`를 전송하지 않는다.

`JobEnvelope`는 `job_id`, `session_id`, `request_id`, `job_status`, `attempt`, `max_attempts`, `poll_after_ms`, `result`, `failure`를 가진다. `job_status`는 `queued | running | validating | searching | rendering | completed | failed`이고 `completed`, `failed`만 종결 상태다. 진행 상태는 `result=null`, `failure=null`, `poll_after_ms=1000`이다. `completed`는 `result` 필수, `failure=null`, `poll_after_ms=null`이다. `failed`는 `result=null`, `failure` 필수, `poll_after_ms=null`이다.

`AgentResult`는 `agent_status`, `reason_codes`, `reference_plan`, `clarifying_question`, `user_message`를 가진다. `agent_status`는 `success | needs_clarification | out_of_scope | unsafe_input | partial_result`다. 서버가 LLM 후보·카탈로그·안전·검색 결과를 조립해 결정한다. `service_unavailable`은 사용하지 않는다.

`ReferencePlan`은 `terms`, `unresolved_roles`를 가진다. `terms`는 역할당 최대 하나의 활성 TERM_CARD를 역할 순서대로 가진다. 각 `TermResult`는 `role`, `term_id`, `label_ko`, `label_en`, `plain_meaning_ko`, `selection_reason`, `reference_checkpoints`, `search_url`, `pins`를 가진다. `pins`는 역할별 최대 8개이며 provider가 준 원래 순서를 보존한다. `PinResult`는 `pin_url`, 응답 전용 `thumbnail_url | null`, `status`를 가진다. `PinStatus`는 `available | thumbnail_unavailable | deleted`다. `PIN_RESULTS_EMPTY`와 `PIN_SEARCH_UNAVAILABLE`은 Pin 상태가 아니라 역할 결과의 reason code다.

`TermResult` 피드백은 JSON에서만 조립하며 LLM이 만들지 않는다. `active_term_feedback[term_id]`가 있으면 `plain_meaning_ko <- plain_meaning_ko`, `selection_reason <- selection_reason_template_ko`, `reference_checkpoints <- reference_checkpoints_ko`다. 해당 피드백이 없으면 `plain_meaning_ko <- source_answer_draft`, `selection_reason=null`, `reference_checkpoints <- look_for`다.

`success`와 `partial_result`만 `reference_plan`을 반환한다. `needs_clarification`은 `reference_plan=null`, 비어 있지 않은 `clarifying_question`을 반환한다. `out_of_scope`와 `unsafe_input`도 `reference_plan=null`이며 `clarifying_question=null`이다. 모든 상태의 `reason_codes`는 배열이다.

`reason_codes` enum은 `ABSTRACT_INTENT_ONLY`, `INSUFFICIENT_VISUAL_EVIDENCE`, `CONFLICTING_CONSTRAINTS`, `DIRECT_SEARCH_DISABLED`, `PIN_RESULTS_EMPTY`, `PIN_SEARCH_UNAVAILABLE`, `OUT_OF_SCOPE_REQUEST`, `UNSAFE_INPUT`이다. `success`는 빈 배열만, `partial_result`는 `PIN_RESULTS_EMPTY` 또는 `PIN_SEARCH_UNAVAILABLE`만, `needs_clarification`은 `ABSTRACT_INTENT_ONLY`·`INSUFFICIENT_VISUAL_EVIDENCE`·`CONFLICTING_CONSTRAINTS`·`DIRECT_SEARCH_DISABLED` 중 하나 이상과 질문 하나를 반환한다. `out_of_scope`는 `OUT_OF_SCOPE_REQUEST`만, `unsafe_input`은 `UNSAFE_INPUT`만 반환한다. 코드 배열은 중복을 허용하지 않는다.

최종 실패는 `result=null`과 `failure={failure_code,user_message,retryable:false}`를 가진다. API에 노출하는 `failure_code` enum은 `LLM_TIMEOUT`, `LLM_RATE_LIMITED`, `LLM_UPSTREAM_UNAVAILABLE`, `LLM_INVALID_STRUCTURED_OUTPUT`, `SEARCH_TIMEOUT`, `SEARCH_RATE_LIMITED`, `SEARCH_UPSTREAM_UNAVAILABLE`, `JOB_INSTANCE_INTERRUPTED`, `CONFIGURATION_ERROR`, `DATABASE_MIGRATION_ERROR`, `DATABASE_UNAVAILABLE`, `CATALOG_INVALID_AT_STARTUP`, `INTERNAL_CODE_ERROR`이다.

## How

- `POST /api/sessions`를 제외한 모든 `/api/*` endpoint는 서버 발급 `HttpOnly`, `SameSite=Lax`, `Path=/` 세션 쿠키를 검증한다. 배포에서는 `Secure=true`이며 로컬 HTTP에서만 명시적 local 설정으로 `false`를 허용한다. job 조회에서 세션이 job 소유자가 아니어도 `JOB_NOT_FOUND`를 반환한다.
- Next.js 프론트는 `NEXT_PUBLIC_API_BASE_URL=/api`와 `credentials:"include"`를 사용한다. 브라우저는 FastAPI origin을 직접 호출하지 않는다. Next.js rewrite가 동일 origin의 `/api/*` 요청을 내부 FastAPI로 전달하며, BFF가 필요해질 때만 Route Handler를 추가한다. 세션 토큰·`anonymous_user_id`를 localStorage, URL, 로그에 저장하지 않는다.
- 같은 job의 자동 실행은 최초 실행을 포함해 최대 3회다. `LLM_*`, `SEARCH_*`, `JOB_INSTANCE_INTERRUPTED`의 회복 가능한 경우에만 내부적으로 재시도한다.
- `CONFIGURATION_ERROR`, `DATABASE_MIGRATION_ERROR`, `INTERNAL_CODE_ERROR`는 즉시 `failed`다. 사용자 UI는 failure code·오류 원문·비밀값을 보이지 않고 “현재 요청을 처리하지 못했습니다. 잠시 후 새 메시지로 다시 시도해 주세요.”만 표시한다.
- 단서 부족·상충은 실패가 아니라 `completed + needs_clarification`이며 질문 하나를 반환한다. 다음 사용자 메시지는 새 job이고 기존 attempt를 승계하지 않는다.
- LLM adapter는 `InterpretationOutput={interpretation_state, selections, unresolved_constraints, clarifying_question}`만 반환한다. 각 `selections` 항목은 `{role, term_id, evidence, confidence}`다. LLM은 최종 `agent_status`, `reason_codes`, 검색 URL을 만들지 않으며, resolver가 활성 JSON 카탈로그·안전 규칙과 대조한 뒤 최종 응답을 조립한다. 구조화 출력이 이 계약을 만족하지 않으면 `LLM_INVALID_STRUCTURED_OUTPUT`으로 처리한다.
- 검색 provider 재시도가 소진돼도 하나 이상의 카드가 유효하면 `completed + partial_result`다. 실패 역할은 `pins=[]`, `PIN_SEARCH_UNAVAILABLE`을 반환하고 UI는 검색 결과 미수신 안내와 용어·검색 URL을 표시한다. 정상 0건은 `PIN_RESULTS_EMPTY`이며 재시도하지 않는다.
- 잘못된 Secret·provider 인증 설정은 `CONFIGURATION_ERROR`, job/session 저장소 연결 불가는 `DATABASE_UNAVAILABLE`, 시작 JSON 카탈로그 검증 실패는 `CATALOG_INVALID_AT_STARTUP`, 코드 버그는 `INTERNAL_CODE_ERROR`로 즉시 실패한다. `CATALOG_INVALID_AT_STARTUP`이면 서비스는 ready가 아니며 job을 수신하지 않는다. 이 네 경우는 자동 재시도하지 않는다.
- provider 결과의 원격 썸네일은 `available`일 때만 표시하고 항상 원본 `pin_url`로 이동한다. `thumbnail_unavailable`은 링크만, `deleted`는 링크·썸네일 미표시다. 이미지 바이트·썸네일 URL·Pin 메타데이터는 저장하거나 재게시하지 않는다.

## AC

**AC-01 · 비동기 제출**

- GIVEN: 유효 세션과 1~500자 입력이 있다.
- WHEN: 메시지를 제출한다.
- THEN: `202`와 queued job을 반환하고 프론트는 종결까지 polling한다.

**AC-02 · 자동 재시도**

- GIVEN: 회복 가능한 LLM 또는 검색 오류가 있다.
- WHEN: worker가 처리한다.
- THEN: 사용자에게 중간 오류를 보이지 않고 최초 실행 포함 최대 3회 실행한다.

**AC-03 · 검색 부분 결과**

- GIVEN: 유효 카드가 있고 검색 provider 재시도가 소진된다.
- WHEN: 결과를 조립한다.
- THEN: `completed + partial_result`, 빈 pins, `PIN_SEARCH_UNAVAILABLE`을 반환한다.

**AC-04 · 최종 실패 코드**

- GIVEN: 재시도 소진 또는 결정적 운영 오류가 발생한다.
- WHEN: job을 종결한다.
- THEN: API는 안정된 `failure_code`를 포함한다.
- AND THEN: UI는 일반 실패 문구만 표시한다.

**AC-05 · 동일 origin API 호출**

- GIVEN: 배포된 Next.js 프론트가 있다.
- WHEN: 브라우저가 API를 호출한다.
- THEN: `/api/*` 상대 경로와 세션 쿠키만 사용한다.
- AND THEN: FastAPI origin으로 직접 cross-origin 요청하지 않는다.

**AC-06 · polling 종료**

- GIVEN: job 조회 응답이 있다.
- WHEN: job이 진행 중이다.
- THEN: `poll_after_ms=1000`을 반환한다.
- WHEN: job이 `completed` 또는 `failed`다.
- THEN: `poll_after_ms=null`을 반환한다.

**AC-07 · TERM_CARD 피드백 조립**

- GIVEN: 활성 카드와 `active_term_feedback[term_id]`가 있다.
- WHEN: `TermResult`를 조립한다.
- THEN: API 피드백 필드는 해당 JSON 피드백에서만 매핑한다.
- GIVEN: 활성 카드에 해당 피드백이 없다.
- WHEN: `TermResult`를 조립한다.
- THEN: `source_answer_draft`, `look_for`를 fallback으로 사용하고 LLM이 문구를 생성하지 않는다.
