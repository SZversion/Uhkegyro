# SDD — UH케그려 MVP 아키텍처

## 1. 기준 데이터와 불변 조건

구현 후 프로젝트 자체 TERM_CARD DB는 LLM 출력·화면 피드백·Pinterest 검색어의 런타임 단일 원본이다. 역할별 JSON은 초기 74개 카드를 검수하고 DB에 적재하기 위한 시드 자료이며, 런타임 요청마다 읽지 않는다. 현재는 DB schema·적재·repository가 미구현이고 역할별 JSON만 존재한다. DB는 `runtime_eligible=true && mvp_status=active_in_current_contract` 카드만 `term_id` 사전으로 만든다. 현재 시드 카드 74개는 모두 이 조건을 통과하며 역할 분포는 body 6, pose 52, view 9, perspective 5, layout 2이다.

Getty AAT는 용어 조사 시 참고한 자료일 뿐 프로젝트 DB·MCP 응답·LLM 입력·사용자 화면에 저장하거나 표시하지 않는다. Getty API·SPARQL·웹 호출은 하지 않는다.

모든 선택 결과는 이 사전에 존재해야 하며, 원본 카드의 `role`, `label_ko`, `label_en`, `query_fragments`, `look_for`, `confidence_gate`, `requires_all_of`, `requires_any_of`, `source_type`, 초보자 피드백을 변경 없이 참조한다. 카드 파일 밖의 자유 형식 용어·검색어·외부 어휘 후보는 런타임 선택 경로에 들어갈 수 없다.

## 2. 컴포넌트와 책임

```text
React + Vite UI
  -> POST /api/sessions -> 서버 세션 쿠키
  -> POST /api/sessions/{session_id}/messages -> 202 {job_id, queued}
  -> GET /api/jobs/{job_id} polling -> Job envelope
  <- completed AgentResult 또는 failed JobFailure
       -> 원격 썸네일을 원본 Pin 링크로 표시

Job executor / recovery
  -> 영속 job claim·lease·상태 전이
  -> LLM adapter (구조화 후보만 생성)
  -> Card repository / resolver (자체 TERM_CARD DB의 활성 카드·제약 검증)
  -> PinterestSearchProvider (교체 가능한 검색 구현)
  -> Response assembler (역할별 최대 8개 {pin_url, thumbnail_url, status} 조립)

배포 시드: term-cards/index.json + 역할별 카드 JSON -> TERM_CARD DB -> Card repository -> Card resolver
FastMCP -> LLM이 필요하다고 판단한 도구 호출을 중계 (도구 목록·계약 미정)
Langfuse <- LLM adapter의 요청 ID·모델·토큰·지연·비용·재시도
```

| 컴포넌트 | 책임 | 금지 |
| --- | --- | --- |
| UI | chat 입력, 역할별 Pin 섹션, 원격 썸네일·원본 링크, 상태·오류·재시도 표시 | 이미지 파일·썸네일 URL 저장, 키 보유, LLM 직접 호출 |
| FastAPI route | 세션·메시지·job 조회/재시도의 HTTP 경계와 Pydantic 검증 | 장시간 도메인 처리 직접 실행 |
| Job executor / recovery | job claim·lease·상태 전이, 결과·실패 영속화, 만료 lease 복구 | 브라우저 상태·세션 소유권 우회 |
| LLM adapter | 카드 ID 후보·모호성·질문 필요 상태 생성 | 카드 밖 ID, 자유 검색어·URL 생성 |
| Card repository | 자체 TERM_CARD DB 조회, 활성 사전·역할별 인덱스 제공 | 카드 변경, 외부 후보 병합 |
| Card resolver | ID·역할·confidence/requires 검증 | 의도 추측, 출처 조작 |
| URL builder | 카드 fragment 순서 보존, 공백·특수문자 URL 인코딩 | 일상어·설명문·추상 intent 추가 |
| FastMCP | 모든 도구를 담는 실행 틀; 도구 목록·계약 확정 후 등록하고 LLM 요청에 따라 호출 중계 | 카드 밖 term 제안, 이미지 파일 저장 |
| PinterestSearchProvider | FastMCP에 등록되는 검색 도구 구현. 활성 카드의 `query_fragments`로 검색하고 `pin_url`·`thumbnail_url`·상태 반환 | 이미지 다운로드·썸네일 URL 저장 |
| Session repository | chat·구조화 결과·Pin URL·상태를 Cloud SQL에 1개월 저장 | 이미지 바이너리·썸네일 URL 저장 |

## 3. API 계약의 강제성

