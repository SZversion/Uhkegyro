# PRD — UH케그려

## Why

캐주얼 캐릭터 일러스트 초보자는 원하는 체형·포즈·시점·구도를 일상어로 표현하지만, 이를 탐색 가능한 드로잉 용어로 바꾸기 어렵다. UH케그려는 1~500자 텍스트 설명을 역할별 전문 용어와 Pinterest 외부 탐색 계획으로 바꿔, 한 장의 정답 이미지를 찾는 대신 여러 레퍼런스를 조합해 러프를 시작하도록 돕는다.

성공은 최소 30건의 정상·경계·실패 유도 평가셋에서 계약 준수율, 완료율, p50/p95 지연, 요청당 비용, LLM·MCP 오류율을 측정하고, 같은 평가셋으로 변경 전후를 비교해 판단하는 것이다.

## Goal

- 설명을 `body`, `pose`, `view`, `perspective`, `layout`로 구조화한다.
- 초보자용 설명, 선택 근거, 확인 지점, 혼동 안내, 추가 질문을 카드 데이터에 따라 제공한다.
- Agent가 선택한 역할별로 Pinterest 검색 결과 상위 8개 Pin을 표시한다. 기본값 8은 설정으로 변경 가능하다.
- Pin 이미지 바이트·썸네일 URL·Pin 메타데이터는 저장하지 않는다. 화면에는 검색 provider가 반환한 원격 썸네일을 원본 Pin 링크로 표시한다.
- 사용자가 입력을 계속하는 하나의 chat 세션에 대화와 검색 결과를 누적한다.
- LLM 출력은 프로젝트 자체 TERM_CARD DB의 현재 런타임 허용 카드만 사용한다. 역할별 JSON은 DB 적재 전 검수·시드 자료이며, 런타임 조회 원본이 아니다.

이미지 생성·편집·업로드 이미지 분석, 특정 작가 화풍 복제, Pinterest 이미지 파일·썸네일·메타데이터 저장·재게시, 카드 자동 생성·수정, 동적 외부 후보의 RAG 주입은 범위 밖이다. Pinterest 검색 결과를 가져오는 검색 제공자는 비즈니스 계정·API 확인 전까지 미정으로 둔다.

## What

1. 사용자가 사진 없이 자연어 텍스트를 Agent chat에 입력한다.
2. LLM은 카드 목록 안의 `term_id`만 선택해 `body`, `pose`, `view`, `perspective`, `layout`별 구조화 JSON을 만든다.
3. 코드가 JSON 형식, 활성 카드, 역할, confidence/requires 조건을 검증한다.
4. 검증되면 검색 도구가 역할별 검색을 수행하고 각 역할의 상위 8개 `{pin_url, thumbnail_url, status}`를 반환한다. 같은 Pin이 여러 역할에 나오면 중복 표시한다.
5. 프론트엔드는 역할별 섹션에서 원격 `thumbnail_url`을 원본 `pin_url` 링크로 표시한다. 썸네일 URL이 없으면 링크만 제공하며, 이미지 바이트·썸네일 URL·Pin 메타데이터는 저장하지 않는다.
6. 검색 결과가 0개이면 해당 역할에 `검색 결과가 없습니다`를 표시한다. Pin 삭제가 확인되면 `이 Pin은 삭제되었습니다`를 표시하고 결과에서 제외한다. 검색 시스템 오류는 오류와 재시도 안내를 표시한다.
7. 사용자가 후속 chat에서 특정 결과는 남기고 다시 찾으라고 하면, 지정한 Pin URL은 세션 결과에 유지하고 해당 역할만 다시 검색한다.
8. 활성 카드로 해석할 수 없으면 Agent가 부족한 정보를 명확히 설명하고 질문하며, 사용자의 다음 입력을 기다린다. 해결하지 못한 경우 휴먼 피드백 필요 상태로 표시한다.

현재 구현되어 동작하는 공개 API는 `GET /health`의 `{"status":"ok"}`뿐이다. Agent API, UI, 실제 MCP, Langfuse 관측은 목표 MVP다.

## How

### TERM_CARDS 계약

