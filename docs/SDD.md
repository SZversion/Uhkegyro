# SDD — UH케그려 MVP 아키텍처

## 1. 기준 데이터와 불변 조건

구현 후 프로젝트 자체 TERM_CARD DB는 LLM 출력·화면 피드백·Pinterest 검색어의 런타임 단일 원본이다. 역할별 JSON은 초기 74개 카드를 검수하고 DB에 적재하기 위한 시드 자료이며, 런타임 요청마다 읽지 않는다. 현재는 DB schema·적재·repository가 미구현이고 역할별 JSON만 존재한다. DB는 `runtime_eligible=true && mvp_status=active_in_current_contract` 카드만 `term_id` 사전으로 만든다. 현재 시드 기준 활성 20개 역할 분포는 body 5, pose 7, view 4, perspective 3, layout 1이다.

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

공개 API의 단일 기준은 [frontend-api-contract.md](./specs/frontend-api-contract.md)다. 브라우저는 `POST /api/sessions`로 서버 세션을 받고, `POST /api/sessions/{session_id}/messages`의 `request_text`로 비동기 job을 생성한다. 메시지 endpoint는 `202`와 `job_id`만 반환하며, `GET /api/jobs/{job_id}`의 job envelope가 최종 결과 기준이다. 결과의 `agent_status`, `reason_codes`, `ReferencePlan` 구조와 job 실패 계약은 [illustration-reference-current-failure-state-contract.md](./specs/illustration-reference-current-failure-state-contract.md)가 유일한 기준이다.

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

1. 배포·시드 적재 시 Card repository가 역할별 JSON의 합계 `card_count=74`와 필수 필드를 검증한 뒤 자체 TERM_CARD DB에 적재한다. 런타임은 DB의 스키마·활성 카드 수를 검증하며, 실패하면 ready 상태로 만들지 않고 운영자 오류로 기록한다.
2. repository는 활성 20개 카드만 인덱싱하고, 후보·미검수 카드는 메모리 모델에서 제외한다.
3. `POST /api/sessions` route가 서버 생성 세션과 `HttpOnly` 쿠키를 만들고, `POST /api/sessions/{session_id}/messages`가 소유권·입력 규칙을 검증한 뒤 `queued` job과 request ID를 영속화한다.
4. Job executor가 job을 claim해 lease와 `running` 상태를 저장한다. Cloud Run 중단으로 lease가 만료되면 recovery가 한 번만 `INSTANCE_INTERRUPTED` failed 상태로 종결한다.
5. LLM adapter는 활성 카드의 ID·role·confidence gate만 근거로 구조화 후보를 생성한다.
6. resolver는 (a) 선택 역할 여부, (b) 활성 사전 존재 여부, (c) 카드 role 일치, (d) `confidence_gate`, (e) `requires_all_of` 전체 충족, (f) `requires_any_of` 중 하나 충족을 검증한다.
7. 단서가 없거나 검증을 통과하지 못하면 `needs_clarification` 결과를 만들어 `completed`로 종결한다.
8. 유효 카드마다 response assembler가 자체 DB의 카드 피드백과 팀 검수 상태를 조립한다. Getty 데이터·귀속·외부 어휘 API·SPARQL·웹 조회는 사용하지 않는다.
9. URL builder는 선택 카드의 `query_fragments` 배열만 합쳐 Pinterest 검색 URL을 만든다. `direct_search_disabled_term_ids`에 해당하면 링크를 만들지 않는다.
10. PinterestSearchProvider가 역할별 결과를 반환하면 `{pin_url, thumbnail_url, status}`를 조립한다. 썸네일 URL이 없으면 `thumbnail_unavailable`로 원본 링크만 표시하고, 삭제 Pin은 `deleted`로 표시 대상에서 제외한다. 0건은 `no_results`, 검색 장애는 `search_error`와 재시도 안내로 구분한다.
11. 카드 결과가 하나 이상이면 `completed`와 `AgentResult`를 저장한다. 안전하게 조립할 수 없는 LLM·DB·resolver 오류는 `failed`와 `PROCESSING_ERROR`, 앱 관리 job 제한 시간은 `JOB_TIMEOUT`으로 종결한다.

