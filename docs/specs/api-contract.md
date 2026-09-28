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
| `/api/agent` | POST | `202 {job_id, job_status:"queued", poll_after_ms:1000}`와 신규·기존 서버 세션의 HttpOnly cookie | `409 IDEMPOTENCY_KEY_CONFLICT`, `422 INVALID_REQUEST_TEXT` |
| `/api/jobs/{job_id}` | GET | `200 JobEnvelope` | `401 SESSION_REQUIRED`, `404 JOB_NOT_FOUND` |

`POST /api/jobs/{job_id}/retry`는 없다. 사용자의 후속 메시지는 새 job이다.

`AgentRequest`는 공백만으로 이루어지지 않은 `request_text` 1~500자만 가진다. 허용하지 않은 추가 필드는 거부한다. `POST /api/agent`는 유효한 기존 세션 쿠키가 있으면 재사용하고, 없으면 서버가 새 익명 세션을 발급해 동일 응답에 HttpOnly cookie로 설정한다. 브라우저는 `role`, `term_id`, 검색어, Pin URL, 세션 토큰, `anonymous_user_id`를 전송하지 않는다. 요청은 UUID `Idempotency-Key` 헤더가 필요하며, 10분 안에 같은 세션·키·원문을 재전송하면 기존 job을 반환한다.

`JobEnvelope`는 `job_id`, `session_id`, `job_status`, `attempt`, `max_attempts`, `poll_after_ms`, `result`, `failure`를 가진다. `job_status`는 `queued | running | validating | searching | rendering | completed | failed`이고 `completed`, `failed`만 종결 상태다. 진행 상태는 `result=null`, `failure=null`, `poll_after_ms=1000`이다. `completed`는 `result` 필수, `failure=null`, `poll_after_ms=null`이다. `failed`는 `result=null`, `failure` 필수, `poll_after_ms=null`이다.

`AgentResult`는 `agent_status`, `reason_codes`, `reference_plan`, `clarifying_question`, `user_message`를 가진다. `agent_status`는 `success | needs_clarification | out_of_scope | unsafe_input | partial_result`다. 서버가 LLM 후보·카탈로그·안전·검색 결과를 조립해 결정한다. `service_unavailable`은 사용하지 않는다.

`ReferencePlan`은 `terms`, `unresolved_roles`를 가진다. `terms`는 역할당 최대 하나의 활성 TERM_CARD를 역할 순서대로 가진다. 각 `TermResult`는 `role`, `term_id`, `label_ko`, `label_en`, `plain_meaning_ko`, `selection_reason`, `reference_checkpoints`, `search_url`, `pins`, `reason_codes`를 가진다. `pins`는 역할별 최대 8개이며 `PinterestCrawlerProvider`가 준 원래 순서를 보존한다. provider는 공개 검색으로 Pin ID·`pin_url`을 수집한 뒤 모든 Pin ID를 widget endpoint로 조회해 응답 전용 `thumbnail_url`을 조립한다. `TermResult.reason_codes`는 빈 배열, `PIN_RESULTS_EMPTY`, `PIN_SEARCH_UNAVAILABLE` 중 하나다. pins가 있으면 빈 배열, 정상 검색 0건이면 `PIN_RESULTS_EMPTY`, 검색 자체가 실패해 Pin을 수집하지 못하면 `PIN_SEARCH_UNAVAILABLE`을 반환한다. `AgentResult.reason_codes`는 역할 코드의 중복 없는 전체 집계다. `PinResult`는 `pin_id`, `pin_url`, 응답 전용 `thumbnail_url | null`, `status`를 가진다. `PinStatus`는 `available | deleted`다. `PIN_RESULTS_EMPTY`와 `PIN_SEARCH_UNAVAILABLE`은 Pin 상태가 아니라 역할 결과의 reason code다.

`TermResult` 피드백은 JSON에서만 조립하며 LLM이 만들지 않는다. `active_term_feedback[term_id]`가 있으면 `plain_meaning_ko <- plain_meaning_ko`, `selection_reason <- selection_reason_template_ko`, `reference_checkpoints <- reference_checkpoints_ko`다. 해당 피드백이 없으면 `plain_meaning_ko <- source_answer_draft`, `selection_reason=null`, `reference_checkpoints <- look_for`다.

`success`와 `partial_result`만 `reference_plan`을 반환한다. `needs_clarification`은 `reference_plan=null`, 비어 있지 않은 `clarifying_question`을 반환한다. `out_of_scope`와 `unsafe_input`도 `reference_plan=null`이며 `clarifying_question=null`이다. 모든 상태의 `reason_codes`는 배열이다.