공개 API의 단일 기준은 [api-contract.md](./specs/api-contract.md)다. 브라우저는 `POST /api/agent`로 요청을 제출하고(신규 세션 시 HttpOnly cookie 발급), `GET /api/jobs/{job_id}`의 job envelope가 최종 결과 기준이다. 결과의 `agent_status`, `reason_codes`, `ReferencePlan` 구조와 job 실패 계약 모두 `api-contract.md`가 유일한 기준이다.

- `GET /health`는 상태 확인 전용이다. `/api/sessions`, `/api/sessions/{session_id}/messages`, `/api/jobs/{job_id}`, `/api/jobs/{job_id}/retry`가 MVP 공개 API다.
- 클라이언트는 `request_text`와 서버가 반환한 현재 화면의 `session_id`만 경로에 사용한다. `role`·`term_id`·검색어·Pin URL·세션 토큰·`anonymous_user_id`는 서버가 결정한다.
- LLM은 `{role, term_id, evidence, confidence}` 후보와 의미 상태만 출력한다. resolver가 자체 TERM_CARD DB의 활성 여부·역할·조건을 다시 검증한다.
- 검색 provider는 검증된 카드의 `query_fragments`만 입력으로 받고 `pin_url`, `thumbnail_url`, `status`를 반환한다. UI는 썸네일 URL이 있을 때만 원격 미리보기를 표시하고, 이미지 바이트·썸네일 URL·Pin 메타데이터를 저장하지 않는다.
- worker 오류는 동기 HTTP 응답이 아니라 `failed` job의 `JobFailure`로 기록한다. 브라우저는 polling에서만 결과·실패를 확인하며, 자동 재시도하지 않는다. 사용자는 `POST /api/jobs/{job_id}/retry`로 새 job을 만든다.

### 세션 저장

세션 레코드는 서버 생성 `session_id`, `session_token_hash`, `anonymous_user_id_hash`, 생성 시각, 마지막 활동 시각, 만료 시각, 최근 대화 요약을 가진다. 브라우저에는 `HttpOnly` 세션 쿠키만 전달하며, `anonymous_user_id`와 토큰 원문을 로컬 저장소·URL·로그에 두지 않는다. 메시지 레코드는 사용자 메시지, 구조화 JSON, 검증 결과, 모델명·프롬프트 버전, 생성 시각을 가진다. job 레코드는 상태, attempt, lease, request ID, 실패 코드, 생성·종료 시각을 가진다. 검색 결과 레코드는 메시지·역할·term_id·Pin URL·`active|thumbnail_unavailable|deleted|no_results|search_error` 상태·생성 시각을 가진다. 이미지 바이너리, 썸네일 URL, Pin 메타데이터, LLM 원문 응답은 저장하지 않는다.

### 응답

`completed` job의 `AgentResult.reference_plan`은 역할별 팀 카드 정보와 최대 8개의 `{pin_url, thumbnail_url, status}`를 담는다. 같은 Pin URL이 여러 역할에 있으면 역할별 중복을 유지한다. UI는 `thumbnail_url`이 있을 때만 원격 썸네일을 표시하고 `pin_url`을 원본 링크로 사용한다. 이미지 바이트·썸네일 URL·Pin 메타데이터는 저장하지 않는다.

## 4. 상세 처리 순서

1. 앱 시작 시 `term-card-catalog.md`의 시작 검증을 실행해 JSON 카탈로그를 메모리에 로드한다. 검증 실패 시 `CATALOG_INVALID_AT_STARTUP`로 ready 상태를 거부한다.
2. resolver는 메모리의 활성 카드 사전만 사용해 후보를 검증한다. DB 적재·외부 어휘 조회는 하지 않는다.
3. `POST /api/agent`가 입력(1~500자, 추가 필드 거부)을 검증하고, 신규 세션 시 HttpOnly cookie를 발급해 `202 {job_id, job_status:"queued"}`를 반환한다. 기존 세션 쿠키가 있으면 재사용한다.
4. Worker가 job을 claim해 `running`→`validating`→`searching`→`rendering` 전이를 기록한다. 회복 가능한 LLM·검색 오류는 사용자에게 노출하지 않고 최초 포함 최대 3회 자동 재시도한다. `JOB_INSTANCE_INTERRUPTED`는 lease 만료 시 한 번만 종결한다.
5. LLM adapter는 `InterpretationOutput`(세션·후보·모호성 질문)만 반환한다. 최종 `agent_status`, `reason_codes`, 검색 URL은 resolver가 조립한다.
6. resolver는 메모리 카탈로그의 활성 `term_id`·`role`·조건(`confidence_gate`, `requires_all_of`, `requires_any_of`)을 통과한 후보만 선택한다.
7. 단서 부족·상충은 실패가 아니라 `completed + needs_clarification`이며 질문 하나를 반환한다. 다음 사용자 메시지는 새 job이다.
8. 유효 카드마다 `active_term_feedback[term_id]`가 있으면 `plain_meaning_ko`, `selection_reason_template_ko`, `reference_checkpoints_ko`를 API 필드에 매핑한다. 없으면 `source_answer_draft`, `look_for`를 fallback으로 사용하고 LLM이 문구를 생성하지 않는다.
9. URL builder는 선택 카드의 `query_fragments`만 합쳐 Pinterest 검색 URL을 만든다. `direct_search_disabled_term_ids` 해당 시 URL·provider 호출 없이 `needs_clarification`을 반환한다.
10. PinterestSearchProvider가 역할별 결과를 반환하면 `{pin_url, thumbnail_url, status}`를 조립한다. 검색 재시도 소진 시 `PIN_SEARCH_UNAVAILABLE`, 정상 0건 시 `PIN_RESULTS_EMPTY`를 역할 `reason_codes`에 기록한다. 하나 이상의 카드가 유효하면 `partial_result`로 종결한다.
11. 모든 카드 유효하고 검색 성공 시 `completed + success`. 재시도 소진 또는 결정적 운영 오류 시 `failed`와 안정된 `failure_code`(예: `LLM_TIMEOUT`, `SEARCH_RATE_LIMITED`, `CONFIGURATION_ERROR` 등)로 종결한다.

