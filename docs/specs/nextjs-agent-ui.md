# Next.js Agent UI Spec

## Why

- **페르소나**: 캐주얼 캐릭터 일러스트 용어가 익숙하지 않은 초보 사용자
- **상황**: 자연어 설명을 제출하고 Agent의 비동기 해석 결과를 확인한다.
- **문제**: API가 비동기로 동작하므로 입력, polling, 질문, 부분 결과, 실패 상태를 일관되게 안내해야 한다.
- **측정 지표**: 유효 요청 제출 성공률 100%, 종결 Job polling 중단 100%, 실패·질문 상태 메시지 표시 100%

## Goal

- `POST /api/agent`와 `GET /api/jobs/{job_id}`를 동일 origin `/api` 경로로 호출한다.
- queued부터 종결 상태까지 현재 처리 상태를 표시한다.
- `completed`, `needs_clarification`, `partial_result`, `failed`를 API 계약에 맞게 표시한다.
- **Out of Scope**: FastAPI 직접 호출, 세션 토큰 저장, 이미지 업로드·생성, 사용자 retry endpoint

## What

**Happy Path**

1. 사용자가 1~500자의 자연어 설명을 입력한다.
2. UI가 UUID `Idempotency-Key`를 생성해 `/api/agent`로 제출한다.
3. `202`와 `job_id`를 받으면 `poll_after_ms` 간격으로 Job을 조회한다.
4. `completed`가 되면 용어 설명과 역할별 원본 Pin 링크를 표시한다.

**Edge Cases**

| 상황 | 처리 |
| --- | --- |
| 빈 입력 또는 500자 초과 | API 호출 없이 입력 오류 표시 |
| `needs_clarification` | `clarifying_question` 표시, 결과 영역은 표시하지 않음 |
| `partial_result` | 사용 가능한 용어와 실패 역할 안내를 함께 표시 |
| `failed` | `user_message`만 표시하고 내부 오류 원문은 표시하지 않음 |
| 세션 쿠키 없음 | `credentials: "include"`로 서버 발급 쿠키 수용 |

## How

- API base path: `NEXT_PUBLIC_API_BASE_URL=/api`
- 요청: `POST /api/agent`, body는 `request_text`만 포함
- 헤더: UUID 형식 `Idempotency-Key`
- polling: `GET /api/jobs/{job_id}`, `poll_after_ms` 사용
- 진행 상태: `queued | running | validating | searching | rendering`
- 종결 상태: `completed | failed`
- 결과 상태: `success | needs_clarification | partial_result | out_of_scope | unsafe_input`
- 브라우저 저장 금지: session token, anonymous user ID, 원문, Pin thumbnail URL
- Next.js rewrite가 동일 origin `/api/*`를 내부 FastAPI로 전달한다.

## AC

**AC-01 · 입력 검증**

- GIVEN: 사용자가 입력창에 값을 입력한다.
- WHEN: 값이 비어 있거나 1~500자 범위를 벗어난다.
- THEN: API를 호출하지 않고 입력 오류를 표시한다.

**AC-02 · 제출과 세션 쿠키**

- GIVEN: 1~500자의 유효한 입력이 있다.
- WHEN: 사용자가 제출한다.
- THEN: UUID `Idempotency-Key`와 `credentials: "include"`로 `/api/agent`를 호출하고 `202` 응답의 `job_id`를 사용한다.

**AC-03 · polling**

- GIVEN: Job이 진행 상태다.
- WHEN: UI가 Job을 조회한다.
- THEN: `poll_after_ms`를 사용해 polling을 계속하고 진행 상태를 표시한다.

**AC-04 · completed**

- GIVEN: Job 응답이 `completed`다.
- WHEN: UI가 응답을 받는다.
- THEN: 용어 설명과 원본 Pin 링크를 표시하고 polling을 중단한다.

**AC-05 · needs clarification**

- GIVEN: `agent_status=needs_clarification`이고 질문이 있다.
- WHEN: UI가 응답을 받는다.
- THEN: 질문을 표시하고 `reference_plan`은 표시하지 않는다.

**AC-06 · partial result**

- GIVEN: `agent_status=partial_result`다.
- WHEN: UI가 응답을 받는다.
- THEN: 사용 가능한 결과와 검색 실패 안내를 표시하고 polling을 중단한다.

**AC-07 · failed**

- GIVEN: Job이 `failed`다.
- WHEN: UI가 응답을 받는다.
- THEN: `user_message`만 표시하고 polling을 중단한다.
