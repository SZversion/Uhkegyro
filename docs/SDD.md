# SDD — UH케그려 MVP 아키텍처

## 1. TERM_CARD 카탈로그

`term-cards/index.json`과 index가 선언한 역할별 JSON이 TERM_CARD의 런타임 단일 원본이다. 시작 시 선언 순서대로 파일 존재, JSON 파싱, 전역 고유 ID, 역할, 필수 필드, 활성 조건, 활성 카드의 검색 조각을 검증한다. 성공하면 활성 카드를 메모리 사전과 역할별 목록에 로드한다. 카드 수와 활성 카드 수의 특정 값은 검증하지 않는다.

카탈로그 검증 실패는 `CATALOG_INVALID_AT_STARTUP` 운영 원인으로 기록하고 ready 상태와 worker 시작을 거부한다. 요청 처리 중 JSON은 다시 읽지 않으며 TERM_CARD를 DB에 적재하지 않는다.

## 2. 컴포넌트와 책임

```text
Next.js UI
  -> POST /api/agent
  -> GET /api/jobs/{job_id} polling

FastAPI route -> job queue/worker -> LLM adapter -> Pydantic candidate validation
                                             -> FastMCP get_active_term_card -> Card resolver
                                             -> Search provider -> response assembler
FastMCP startup -> JSON catalog validation -> immutable active-card memory
```

| 컴포넌트 | 책임 | 금지 |
| --- | --- | --- |
| Next.js UI | `/api/agent` 제출, polling, 결과·질문·일반 실패 표시 | LLM/MCP 직접 호출, 비밀값·카드 결정 |
| FastAPI route | 쿠키 소유권, 요청 검증, job 생성/조회 | 도메인 해석 |
| LLM adapter | 카드 후보·근거·모호성 신호 생성 | 자유 term ID·검색 URL·최종 상태 결정 |
| FastMCP TERM_CARD tool | 시작 검증을 통과한 JSON 메모리에서 활성 카드 한 건을 구조화 조회 | 외부 어휘 병합·새 카드 생성·검색 실행 |
| Card resolver | MCP가 반환한 카드의 역할·활성·조건을 재검증 | 외부 어휘 병합 |
| PinterestCrawlerProvider | 활성 카드의 검증된 검색 조각으로 공개 Pinterest 검색을 크롤링하고, 수집한 Pin ID를 widget endpoint로 조회해 Pin 결과 반환 | API v5 사용, 브라우저 직접 호출, 이미지·썸네일 URL 저장 |
| Response assembler | 상태·카드 피드백·Pin 결과 조립 | 오류 원문·비밀값 노출 |

## 3. 비동기 job과 실패

메시지 제출은 `202`와 queued job을 반환한다. job은 `queued → running → validating → searching → rendering → completed` 또는 `failed`로 전이하며 종결 뒤 바뀌지 않는다.

LLM timeout/429/일시적 5xx·구조화 출력 오류, PinterestCrawlerProvider의 공개 검색·widget timeout/차단/일시적 5xx, worker 중단은 최초 실행 포함 최대 3회 자동 재시도한다. 설정·migration·결정적 코드 오류는 즉시 `failed`와 운영 알림으로 끝낸다.

유효 카드가 있으면 PinterestCrawlerProvider의 검색 또는 widget 실패가 소진돼도 `completed + partial_result`로 조립한다. 실패 역할은 빈 pins와 `PIN_SEARCH_UNAVAILABLE` reason code를 가진다. widget이 이미지 URL을 주지 않은 경우는 실패가 아니라 `thumbnail_unavailable` 상태와 원본 `pin_url`을 유지한다. 0건은 `PIN_RESULTS_EMPTY`이며 재시도하지 않는다. 단서 부족은 `completed + needs_clarification`이며 후속 메시지가 새 job을 만든다.

## 4. API·프론트 경계

정확한 endpoint, Pydantic 모델, 상태 enum, failure code는 [api-contract.md](./specs/api-contract.md)가 단일 기준이다. UI는 Next.js이며 `NEXT_PUBLIC_API_BASE_URL=/api`, `credentials:"include"`, HttpOnly same-origin 세션 쿠키를 사용한다. 브라우저의 `/api/*` 요청은 Next.js rewrite를 거쳐 내부 FastAPI로 전달하며, FastAPI origin 직접 호출·cross-origin credential cookie·Vite proxy는 사용하지 않는다. 요청·응답 변환이 필요해질 때만 Next.js Route Handler BFF를 추가한다. `/mcp`는 브라우저가 직접 호출하지 않는 Streamable HTTP 도구 endpoint이며, 계약은 [mcp-contract.md](./specs/mcp-contract.md)가 단일 기준이다. `pinit.js`, 사용자 retry endpoint는 사용하지 않는다.

## 5. 데이터·보안·관측

세션·chat·job 이력 저장소는 TERM_CARD 카탈로그와 분리한다. `PinterestCrawlerProvider`는 서버에서만 실행하고 활성 카드의 `query_fragments`만 검색 URL에 사용한다. 세션·job 이력에 포함된 결과의 `pin_url`과 `status`는 유지하되, 이를 위한 별도 Pin 저장소는 만들지 않는다. widget의 이미지 바이트·`thumbnail_url`과 부가 Pin 필드는 저장·LLM 입력·trace·로그에 사용하지 않는다. trace에는 요청 원문 해시, 세션 ID 해시와 비밀이 아닌 안전한 운영 필드만 남긴다. 세션 쿠키 토큰 원문과 그 해시는 trace·로그에 남기지 않는다.

## 6. 검증

- JSON 카탈로그 시작 검증 실패 시 fail-closed
- 활성 카드 외 term ID·역할 불일치·자유 검색어 거부
- 자동 재시도, 검색 부분 결과, 최종 failure code, 질문 job을 계약 평가로 검증
- 삭제된 문서와 링크의 잔존 참조를 0건으로 검증
