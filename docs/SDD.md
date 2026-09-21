# SDD — UH케그려 MVP 아키텍처

## 1. 기준 데이터와 불변 조건

`docs/domains/illustration-reference/TERM_CARDS_MASTER_100_DRAFT.json`은 LLM 출력·화면 피드백·Pinterest 검색어의 단일 원본이다. 런타임 시작 시 JSON을 한 번 로드하여 `runtime_eligible=true && mvp_status=active_in_current_contract` 카드만 `term_id` 사전으로 만든다. 현재 활성 20개 역할 분포는 body 5, pose 7, view 4, perspective 3, layout 1이다.

모든 선택 결과는 이 사전에 존재해야 하며, 원본 카드의 `role`, `label_ko`, `label_en`, `query_fragments`, `look_for`, `confidence_gate`, `requires_all_of`, `requires_any_of`, `source_type`, `getty_aat`, 초보자 피드백을 변경 없이 참조한다. 카드 파일 밖의 자유 형식 용어, 검색어, 외부 Getty 후보는 런타임 선택 경로에 들어갈 수 없다.

## 2. 컴포넌트와 책임

```text
React + Vite UI
  -> POST /api/sessions (서버 발급 토큰·HttpOnly 쿠키)
  -> Agent 메시지 API (명세 미정, 비동기 job 생성)
  -> 작업 상태 API (명세 미정)
       -> Request validator
       -> LLM adapter (구조화 후보만 생성)
       -> Card resolver (활성 카드·제약 검증)
       -> Response assembler (피드백·출처·상태 조립)
       -> PinterestSearchProvider (교체 가능한 검색 구현)
       -> Result assembler (역할별 최대 8 Pin URL)
  <- GET /api/jobs/{job_id} 결과
       -> pinit.js embedPin 렌더링

TERM_CARDS_MASTER_100_DRAFT.json -> Card repository -> Card resolver
FastMCP -> LLM이 필요하다고 판단한 도구 호출을 중계 (도구 목록·계약 미정)
Langfuse <- LLM adapter의 요청 ID·모델·토큰·지연·비용·재시도
```

| 컴포넌트 | 책임 | 금지 |
| --- | --- | --- |
| UI | chat 입력, 세션 목록, 역할별 Pin 섹션, `pinit.js` 렌더링, 상태·오류·재시도 표시 | 이미지 파일 저장, 키 보유, LLM 직접 호출 |
| FastAPI route | HTTP 경계, Pydantic 요청/응답 검증 | 도메인 규칙·SDK 호출 분산 |
| LLM adapter | 카드 ID 후보·모호성·질문 필요 상태 생성 | 카드 밖 ID, 자유 검색어·URL 생성 |
| Card repository | JSON 로드, 활성 사전·역할별 인덱스 제공 | 카드 변경, 외부 후보 병합 |
| Card resolver | ID·역할·confidence/requires 검증 | 의도 추측, 출처 조작 |
| URL builder | 카드 fragment 순서 보존, 공백·특수문자 URL 인코딩 | 일상어·설명문·추상 intent 추가 |
| FastMCP | 모든 도구를 담는 실행 틀; 도구 목록·계약 확정 후 등록하고 LLM 요청에 따라 호출 중계 | 카드 밖 term 제안, 이미지 파일 저장 |
| PinterestSearchProvider | FastMCP에 등록되는 검색 도구 구현. 활성 카드의 `query_fragments`로 검색하고 Pin URL·상태 반환 | 이미지 다운로드·썸네일 저장 |
| Session repository | chat·구조화 결과·Pin URL·상태를 Cloud SQL에 1개월 저장 | 이미지 바이너리 저장 |

## 3. API 계약의 강제성

정확한 공개 API 명세는 현재 미정으로 둔다. 아래 endpoint와 흐름은 아키텍처 경계와 책임을 설명하기 위한 참고안이며, 실제 구현 전 별도 API Spec에서 request/response 필드, HTTP 상태 코드, 오류 코드, 인증 헤더·쿠키 계약, pagination, polling 간격·종료 조건을 확정한다. API Spec이 확정되기 전에는 구현자가 임의의 공개 계약을 추가하지 않는다.

### 필수 계약(구현 전 반드시 확정)

공개 API 경로·메서드·필드·상태 코드는 아직 미정이다. 구현 전 별도 API 명세서에서 확정하기 전까지 구현자는 공개 endpoint나 필드를 추가·변경해서는 안 된다. 필수 기능 경계는 세션 생성/조회, Agent 메시지 제출, 비동기 작업 상태 조회, health check이며, 상세 contract는 API 명세서가 유일한 기준이다.