- 데이터셋: `illustration_reference_master_term_cards`, 버전 `0.6-self-managed-term-card-store-draft`, 총 74개 시드 카드. 역할별 JSON은 자체 TERM_CARD DB 적재 전의 검수·시드 자료이며, 구현 후 런타임 단일 원본은 자체 DB다.
- 현재 선택 가능 조건: `runtime_eligible=true` **그리고** `mvp_status=active_in_current_contract`.
- 현재 선택 가능 카드는 20개이며 역할별로 `body` 5, `pose` 7, `view` 4, `perspective` 3, `layout` 1개다.
- `runtime_eligible=false` 카드는 API·UI·검색 결과에 노출하지 않는다. `detail`, `intent`, `style`은 현재 MVP 데이터셋과 역할별 파일에서 제외한다.
- 카드의 `confidence_gate`, `requires_all_of`, `requires_any_of`를 만족하지 않으면 선택하지 않는다.

### 품질·안전 원칙

- LLM은 의미 해석만 한다. 허용 ID 검증, 카드 로딩, 역할 순서, 링크 생성, URL 인코딩, 실패 응답은 결정론 코드가 맡는다.
- TERM_CARD는 팀이 작성·검수한 자체 DB의 단일 원본이다. Getty는 용어 조사 시 참고한 자료일 뿐 서비스 DB·사용자 응답·런타임 도구 출처가 아니다. 외부 API·provider 결과·참고 자료가 새 `term_id`가 되거나 LLM에 자동 주입되면 안 된다.
- 모호·상충 입력은 단정하지 않고 낮은 확신도, 한계, `pending_human_review`, 또는 추가 질문으로 처리한다.
- 비밀값은 UI에 노출하지 않으며 `.env`만 사용한다. MCP는 무제한 공개 endpoint로 제공하지 않는다.
- 사용자·LLM chat과 검색 이력은 Cloud SQL for PostgreSQL에 1개월 보관하고 하루 한 번 만료 데이터를 삭제한다. `anonymous_user_id`는 브라우저 로컬 저장소의 비식별 UUID이며, `session_id`는 탭 단위 UUID로 요청마다 전달한다.

## AC

1. **Given** 유효한 설명과 역할, **When** Agent가 해석하면, **Then** 응답의 모든 `term_id`는 현재 런타임 허용 카드에 존재한다.
2. **Given** 카드 밖·비활성 카드·잘못된 역할, **When** 결정론 검증을 수행하면, **Then** 해당 값은 응답과 링크에서 제거되고 폴백 또는 실패 응답이 반환된다.
3. **Given** 카드 선택, **When** 검색 도구를 호출하면, **Then** 해당 카드의 `query_fragments`만 검색 입력으로 사용하고 역할별 최대 8개의 `{pin_url, thumbnail_url, status}`를 반환한다.
4. **Given** 단서 부족 또는 충돌 입력, **When** 해석하면, **Then** 용어·링크를 추측하지 않고 카드 기반 추가 질문 또는 `pending_human_review`를 반환한다.
5. **Given** 특정 역할만 선택, **When** 링크를 만들면, **Then** 미선택 역할의 개별 링크는 없다.
6. **Given** 활성 자체 DB 카드, **When** 결과를 표시하면, **Then** 팀이 작성·검수한 용어·설명·선택 근거만 표시하고 Getty 데이터·URI·귀속 정보를 표시하거나 조회하지 않는다.
7. **Given** 상태 점검, **When** `GET /health`를 호출하면, **Then** `{"status":"ok"}`를 반환한다.
8. **Given** 활성 카드가 선택된 역할, **When** 검색이 완료되면, **Then** 해당 역할 섹션에 최대 8개의 Pin 미리보기를 표시한다.
9. **Given** 사용자가 후속 chat으로 일부 역할만 다시 검색하라고 하면, **When** Agent가 처리하면, **Then** 지정된 Pin은 유지하고 요청된 역할의 새 결과만 누적한다.
10. **Given** Cloud Run 작업이 중단되면, **When** 상태를 조회하면, **Then** 사용자에게 실패 상태와 재시도 안내를 표시한다.
