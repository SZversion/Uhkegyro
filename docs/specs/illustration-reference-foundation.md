> **2026-09-22 폐기됨:** 아래 본문은 초기 골조·동기 단일 응답·브라우저 생성 식별자 계약의 이력이며, 구현·실행·평가 기준으로 사용하지 않는다. 현행 MVP는 서버 세션 쿠키와 비동기 job을 사용하는 `docs/PRD.md`, `docs/SDD.md`, [`frontend-api-contract.md`](./frontend-api-contract.md), [`illustration-reference-current-failure-state-contract.md`](./illustration-reference-current-failure-state-contract.md)의 자체 TERM_CARD DB 계약을 따른다.

# 캐주얼 캐릭터 일러스트 레퍼런스 Agent — 기반 골조 Spec

## Why

- **페르소나**: 캐주얼 캐릭터를 처음 그리며 체형/소체, 포즈, 구도 용어가 낯선 사용자
- **상황**: 텍스트로 원하는 캐릭터를 설명하고, 실제로 언급한 조건만 바탕으로 레퍼런스를 탐색하고 싶다.
- **문제**: 현재 저장소는 강의용 빈 FastAPI/MCP 뼈대만 있어 용어 ID, 역할 순서, 요청 형식, 검색 URL 생성 규칙이 코드로 고정되어 있지 않다.
- **측정 지표**: 기반 단위 테스트에서 허용되지 않은 용어/축 조합을 100% 거부하고, 선택된 역할만 정해진 순서로 검색 계획에 포함한다.

## Goal

- **해결 목표**: 이후 LLM·정적 카드 검증 MCP·UI가 같은 계약을 사용할 수 있도록 FastAPI health check, Pydantic 요청/선택 모델, 자체 관리 정적 용어 카드, 도메인 검증, Pinterest 검색 URL 생성 함수를 구현한다.
- **성공 기준**: `/health`가 서비스 상태를 반환하고, 입력 길이/추가 필드/UUID 형식과 term ID·축·구도 하위 역할을 검증한다. 유효한 LLM 선택은 팀 카드 정보와 함께 `body → pose → view → perspective → layout` 순서의 URL 계획으로 변환한다.
- **Out of Scope**: OpenAI 또는 Langfuse 호출, LLM 해석, PostgreSQL TERM_CARD DB의 실제 적재·마이그레이션, Pinterest HTTP 요청·스크래핑·이미지 표시, Next.js UI, Docker Compose 확장, 배포, 평가 데이터 업로드, Getty 데이터·외부 어휘 API·SPARQL·웹 호출.

## What

**Happy Path**

1. 클라이언트 요청 계약은 1~500자 `request_text`와 UUID 형식의 익명 사용자/세션 ID를 받는다.
2. 검증된 `body`, `pose`, `view`, `perspective`, `layout` 선택만 정적 용어 카드와 대조한다.
3. 선택된 역할만 고정 역할 순서로 정렬하고, 역할별 Pinterest 검색 URL과 통합 검색 URL을 결정론적으로 생성한다.
4. `/health`는 API가 실행 중임을 반환한다.
5. FastMCP 파이프라인은 각 유효 term ID를 팀이 관리하는 정적 카드와 대조하고, 카드가 없거나 저장소가 없으면 결정론적 실패 상태를 반환한다.

**Edge Cases**

| # | 상황 | 처리 방식 |
|---|---|---|
| EC-01 | 빈 문자열 또는 501자 입력 | Pydantic 요청 검증에서 거부한다. |
| EC-02 | 허용 목록 밖 term ID | 도메인 검증에서 거부한다. |
| EC-03 | `body` term을 `pose` 축으로 전달 | 도메인 검증에서 거부한다. |
| EC-04 | `view`와 `perspective`를 함께 선택 | 서로 다른 역할로 유지하고 둘 다 포함한다. |
| EC-05 | 체형이 없는 포즈 요청 | 빈 체형 역할을 만들지 않고 포즈부터 검색 계획을 만든다. |

## How

- Python 3.11 이상, FastAPI, Pydantic v2, pytest를 사용한다.
- `backend/app/schemas.py`는 API 요청과 내부 선택/검색 항목의 Pydantic 계약을 둔다.
- `backend/app/domain/term_cards.py`는 허용된 term ID와 축·역할·검색 조각·관찰 기준을 고정한다.
- `backend/app/services/validator.py`는 LLM을 호출하지 않고 선택이 정적 카드와 일치하는지만 검증한다.
- `backend/app/services/search_plan.py`는 `urllib.parse.urlencode`로 역할별·통합 Pinterest 검색 URL을 만든다. Pinterest에 HTTP 요청하지 않는다.
- 역할별 JSON은 TERM_CARD DB 적재 전 시드·검수 자료다. 런타임 선택 저장소는 자체 TERM_CARD DB이며, 실제 repository·스키마·마이그레이션·적재는 별도 구현 작업이다. Getty 데이터는 사용하지 않는다.
- 이번 단계에는 `POST /api/agent`를 구현하지 않는다. LLM Structured Output과 재시도 정책이 준비되는 다음 단계에서 최신 응답 계약과 함께 추가한다.

## AC (Given-When-Then)

**AC-01 · 요청 계약 검증**
- GIVEN: 1~500자 텍스트와 UUID 두 개
- WHEN: `AgentRequest`를 검증
- THEN: 유효한 요청을 만들며 추가 필드는 거부한다.

**AC-02 · 용어 축 검증**
- GIVEN: `body_inverted_triangle` term ID
- WHEN: 이를 `pose` 축으로 검증
- THEN: 축 불일치 오류를 반환한다.

**AC-03 · 검색 역할 순서**
- GIVEN: body, pose, view 선택
- WHEN: 검색 계획을 생성
- THEN: 세 역할만 `body → pose → view` 순서로 만들고, 각 역할 URL과 통합 URL을 반환한다.

**AC-04 · 체형 없는 검색**
- GIVEN: pose 선택만 존재
- WHEN: 검색 계획을 생성
- THEN: `body` 역할을 만들지 않고 pose URL만 반환한다.

**AC-05 · 외부 데이터 미호출**
- GIVEN: 어떤 선택 목록
- WHEN: 검색 계획을 생성
- THEN: URL 문자열만 만들며 Pinterest, OpenAI, Langfuse, MCP 또는 외부 어휘 API에 HTTP 요청하지 않는다.