서버는 HttpOnly 쿠키의 불투명 토큰을 검증하고 토큰 소유자와 `session_id`의 소유권을 확인해야 한다. 토큰이 없거나 만료되면 새 세션 생성 흐름으로 유도하며, 다른 사용자의 세션을 조회·변경할 수 없어야 한다. `role`은 클라이언트가 권한·검색 범위를 정하는 값으로 전달하지 않으며, LLM의 카드 선택과 서버의 카드 `role` 검증으로만 결정한다.

### 참고안(확정 전 구현 금지)

다음은 설계 방향일 뿐 공개 contract가 아니다: 텍스트 메시지 1~500자, 서버 발급 `session_id`, 쿠키 기반 인증, 작업 `job_id`와 polling, 역할별 결과 누적. API 명세서가 확정되기 전에는 이 이름·길이·경로를 외부에 노출하거나 이를 근거로 구현하지 않는다.

### LLM 내부 출력

- `selections`: `{role, term_id, confidence}` 목록. 역할은 LLM이 활성 카드 목록에서 선택한다.
- `needs_clarification`: boolean 및 선택 이유.
- LLM은 활성 카드 ID만 출력하도록 프롬프트와 structured-output enum으로 제한한다. 출력 후에도 resolver가 독립 검증한다.
- `needs_clarification=true` 또는 ID 검증 실패이면 용어·링크 조립을 중단하고 질문 경로로 전환한다.

### 비동기 작업 필수 운영 정책

Agent 메시지 제출 API(경로·계약 미정)는 사용자 메시지를 저장하고 작업 식별자를 반환해야 한다. 작업 레코드는 Cloud SQL에 상태 전환과 실패 원인을 기록한다. Cloud Run 인스턴스 종료, 작업 timeout, 처리 예외로 정상 완료하지 못한 작업은 `failed`로 종결하며, 클라이언트는 원인에 맞는 실패 메시지와 사용자 재시도 안내를 표시한다. 자동 재시도는 금지한다.

정상 흐름은 `queued → running → validating → searching → rendering → completed` 참고안으로 둔다. `failed`는 timeout·인스턴스 종료·검색/렌더링 장애·검증 외의 처리 예외를 포함하는 종결 상태다. 사용자가 재시도하면 새 작업을 생성하고 원래 작업의 입력·실패 원인을 연결해 기록하며, 이미 저장된 결과는 중복 생성하지 않는다. 후속 chat은 기존 세션의 전체 대화와 보존된 결과를 문맥으로 사용한다.

### 검증 기준

- API 명세서 확정 전에는 참고안의 경로·필드·상태를 필수 contract로 취급하지 않는다.
- 모든 요청은 쿠키 토큰과 세션 소유권을 서버에서 검증한다.
- 클라이언트가 전달할 수 있는 값은 자연어 텍스트와 명세서가 허용한 세션 참조뿐이며, `role`·`term_id`·검색어·Pin URL을 결정할 수 없다.
- `failed` 작업은 상태, 실패 범주, 사용자 메시지, 재시도 가능 여부를 기록하고 자동 재시도하지 않는다.

### 세션 저장

세션 레코드는 `session_id`, 토큰 해시, 생성 시각, 마지막 활동 시각, 만료 시각, 세션 상태, 최근 대화 요약을 가진다. 메시지 레코드는 사용자 메시지, 구조화 JSON, 검증 결과, 모델명·프롬프트 버전, 생성 시각을 가진다. 검색 결과 레코드는 메시지·역할·term_id·Pin URL·`active|deleted|no_results|search_error` 상태·생성 시각을 가진다. 이미지 바이너리, 썸네일, LLM 원문 응답은 저장하지 않는다.

### 응답

작업 결과는 세션의 기존 결과와 누적한다. 역할별 항목은 카드 정보와 최대 8개의 `{pin_url, render_status}`를 담는다. 같은 Pin URL이 여러 역할에 있으면 중복을 유지한다. 이미지는 저장하지 않으며, React+Vite가 각 URL을 `pinit.js` `embedPin`으로 렌더링한다.

## 4. 상세 처리 순서

