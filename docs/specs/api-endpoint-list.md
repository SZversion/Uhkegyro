# API 엔드포인트 목록 — 강사님 회의(2026-09-22) 접수·확정 (PR #15 정합)

**팀**: 4조 (UH케그려)
**작성일**: 2026-09-22
**작성자**: 윤태현 (YTH)
**상태**: 강사님 회의(2026-09-22) 반영 · **비동기 확정** · PR #15(`OSC04/docs/self-managed-term-card-db`) 계약 정합 반영
**근거 문서**:
- 현행 계약(PR #15): `docs/specs/frontend-api-contract.md` — 공개 HTTP API · 세션·job 모델
- 현행 계약(PR #15): `docs/specs/illustration-reference-current-failure-state-contract.md` — job·실패·재시도 계약
- `docs/SDD.md` §3 — 자체 TERM_CARD DB·job executor·recovery
- `260921 강사님회의/06_트레이싱_정의.md`: MCP span·도구명

---

## 1. 한눈에 보기

| 계층 | 호출자 | 엔드포인트/도구 | 확정 상태 |
| --- | --- | --- | --- |
| 공개 HTTP API | 브라우저(프런트) → 백엔드 | `GET /health` · `POST /api/sessions` · `POST /api/sessions/{id}/messages` · `GET /api/jobs/{id}` · `POST /api/jobs/{id}/retry` | **비동기 확정** (PR #15 기준) |
| MCP 도구 | LLM → 백엔드 (서버 간) | 자체 TERM_CARD DB 조회·검색 provider 중계 — **도구 목록·계약 미정** (별도 MCP Spec으로 확정) | 구현 전 — 별도 MCP Spec으로 확정 |
| 비공개 경계 | 브라우저 | `/mcp`·LLM SDK·비밀값 **직접 호출 금지** | 현행 계약으로 확정 |

> 프런트가 부르는 것(HTTP API)과 LLM이 도구로 부르는 것(MCP)을 이 표로 구분한다. 두 계층은 스키마·오류·인증이 별개다.

---

## 2. 공개 HTTP API (비동기 확정 — PR #15 기준)

| 엔드포인트 | 메서드 | 성공 응답 | 권한 | 오류 |
| --- | --- | --- | --- | --- |
| `/health` | GET | `200 {"status":"ok"}` | 쿠키 불필요 | — |
| `/api/sessions` | POST | `201` + `Set-Cookie` + `{session_id, expires_at}` | — | — |
| `/api/sessions/{session_id}/messages` | POST | `202 {message_id, job_id, job_status:queued, poll_after_ms:1000}` | 쿠키 소유 | `401 SESSION_REQUIRED` / `404 SESSION_NOT_FOUND` / `422 INVALID_REQUEST_TEXT` |
| `/api/jobs/{job_id}` | GET | `200` (항상, 본문 `JobEnvelope`에 상태) | 쿠키 소유 | `401 SESSION_REQUIRED` / `404 JOB_NOT_FOUND`(타인 접근 포함) |
| `/api/jobs/{job_id}/retry` | POST | `202 {job_id, retry_of_job_id, job_status:queued, poll_after_ms:1000}` | 쿠키 소유 | `401` / `404` / `409 JOB_NOT_RETRYABLE` |

### 세부 계약 포인트

- **요청**: 공개 body의 사용자 결정 값은 `request_text`(1~500자)뿐. `role`·`term_id`·검색어·Pin URL은 백엔드만 결정.
- **세션**: 서버 생성 불투명 UUID. 쿠키 `HttpOnly`·`Secure`·`SameSite=Lax`·`Path=/`.
- **폴링**: 조회는 항상 `200` — 처리 실패는 본문 `job_status=failed` + `failure`(`JobFailure`)로 표현 (HTTP 레벨과 본문 상태 레벨 구분). 진행 중 `poll_after_ms=1000`, 종결 후 `null`.
- **재시도**: 자동 재시도 금지. `failed`+`retryable=true`일 때만 사용자가 명시적으로 재시도 (`max_attempts=3`).
- **스키마 참조**: `input-output-pydantic-schema.md` (JobEnvelope · AgentResult · ReferencePlan · TermResult · PinResult)

---

## 3. MCP 도구 (LLM → 백엔드)

PR #15 계약에서는 FastMCP 도구 목록·계약이 **미정**이다. 용어 원본이 자체 TERM_CARD DB로 고정되면서 MCP는 자체 DB 카드 조회와 검색 provider 중계를 담당하며, Getty·외부 어휘 조회 도구는 만들지 않는다.

| 도구 | 용도 | 확정 상태 |
| --- | --- | --- |
| (미정 — 2~3개 예상) | 자체 TERM_CARD DB 조회 · 검증된 카드의 `query_fragments`로 검색 계획 생성 | 구현 전 — 별도 MCP Spec으로 확정 (SDD §2 기준: FastMCP는 LLM이 필요하다고 판단한 도구 호출 중계, 도구 목록·계약 미정) |

### 확정 원칙 (현행 계약)

- MCP는 **임시 용어·새 term_id·검색 URL을 만들지 않는다.** 없다는 판정은 서버(결정론 코드)만 한다.
- Getty 데이터·외부 어휘 API·SPARQL·웹 호출은 도구 목록에 포함하지 않는다 (참고 자료일 뿐 런타임 데이터가 아님).
- 브라우저는 MCP·LLM SDK·비밀값을 직접 호출하지 않는다 — `/mcp`는 공개 데모용 무제한 노출 금지.

---

## 4. 트레이싱 span ↔ 엔드포인트/도구 대응

| span | 대응 | 남기는 값 |
| --- | --- | --- |
| `api_agent` | HTTP API (세션·메시지·job 조회·retry) | 상태 코드 · 스키마 통과 · request_id · job_id · failure_code |
| `llm_interpret` | 기본 LLM 해석 호출 | 모델 · 프롬프트 버전 · 재시도 · 지연 |
| `mcp_pinterest_links` | 검색 provider 중계 (PinterestSearchProvider) | 입력 role 수 · `pins[].status` (available/thumbnail_unavailable/deleted) |
| `response_validate` | 최종 응답 검증 | `output_schema_valid` · 링크 역할 수 |

> Getty/외부 어휘 조회 span(`mcp_getty_terms`, `resolve_illustration_reference_plan`, `search_getty_aat_terms`)은 PR #15 계약에서 제거되어 기록하지 않는다.

---

## 5. 회의 확정 사항

| # | 결정 포인트 | 결과 (2026-09-22 회의 기준 · PR #15 정합) |
| --- | --- | --- |
| 1 | 공개 HTTP API 목록 | **PR #15 채택 (비동기)** — 표 2장 기준으로 고정 |
| 2 | 소유권 미노출 404 | `404`로 존재 여부 미노출 유지 (타인 접근 포함) |
| 3 | MCP 도구 목록 | **미정 상태로 고정** — 구현 전 별도 MCP Spec에서 도구명·입출력·전송 방식 확정 (SDD와 일치) |
| 4 | MCP Spec 분리 | 별도 문서에서 도구명·입출력·전송 방식 확정 (현행 계약 Out of Scope와 일치) |
| 5 | `retryable`·재시도 | 폴링 본문(`job_status`·`failure`) — HTTP 200 유지, `max_attempts=3`, 자동 재시도 없음 |

---

## 6. Next Task

1. 확정 5건 → 엔드포인트 총괄 표 1장을 현행 계약(`frontend-api-contract.md`)에 반영 (PR #15 병합 시점 이후)
2. MCP Spec 신규 작성: 자체 TERM_CARD DB 조회·검색 provider 도구 + 접근 제어 정책 (SDD §2 기준)
3. `mcp_server/server.py`의 `example_tool` → MCP Spec 확정 후 실제 도구 교체
4. 평가셋: HTTP API 오류코드(401/404/409/422)·폴링 상태 전이 케이스 포함 (9/23 마일스톤)