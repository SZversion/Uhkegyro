# API 엔드포인트 목록 — 강사님 회의(2026-09-22) 접수·확정 (PR #15 정합)

**팀**: 4조 (UH케그려)
**작성일**: 2026-09-22
**작성자**: 윤태현 (YTH)
**상태**: 강사님 회의(2026-09-22) 반영 · **비동기 확정** · PR #15(`OSC04/docs/self-managed-term-card-db`) 계약 정합 반영
**근거 문서**:
- `docs/PRD.md` — 제품 원칙·용어 단일 원본·범위 정의 기준
- 현행 계약(PR #15): `docs/specs/api-contract.md` — 공개 HTTP API · 세션·job·Pydantic·실패·재시도 단일 기준
- `docs/SDD.md` §3 — 자체 TERM_CARD DB·job executor·recovery
- `260921 강사님회의/06_트레이싱_정의.md`: MCP span·도구명
- `docs/specs/mcp-contract.md` — MCP 도구 계약 (신규)
- `docs/specs/term-card-catalog.md` — TERM_CARD JSON 카탈로그 (신규)

---

## 0. Why · Goal · What · How · AC

### Why

- **페르소나**: 프런트(김호섭)·백엔드(윤태현)·MCP 구현자
- **상황**: HTTP API와 MCP 도구 경계가 뒤섞이면 인증·오류·스키마가 섞인다.
- **문제**: (1) 어떤 엔드포인트가 확정됐는지 불명확 (2) MCP 도구명이 아직 미정인데 문서에서 확정처럼 보임
- **측정 지표**: 평가셋의 HTTP 오류코드·폴링 전이 케이스 통과, 도구명 미정 표기 일관성

### Goal

- **해결 목표**: 공개 HTTP 2종·비공개 금지 경계·MCP(신규 Spec)를 구분해 구현 인원별 작업 단위를 고정한다.
- **성공 기준**: 배포되는 엔드포인트가 §2 표와 일치하고, MCP 영역은 `mcp-contract.md` 확정 상태를 유지한다.
- **Out of Scope**: MCP 도구 상세(별도 `mcp-contract.md`)

### What

- 공개 HTTP API 2종(비동기 확정: `POST /api/agent`, `GET /api/jobs/{job_id}`), MCP 도구 1종(`get_active_term_card`), 비공개 경계(브라우저 직접 호출 금지)
- 트레이싱 span ↔ 엔드포인트/도구 대응, 회의 확정 5건

### How

- 백엔드 FastAPI 라우터·Langfuse span을 `api-contract.md` 기준으로 구현하고, `mcp-contract.md` 확정 시 본 문서를 갱신한 뒤 도구 구현을 시작한다.

### AC

**AC-01 · 엔드포인트 목록**
- GIVEN: 배포된 백엔드 엔드포인트를 열거할 때
- WHEN: 구현을 확인하면
- THEN: `/health`·`/api/agent`·`/api/jobs/{job_id}` 3종만 공개되고 나머지는 비공개/금지 경계로 남는다.

**AC-02 · 형식 오류는 HTTP 422**
- GIVEN: `request_text`가 공백만이거나 500자를 넘으면
- WHEN: 요청 검증을 거치면
- THEN: `422 INVALID_REQUEST_TEXT`가 반환되고 LLM·도구를 호출하지 않는다.

**AC-03 · 도구명 미확정 표기**
- GIVEN: MCP Spec이 확정되지 않았을 때
- WHEN: trace·문서에 검색 provider를 표기하면
- THEN: 확정 도구명(`mcp_*`)을 쓰지 않고 provider/논리 span(`pinterest_search_provider` 등)으로만 표기한다.

---

## 1. 한눈에 보기

| 계층 | 호출자 | 엔드포인트/도구 | 확정 상태 |
| --- | --- | --- | --- |
| 공개 HTTP API | 브라우저(프런트) → 백엔드 | `GET /health` · `POST /api/agent` · `GET /api/jobs/{job_id}` | **비동기 확정** (`api-contract.md`) |
| MCP 도구 | LLM → 백엔드 (서버 간) | `get_active_term_card(term_id)` — 자체 TERM_CARD DB 조회 | `mcp-contract.md` 확정 |
| 비공개 경계 | 브라우저 | `/mcp`·LLM SDK·비밀값 **직접 호출 금지** | 현행 계약으로 확정 |

> 프런트가 부르는 것(HTTP API)과 LLM이 도구로 부르는 것(MCP)을 이 표로 구분한다. 두 계층은 스키마·오류·인증이 별개다.

---

## 2. 공개 HTTP API (비동기 확정 — `api-contract.md` 기준)

| 엔드포인트 | 메서드 | 성공 응답 | 권한 | 오류 |
| --- | --- | --- | --- | --- |
| `/health` | GET | `200 {"status":"ok"}` | 쿠키 불필요 | — |
| `/api/agent` | POST | `202 {message_id, job_id, job_status:"queued", poll_after_ms:1000}` + HttpOnly cookie(신규/기존) | 쿠키 소유(신규 세션 발급 가능) | `422 INVALID_REQUEST_TEXT` |
| `/api/jobs/{job_id}` | GET | `200 JobEnvelope` (진행 중: `poll_after_ms=1000`, 종결: `poll_after_ms=null`) | 쿠키 소유 | `401 SESSION_REQUIRED` / `404 JOB_NOT_FOUND`(타인 접근 포함) |

### 세부 계약 포인트

- **요청**: 공개 body의 사용자 결정 값은 `request_text`(1~500자)뿐. `role`·`term_id`·검색어·Pin URL은 백엔드만 결정.
- **세션**: 서버 생성 불투명 UUID. 쿠키 `HttpOnly`·`Secure`·`SameSite=Lax`·`Path=/`. 신규 세션 시 쿠키 발급, 기존 세션 쿠키 재사용.
- **폴링**: 조회는 항상 `200` — 처리 실패는 본문 `job_status=failed` + `failure`(`JobFailure`)로 표현 (HTTP 레벨과 본문 상태 레벨 구분). 진행 중 `poll_after_ms=1000`, 종결 후 `null`.
- **재시도**: 사용자 재시도 endpoint 없음(`POST /api/jobs/{job_id}/retry` 제거). 자동 재시도는 서버가 내부적으로 최대 3회(최초 포함) 실행. 다음 사용자 메시지는 새 job.
- **스키마 참조**: `api-contract.md` (JobEnvelope · AgentResult · ReferencePlan · TermResult · PinResult · AgentRequest · InterpretationOutput)

---

## 3. MCP 도구 (LLM → 백엔드)

`mcp-contract.md`에서 확정: `get_active_term_card(term_id)` 1개 도구. FastMCP Streamable HTTP `/mcp`로 제공.

| 도구 | 용도 | 확정 상태 |
| --- | --- | --- |
| `get_active_term_card` | 활성 `term_id`에 대한 팀 검수 설명·검색 조각 반환 | `mcp-contract.md` 확정 |

### 확정 원칙 (현행 계약)

- MCP는 **임시 용어·새 term_id·검색 URL을 만들지 않는다.** 없다는 판정은 서버(결정론 코드)만 한다.
- Getty 데이터·외부 어휘 API·SPARQL·웹 호출은 도구 목록에 포함하지 않는다 (참고 자료일 뿐 런타임 데이터가 아님).
- 브라우저는 MCP·LLM SDK·비밀값을 직접 호출하지 않는다 — `/mcp`는 공개 데모용 무제한 노출 금지.

---

## 4. 트레이싱 span ↔ 엔드포인트/도구 대응

| span | 대응 | 남기는 값 |
| --- | --- | --- |
| `api_agent` | HTTP API (`/api/agent`, `/api/jobs/{job_id}`) | 상태 코드 · 스키마 통과 · request_id · job_id · failure_code |
| `llm_interpret` | 기본 LLM 해석 호출 | 모델 · 프롬프트 버전 · 재시도 · 지연 |
| `pinterest_search_provider` (잠정 논리 span) | 검색 provider 중계 (PinterestSearchProvider) | 입력 role 수 · `pins[].status` (available/thumbnail_unavailable/deleted) |
| `response_validate` | 최종 응답 검증 | `output_schema_valid` · 링크 역할 수 |
| `mcp_get_active_term_card` | MCP 도구 호출 | term_id · status(found/not_found) |

> Getty/외부 어휘 조회 span(`mcp_getty_terms`, `resolve_illustration_reference_plan`, `search_getty_aat_terms`)은 PR #15 계약에서 제거되어 기록하지 않는다.

---

## 5. 회의 확정 사항

| # | 결정 포인트 | 결과 (2026-09-22 회의 기준 · PR #15 정합) |
| --- | --- | --- |
| 1 | 공개 HTTP API 목록 | **`api-contract.md` 채택 (비동기)** — `POST /api/agent` + `GET /api/jobs/{job_id}` 고정 |
| 2 | 소유권 미노출 404 | `404 JOB_NOT_FOUND`로 존재 여부 미노출 유지 (타인 접근 포함) |
| 3 | MCP 도구 | **`get_active_term_card` 1개 확정** — `mcp-contract.md` 참고 |
| 4 | MCP Spec 분리 | `mcp-contract.md`에서 도구·입출력·전송 방식·접근 제어 확정 |
| 5 | 재시도 | 서버 내부 자동 재시도(최대 3회). 사용자 retry endpoint 없음. |

---

## 6. Next Task

1. `api-contract.md`를 단일 기준으로 백엔드 라우터·worker·검증 구현 (T13~T18)
2. `mcp-contract.md` 구현: `get_active_term_card` 도구 + 접근 제어 (T20~T21)
3. `mcp_server/server.py`의 `example_tool` → `get_active_term_card` 교체
4. 평가셋: HTTP API 오류코드(401/404/422)·폴링 상태 전이·자동 재시도 케이스 포함 (9/23 마일스톤)