`reason_codes` enum은 `ABSTRACT_INTENT_ONLY`, `INSUFFICIENT_VISUAL_EVIDENCE`, `CONFLICTING_CONSTRAINTS`, `DIRECT_SEARCH_DISABLED`, `PIN_RESULTS_EMPTY`, `PIN_SEARCH_UNAVAILABLE`, `OUT_OF_SCOPE_REQUEST`, `UNSAFE_INPUT`이다. `success`는 빈 배열만, `partial_result`는 `PIN_RESULTS_EMPTY` 또는 `PIN_SEARCH_UNAVAILABLE`만, `needs_clarification`은 `ABSTRACT_INTENT_ONLY`·`INSUFFICIENT_VISUAL_EVIDENCE`·`CONFLICTING_CONSTRAINTS`·`DIRECT_SEARCH_DISABLED` 중 하나 이상과 질문 하나를 반환한다. `out_of_scope`는 `OUT_OF_SCOPE_REQUEST`만, `unsafe_input`은 `UNSAFE_INPUT`만 반환한다. 코드 배열은 중복을 허용하지 않는다.

최종 실패는 `result=null`과 `failure={failure_code,user_message,retryable:false}`를 가진다. API에 노출하는 `failure_code` enum은 `LLM_TIMEOUT`, `LLM_RATE_LIMITED`, `LLM_UPSTREAM_UNAVAILABLE`, `LLM_INVALID_STRUCTURED_OUTPUT`, `SEARCH_TIMEOUT`, `SEARCH_RATE_LIMITED`, `SEARCH_UPSTREAM_UNAVAILABLE`, `JOB_INSTANCE_INTERRUPTED`, `CONFIGURATION_ERROR`, `DATABASE_MIGRATION_ERROR`, `DATABASE_UNAVAILABLE`, `CATALOG_INVALID_AT_STARTUP`, `INTERNAL_CODE_ERROR`이다.

## How

- 세션 쿠키의 발급·90일 갱신, session/job 저장 구조, idempotency 저장 규칙은 [session-job-persistence.md](./session-job-persistence.md)가 단일 기준이다. `GET /api/jobs/{job_id}`는 이 쿠키를 검증하며, job 조회에서 세션이 job 소유자가 아니어도 `JOB_NOT_FOUND`를 반환한다.
- Next.js 프론트는 `NEXT_PUBLIC_API_BASE_URL=/api`와 `credentials:"include"`를 사용한다. 브라우저는 FastAPI origin을 직접 호출하지 않는다. Next.js rewrite가 동일 origin의 `/api/*` 요청을 내부 FastAPI로 전달하며, BFF가 필요해질 때만 Route Handler를 추가한다. 세션 토큰·`anonymous_user_id`를 localStorage, URL, 로그에 저장하지 않는다.
- worker의 polling, lease, 세션별 실행 순서와 재실행은 [postgres-job-worker.md](./postgres-job-worker.md)가 단일 기준이다. 같은 job은 최초 실행을 포함해 최대 3회이며 LLM 회복 가능 실패 뒤에는 `next_retry_at` 전까지 재실행하지 않는다. `next_retry_at`의 저장 계약은 [session-job-persistence.md](./session-job-persistence.md)가 단일 기준이다. LLM 오류별 재시도·backoff·최종 failure code는 [openrouter-llm-adapter.md](./openrouter-llm-adapter.md)가 단일 기준이다.
- `CONFIGURATION_ERROR`, `DATABASE_MIGRATION_ERROR`, `INTERNAL_CODE_ERROR`는 즉시 `failed`다. 사용자 UI는 failure code·오류 원문·비밀값을 보이지 않고 “현재 요청을 처리하지 못했습니다. 잠시 후 새 메시지로 다시 시도해 주세요.”만 표시한다.
- 단서 부족·상충은 실패가 아니라 `completed + needs_clarification`이며 질문 하나를 반환한다. 다음 사용자 메시지는 새 job이고 기존 attempt를 승계하지 않는다.
- LLM adapter는 `InterpretationOutput={interpretation_state, clarification_type, selections, unresolved_constraints, clarifying_question}`만 반환한다. `interpretation_state`는 `select_terms | needs_clarification` enum이고, 허용하지 않은 추가 필드는 거부한다. 각 `selections` 항목은 `{role, term_id, evidence, confidence}`이며, `evidence`는 요청에서 확인한 비어 있지 않은 한국어 표현의 배열(`list[str]`, 한 개 이상), `confidence`는 `0.0..1.0`이다. 역할은 중복되지 않고 `body → pose → view → perspective → layout` 순서를 따른다.
- `select_terms`이면 selections는 한 개 이상, `unresolved_constraints=[]`, `clarifying_question=null`, `clarification_type=null`이다. `needs_clarification`이면 selections는 빈 배열, `unresolved_constraints`는 비어 있거나 공백만으로 이루어지지 않은 항목을 한 개 이상 가지며, `clarifying_question`은 비어 있지 않은 한국어 질문 하나, `clarification_type`은 `abstract_intent | insufficient_visual_evidence | conflicting_constraints` 중 하나다. `clarification_type`은 최종 `reason_code`가 아닌 resolver가 다시 검증할 후보다.
- LLM은 최종 `agent_status`, `reason_codes`, 검색 URL을 만들지 않으며, resolver가 활성 JSON 카탈로그·안전 규칙과 대조한 뒤 최종 응답을 조립한다. 구조화 출력이 이 계약을 만족하지 않으면 `LLM_INVALID_STRUCTURED_OUTPUT`으로 처리한다. `requires_all_of`·`requires_any_of`는 카탈로그의 부모 `term_id` 의존 관계이며 LLM selection 목록의 추가 항목이 아니다. resolver는 부모 ID가 selection에 없다는 이유로 후보를 거부하지 않고, 선택 카드의 의존 그래프가 존재·활성·비순환인지 확인한다.
- resolver의 질문 사유 매핑은 아래와 같다. free-text `unresolved_constraints`만으로 최종 코드를 정하지 않으며, 요청 단서와 카드 조건을 함께 다시 검증한다.

