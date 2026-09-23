# PRD — UH케그려

## Why

캐주얼 캐릭터 일러스트 초보자는 일상어로 원하는 체형·포즈·시점·원근·구도를 말하지만, 이를 검수된 탐색 용어로 바꾸기 어렵다. UH케그려는 텍스트 설명을 팀 관리 TERM_CARD와 Pinterest 탐색 계획으로 바꿔 여러 레퍼런스를 조합해 러프를 시작하도록 돕는다.

## Goal

- 자연어 설명을 `body`, `pose`, `view`, `perspective`, `layout`의 검수된 TERM_CARD로 해석한다.
- 카드의 용어, 쉬운 설명, 선택 근거, 확인 지점, 추가 질문을 제공한다.
- 역할별 Pinterest 결과와 원본 링크를 표시하되 이미지·썸네일 URL·Pin 메타데이터를 저장하거나 재게시하지 않는다.
- 모호한 입력에는 질문을, 일부 검색 실패에는 사용 가능한 부분 결과를, 최종 처리 실패에는 일반 장애 안내를 제공한다.

이미지 생성·편집·업로드 이미지 분석, 특정 작가 화풍 복제, Pinterest 크롤링, 이미지 파일·Pin 메타데이터 저장·재게시, 외부 어휘 조회·RAG 주입은 범위 밖이다.

## What

1. 브라우저는 서버 세션과 HttpOnly 쿠키를 받고 자연어 메시지를 전송한다.
2. 서버는 비동기 job을 만들고 프론트는 종결 상태까지 polling한다.
3. LLM은 활성 TERM_CARD ID 후보와 근거만 구조화 출력한다.
4. 서버는 JSON 카탈로그에서 로드한 활성 카드·역할·조건을 검증한다.
5. 유효 카드의 `query_fragments`만 결정론 검색어 조립기에 전달하고, 조립기는 고정 접미사 `drawing`을 한 번 붙여 역할별 결과를 조립한다.
6. 검색이 일부 실패해도 유효 카드가 있으면 용어·설명·검색 URL과 실패 안내를 반환한다.

## How

### TERM_CARD 계약

- `docs/domains/illustration-reference/term-cards/index.json`과 index가 선언한 5개 역할 JSON은 런타임 단일 원본이다.
- 앱 시작 시 카탈로그를 검증하고 활성 카드만 메모리에 로드한다. 요청 중 JSON을 다시 읽지 않는다.
- 활성 카드 수는 고정하지 않고 `runtime_eligible=true && mvp_status=active_in_current_contract` 조건으로 동적으로 계산한다.
- 카탈로그 오류는 ready 실패로 처리하며 job worker를 시작하지 않는다.

### 사용자 결과 계약

- 사용자 의미 상태는 `success`, `needs_clarification`, `out_of_scope`, `unsafe_input`, `partial_result`다.
- LLM·검색 provider·worker의 회복 가능한 오류는 같은 job에서 최초 실행 포함 최대 3회 자동 재시도한다.
- 검색 재시도 소진 뒤 유효 카드가 있으면 `partial_result`로 용어·검색 URL과 검색 실패 안내를 제공한다.
- 최종 실패는 API failure code를 포함할 수 있지만 UI는 “현재 요청을 처리하지 못했습니다. 잠시 후 새 메시지로 다시 시도해 주세요.”만 표시한다.

## AC

1. **Given** 유효 입력, **When** 해석하면, **Then** 모든 선택 term ID는 메모리에 로드된 활성 카드에 존재한다.
2. **Given** 카드 카탈로그 구조 오류, **When** 앱을 시작하면, **Then** ready 상태와 worker 시작을 거부한다.
3. **Given** 단서 부족 입력, **When** 처리하면, **Then** `needs_clarification`과 질문 하나를 반환한다.
4. **Given** 유효 카드와 검색 provider 재시도 소진, **When** 결과를 조립하면, **Then** `partial_result`와 검색 실패 역할의 빈 pins를 반환한다.
5. **Given** 최종 worker 실패, **When** job을 조회하면, **Then** failure code는 API에 제공하고 UI는 일반 실패 문구만 표시한다.