## 5. 실패와 폴백

상세 실패 코드·자동 재시도 규칙·UI 표시 규칙은 [api-contract.md](./specs/api-contract.md) §How·§AC를 단일 기준으로 따른다. 요약:

| 실패 유형 | 결과 처리 |
| --- | --- |
| 카탈로그 검증 실패 | `CATALOG_INVALID_AT_STARTUP` — ready 거부, job 수신 안 함 |
| 입력 계약 위반(길이·필드) | `422 INVALID_REQUEST_TEXT` — LLM·MCP 미호출 |
| 회복 가능한 LLM 오류 | 자동 재시도(최대 3회), 소진 시 `LLM_TIMEOUT`·`LLM_RATE_LIMITED`·`LLM_UPSTREAM_UNAVAILABLE`·`LLM_INVALID_STRUCTURED_OUTPUT` |
| 회복 가능한 검색 오류 | 자동 재시도(최대 3회), 소진 시 `SEARCH_TIMEOUT`·`SEARCH_RATE_LIMITED`·`SEARCH_UPSTREAM_UNAVAILABLE` |
| 결정적 운영 오류 | 즉시 `failed` — `CONFIGURATION_ERROR`·`DATABASE_MIGRATION_ERROR`·`DATABASE_UNAVAILABLE`·`INTERNAL_CODE_ERROR` |
| 단서 부족·상충 | `completed + needs_clarification` + 질문 (실패 아님) |
| 카드 밖·비활성 ID | resolver가 폐기, 검색 URL·provider 호출 안 함 |
| 검색 0건 | `PIN_RESULTS_EMPTY` (재시도 안 함) |
| 검색 재시도 소진 | `PIN_SEARCH_UNAVAILABLE` (유효 카드 있으면 `partial_result`) |
| Pin 썸네일 부재/삭제 | `thumbnail_unavailable`·`deleted` — 표시만 제한, job 상태 영향 없음 |

## 6. 관측·보안·검증

관측·프롬프트 버전·구조화 로그·retry event 계약은 [observability-and-prompt-versioning.md](./specs/observability-and-prompt-versioning.md)를 단일 기준으로 따른다.

비밀값은 `.env`와 배포 Secret Manager에만 두며 UI와 git에 노출하지 않는다. `session_id`, 세션 토큰 원문은 로그·trace에 남기지 않고 해시만 기록한다. 세션·job 상태·구조화 결과·Pin URL과 상태는 1개월 저장하고 만료 삭제한다(로컬 SQLite, 운영 Neon PostgreSQL). 썸네일 URL과 이미지 바이트·Pin 메타데이터는 저장하지 않는다. 세션 쿠키는 배포에서 `HttpOnly`, `Secure=true`, `SameSite=Lax`로 설정한다. 로컬 HTTP 개발에서만 명시적 local 설정의 `Secure=false`를 허용하며 배포 설정에 재사용하지 않는다. Next.js 프론트는 동일 origin(`/api/*` rewrite)으로 API 호출하며, cross-site cookie는 범위 밖이다. Pinterest 검색 API·비즈니스 계정은 provider 구현을 교체 가능하게 유지한다. `main`에는 직접 push하지 않고 개인 브랜치·PR·리뷰 흐름을 따른다.