| resolver가 검증한 조건 | 허용된 `clarification_type` 후보 | 최종 `reason_code` |
| --- | --- | --- |
| 구체적인 체형·포즈·시점·원근·구도 단서 없이 인상·의도만 있음 | `abstract_intent` | `ABSTRACT_INTENT_ONLY` |
| 역할 단서는 있으나 해당 카드의 `confidence_gate`를 충족할 단서가 없음 | `insufficient_visual_evidence` | `INSUFFICIENT_VISUAL_EVIDENCE` |
| 서로 양립할 수 없는 체형·시점·자세 조건이 동시에 명시됨 | `conflicting_constraints` | `CONFLICTING_CONSTRAINTS` |
| 유효한 카드가 선택됐지만 `direct_search_disabled_term_ids`에 포함됨 | 해당 없음 — LLM이 판단하지 않음 | `DIRECT_SEARCH_DISABLED` |
- `PinterestCrawlerProvider` 구현 시 서버 Playwright는 활성 카드의 `query_fragments`만 카드 유래 입력으로 사용해야 한다. 결정론 URL 빌더는 기존 조각의 `drawing` 포함 여부를 검사하거나 제거하지 않고 결합한 검색어 끝에 고정 접미사 `drawing`을 무조건 한 번 추가한 뒤 공개 검색을 수행하고, 모든 수집 Pin ID를 widget endpoint로 조회해야 한다. 브라우저는 Pinterest·widget endpoint를 직접 호출하지 않으며 Pinterest API v5도 사용하지 않는다.
- 검색 provider 재시도가 소진돼도 하나 이상의 카드가 유효하면 `completed + partial_result`다. 실패 역할은 `pins=[]`, `PIN_SEARCH_UNAVAILABLE`을 반환하고 UI는 검색 결과 미수신 안내와 용어·검색 URL을 표시한다. 수집한 Pin의 widget·원본 접근 실패 또는 이미지 URL 부재는 `deleted` 상태로 반환한다. 정상 0건은 `PIN_RESULTS_EMPTY`이며 재시도하지 않는다.
- 잘못된 Secret·provider 인증 설정은 `CONFIGURATION_ERROR`, job/session 저장소 연결 불가는 `DATABASE_UNAVAILABLE`, 시작 JSON 카탈로그 검증 실패는 `CATALOG_INVALID_AT_STARTUP`, 코드 버그는 `INTERNAL_CODE_ERROR`로 즉시 실패한다. `CATALOG_INVALID_AT_STARTUP`이면 서비스는 ready가 아니며 job을 수신하지 않는다. 이 네 경우는 자동 재시도하지 않는다.
- provider 결과의 원격 썸네일은 `available`일 때만 표시하고 항상 원본 `pin_url`로 이동한다. widget이 이미지 URL을 주지 않거나 접근할 수 없으면 `deleted`와 접근 불가 안내를 반환한다. `pin_id`, `pin_url`, `status`는 세션·job 이력에 포함된 결과로만 유지하고 별도 Pin 저장소를 만들지 않는다. `GET /api/jobs/{job_id}`는 저장된 `pin_id`로 widget을 다시 조회해 응답 전용 `thumbnail_url`을 조립하며, 이 조회에서 접근할 수 없는 Pin은 `deleted`로 표시한다. widget의 이미지 바이트·`thumbnail_url`과 부가 Pin 필드는 저장·재게시·LLM 입력·trace·로그에 사용하지 않는다.

## AC

**AC-01 · 비동기 제출**

- GIVEN: 1~500자 입력이 있다.
- WHEN: `POST /api/agent`로 요청을 제출한다.
- THEN: 신규 세션은 HttpOnly cookie를 발급하고, 기존 세션은 이를 재사용하며, `202`와 queued job을 반환한다.
- AND THEN: 프론트는 종결까지 polling한다.

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