## 5. 실패와 폴백

| 실패 | 응답/운영 처리 |
| --- | --- |
| JSON 누락·파싱 실패·스키마 불일치 | 서비스 준비 실패, 운영 로그 기록; 빈 허용 목록으로 실행 금지 |
| 입력 계약 위반 | 검증 오류; LLM·MCP를 호출하지 않음 |
| LLM timeout·형식 오류 | `failed` job과 `JOB_TIMEOUT` 또는 `PROCESSING_ERROR` 기록; 사용자 수동 재시도 가능 상태와 trace 기록 |
| 앱 관리 job 제한 시간 초과 | `failed` job과 `JOB_TIMEOUT`으로 종결 |
| Cloud Run 종료 | lease 만료 뒤 recovery가 `failed` job과 `INSTANCE_INTERRUPTED`로 종결 |
| 게이트웨이 timeout·브라우저 연결 단절 | job 상태를 바꾸지 않음; 브라우저 전송 실패 안내 후 같은 job polling 또는 새 요청 |
| 카드 밖 또는 비활성 ID | resolver가 폐기; 링크 생성 금지 |
| 단서 부족·상충 | 추측 금지, 질문 또는 `pending_human_review` |
| 카드 필수 필드 누락 | 해당 카드를 검증 오류로 기록하고, 외부 출처를 생성·조회하지 않음 |
| 자체 TERM_CARD DB 미연결·미적재 | `TERM_CARD_STORE_UNAVAILABLE`을 기록하고 결과·링크를 만들지 않음 |
| Pinterest URL 생성 불가 | URL 생략 및 사유 표시; 대체 자유 문장 URL 금지 |
| 검색 결과 0건 | 해당 역할에 `no_results`와 `검색 결과가 없습니다` 표시 |
| Pin 썸네일 부재 | `thumbnail_unavailable`으로 원본 Pin 링크만 표시 |
| Pin 삭제 | URL은 세션 이력에 남기되 `deleted` 상태와 `이 Pin은 삭제되었습니다` 표시 |
| 검색 시스템 오류 | `search_error`와 재시도 안내 표시 |
| term card로 해결 불가 | 추가 질문을 저장하고 사용자 다음 입력을 기다림; 계속 해결하지 못하면 휴먼 피드백 필요 상태 |

## 6. 관측·보안·검증

LLM adapter는 Langfuse에 요청 ID, 모델, 프롬프트 버전, 입력/출력 계약 통과 여부, 토큰 수, 지연, 비용, 재시도를 기록한다. 평가셋은 최소 30건이며 정상·경계·실패 유도를 포함한다. 회귀는 카드 허용 목록, 역할 필터, URL fragment 전용 생성, 모호성 질문, 카드에 저장된 출처 노출, `/health`를 검증한다.

비밀값은 `.env`와 배포 Secret Manager에만 두며 UI와 git에 노출하지 않는다. `anonymous_user_id`, `session_id`, 세션 토큰 원문은 로그·trace에 남기지 않고 해시만 기록한다. 세션·chat·job 상태·구조화 결과·Pin URL과 상태는 Cloud SQL for PostgreSQL에 1개월 저장하고 Cloud Scheduler가 하루 한 번 만료 데이터를 삭제한다. 썸네일 URL과 이미지 바이트·Pin 메타데이터는 저장하지 않는다. 세션 쿠키는 배포에서 `HttpOnly`, `Secure=true`, `SameSite=Lax`로 설정한다. 로컬 HTTP 개발에서만 명시적 local 설정의 `Secure=false`를 허용하며 배포 설정에 재사용하지 않는다. `SameSite=Lax` 쿠키 MVP는 UI와 API를 같은 origin으로 제공하며, 개발 환경은 Vite proxy로 연결한다. Vercel UI와 별도 Cloud Run API의 교차 사이트 cookie 호출은 BFF 또는 별도 쿠키 정책을 확정하기 전까지 범위 밖이다. Pinterest 검색 API·비즈니스 계정은 후속 확인 전까지 provider 구현을 교체 가능하게 유지한다. `main`에는 직접 push하지 않고 개인 브랜치·PR·리뷰 흐름을 따른다.
