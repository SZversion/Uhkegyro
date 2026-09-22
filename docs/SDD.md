# SDD — UH케그려 MVP 아키텍처

## 1. TERM_CARD 카탈로그

`term-cards/index.json`과 index가 선언한 역할별 JSON이 TERM_CARD의 런타임 단일 원본이다. 시작 시 선언 순서대로 파일 존재, JSON 파싱, 전역 고유 ID, 역할, 필수 필드, 활성 조건, 활성 카드의 검색 조각을 검증한다. 성공하면 활성 카드를 메모리 사전과 역할별 목록에 로드한다. 카드 수와 활성 카드 수의 특정 값은 검증하지 않는다.

카탈로그 검증 실패는 `CATALOG_INVALID_AT_STARTUP` 운영 원인으로 기록하고 ready 상태와 worker 시작을 거부한다. 요청 처리 중 JSON은 다시 읽지 않으며 TERM_CARD를 DB에 적재하지 않는다.

## 2. 컴포넌트와 책임

```text
Next.js UI
  -> POST /api/sessions
  -> POST /api/sessions/{session_id}/messages
  -> GET /api/jobs/{job_id} polling

FastAPI route -> job queue/worker -> LLM adapter -> Card resolver -> Search provider -> response assembler
                                         ^
                              JSON catalog memory lookup
```

| 컴포넌트 | 책임 | 금지 |
| --- | --- | --- |
| Next.js UI | 세션 생성, 메시지 전송, polling, 결과·질문·일반 실패 표시 | LLM/MCP 직접 호출, 비밀값·카드 결정 |
| FastAPI route | 쿠키 소유권, 요청 검증, job 생성/조회 | 도메인 해석 |
| LLM adapter | 카드 후보·근거·모호성 신호 생성 | 자유 term ID·검색 URL·최종 상태 결정 |
| Card resolver | 메모리 카탈로그의 역할·활성·조건 검증 | 외부 어휘 병합 |
| Search provider | 검증된 검색 조각으로 Pin 결과 반환 | 크롤링·이미지 저장 |
| Response assembler | 상태·카드 피드백·Pin 결과 조립 | 오류 원문·비밀값 노출 |

## 3. 비동기 job과 실패

메시지 제출은 `202`와 queued job을 반환한다. job은 `queued → running → validating → searching → rendering → completed` 또는 `failed`로 전이하며 종결 뒤 바뀌지 않는다.

LLM timeout/429/일시적 5xx·구조화 출력 오류, 검색 provider timeout/429/일시적 5xx, worker 중단은 최초 실행 포함 최대 3회 자동 재시도한다. 설정·migration·결정적 코드 오류는 즉시 `failed`와 운영 알림으로 끝낸다.

유효 카드가 있으면 검색 provider 실패가 소진돼도 `completed + partial_result`로 조립한다. 실패 역할은 빈 pins와 `PIN_SEARCH_UNAVAILABLE` reason code를 가진다. 0건은 `PIN_RESULTS_EMPTY`이며 재시도하지 않는다. 단서 부족은 `completed + needs_clarification`이며 후속 메시지가 새 job을 만든다.

## 4. API·프론트 경계

정확한 endpoint, Pydantic 모델, 상태 enum, failure code는 [api-contract.md](./specs/api-contract.md)가 단일 기준이다. UI는 Next.js이며 `NEXT_PUBLIC_API_BASE_URL`, `credentials:"include"`, HttpOnly same-origin 세션 쿠키를 사용한다. Vite proxy, `pinit.js`, 사용자 retry endpoint는 사용하지 않는다.

## 5. 데이터·보안·관측

세션·chat·job 이력 저장소는 TERM_CARD 카탈로그와 분리한다. Pin URL과 상태는 보관할 수 있으나 이미지 바이트·썸네일 URL·Pin 메타데이터·LLM 원문 응답은 저장하지 않는다. trace에는 요청 원문·토큰·비밀값 대신 해시와 안전한 운영 필드만 남긴다.

## 6. 검증

- JSON 카탈로그 시작 검증 실패 시 fail-closed
- 활성 카드 외 term ID·역할 불일치·자유 검색어 거부
- 자동 재시도, 검색 부분 결과, 최종 failure code, 질문 job을 계약 평가로 검증
- 삭제된 문서와 링크의 잔존 참조를 0건으로 검증