1. 앱 시작 시 Card repository가 JSON의 `card_count=100`과 필수 필드를 검증한다. 실패하면 앱을 ready 상태로 만들지 않고 운영자 오류로 기록한다.
2. repository는 활성 20개 카드만 인덱싱하고, 후보·미검수 카드는 메모리 모델에서 제외한다.
3. API 명세서가 확정되면 route가 그 명세서의 입력 규칙과 쿠키·세션 소유권을 검증하고 요청 ID를 생성한다.
4. LLM adapter는 활성 카드의 ID·role·confidence gate만 근거로 구조화 후보를 생성한다.
5. resolver는 (a) 선택 역할 여부, (b) 활성 사전 존재 여부, (c) 카드 role 일치, (d) `confidence_gate`, (e) `requires_all_of` 전체 충족, (f) `requires_any_of` 중 하나 충족을 검증한다.
6. 단서가 없거나 검증을 통과하지 못하면 해당 역할에 카드를 선택하지 않고 카드의 `clarifying_question_ko` 또는 일반 확인 상태를 반환한다.
7. 유효 카드마다 response assembler가 카드 JSON에 저장된 원문 피드백과 출처를 조립한다. `getty_aat`가 존재하면 해당 카드의 AAT URI·label·attribution을 그대로 표시하며, 외부 조회나 보강은 하지 않는다.
8. URL builder는 선택 카드의 `query_fragments` 배열만 합쳐 Pinterest 검색 URL을 만든다. `direct_search_disabled_term_ids`에 해당하면 링크를 만들지 않는다.
9. PinterestSearchProvider가 역할별 결과를 반환하면 삭제된 Pin은 `deleted` 상태로 표시하고 화면에 `이 Pin은 삭제되었습니다`를 남긴 뒤 렌더링 대상에서 제외한다. 0건은 `no_results`, 검색 장애는 `search_error`와 재시도 안내로 구분한다.
10. 작업이 Cloud Run 종료로 중단되면 job을 `failed`로 기록하고 클라이언트에 상태와 재시도 안내를 반환한다. 자동 재시도는 하지 않는다.

## 5. 실패와 폴백

| 실패 | 응답/운영 처리 |
| --- | --- |
| JSON 누락·파싱 실패·스키마 불일치 | 서비스 준비 실패, 운영 로그 기록; 빈 허용 목록으로 실행 금지 |
| 입력 계약 위반 | 검증 오류; LLM·MCP를 호출하지 않음 |
| LLM timeout/형식 오류 | 자동 재시도 없이 카드 선택 없이 `failed` 기록; 사용자 재시도 가능 상태와 trace 기록 |
| 카드 밖 또는 비활성 ID | resolver가 폐기; 링크 생성 금지 |
| 단서 부족·상충 | 추측 금지, 질문 또는 `pending_human_review` |
| 카드 출처 필드 누락 | 해당 카드의 누락을 검증 오류로 기록하고, 외부 출처를 생성·조회하지 않음 |
| Pinterest URL 생성 불가 | URL 생략 및 사유 표시; 대체 자유 문장 URL 금지 |
| 검색 결과 0건 | 해당 역할에 `no_results`와 `검색 결과가 없습니다` 표시 |
| Pin 삭제 | URL은 세션 이력에 남기되 `deleted` 상태와 `이 Pin은 삭제되었습니다` 표시 |
| 검색 시스템 오류 | `search_error`와 재시도 안내 표시 |
| term card로 해결 불가 | 추가 질문을 저장하고 사용자 다음 입력을 기다림; 계속 해결하지 못하면 휴먼 피드백 필요 상태 |

## 6. 관측·보안·검증

LLM adapter는 Langfuse에 요청 ID, 모델, 프롬프트 버전, 입력/출력 계약 통과 여부, 토큰 수, 지연, 비용, 재시도를 기록한다. 평가셋은 최소 30건이며 정상·경계·실패 유도를 포함한다. 회귀는 카드 허용 목록, 역할 필터, URL fragment 전용 생성, 모호성 질문, 카드에 저장된 출처 노출, `/health`를 검증한다.

비밀값은 `.env`와 배포 Secret Manager에만 두며 UI와 git에 노출하지 않는다. 세션 토큰은 서버가 발급하는 불투명 랜덤 값이며 HttpOnly 쿠키로 전달한다. 세션·chat·구조화 결과·Pin URL은 Cloud SQL for PostgreSQL에 1개월 저장하고 Cloud Scheduler가 하루 한 번 만료 데이터를 삭제한다. Cloud Run CORS는 개발 중 localhost와 Vercel 도메인을 허용하고 배포 시 Vercel 도메인만 허용한다. Pinterest 검색 API·비즈니스 계정은 후속 확인 전까지 provider 구현을 교체 가능하게 유지한다. `main`에는 직접 push하지 않고 개인 브랜치·PR·리뷰 흐름을 따른다.
