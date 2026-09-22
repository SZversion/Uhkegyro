# API 엔드포인트 목록 — 강사님 회의(2026-09-22) 접수·확정

**팀**: 4조 (UH케그려)
**작성일**: 2026-09-22
**작성자**: 윤태현 (YTH)
**상태**: 강사님 회의(2026-09-22) 반영 · **비동기 확정** · 프런트/LLM 도구 구분 확정
**근거 문서**:
- PR #12(`docs/specs/api-contract.md`, 보류 초안): 공개 HTTP API · 세션·job 모델
- 머지 스펙 `frontend-api-contract.md`: 브라우저 접근 경계
- 머지 스펙 `getty-term-resolution-pipeline.md`·`vocabulary-provider-seam.md`: MCP 도구 계약
- `260921 강사님회의/06_트레이싱_정의.md`: MCP span·도구명

---

## 1. 한눈에 보기

| 계층 | 호출자 | 엔드포인트/도구 | 확정 상태 |
| --- | --- | --- | --- |
| 공개 HTTP API | 브라우저(프런트) → 백엔드 | `GET /health` · `POST /api/sessions` · `POST /api/sessions/{id}/messages` · `GET /api/jobs/{id}` · `POST /api/jobs/{id}/retry` | **비동기 확정** (PR #12 기준) |
| MCP 도구 | LLM → 백엔드 (서버 간) | `search_getty_aat_terms` · `resolve_illustration_reference_plan` · `mcp_pinterest_links` | 구현 전 — 별도 MCP Spec으로 확정 |
| 비공개 경계 | 브라우저 | `/mcp`·LLM SDK·비밀값 **직접 호출 금지** | 머지 스펙으로 확정 |

> 프런트가 부르는 것(HTTP API)과 LLM이 도구로 부르는 것(MCP)을 이 표로 구분한다. 두 계층은 스키마·오류·인증이 별개다.

---

## 2. 공개 HTTP API (비동기 확정 — PR #12 기준)

| 엔드포인트 | 메서드 | 성공 응답 | 권한 | 오류 |
| --- | --- | --- | --- | --- |
| `/health` | GET | `200 {"status":"ok"}` | 쿠키 불필요 | — |
| `/api/sessions` | POST | `201` + `Set-Cookie` + `{session_id, expires_at}` | — | — |
| `/api/sessions/{session_id}/messages` | POST | `202 {message_id, job_id, job_status:queued}` | 쿠키 소유 | `401 SESSION_REQUIRED` / `404 SESSION_NOT_FOUND` / `422 INVALID_REQUEST_TEXT` |
| `/api/jobs/{job_id}` | GET | `200` (항상, 본문에 상태) | 쿠키 소유 | `401 SESSION_REQUIRED` / `404 JOB_NOT_FOUND`(타인 접근 포함) |
| `/api/jobs/{job_id}/retry` | POST | `202 {job_id, retry_of_job_id, job_status}` | 쿠키 소유 | `401` / `404` / `409 JOB_NOT_RETRYABLE` |

### 세부 계약 포인트

- **요청**: 공개 body의 사용자 결정 값은 `request_text`(1~500자)뿐. `role`·`term_id`·검색어·Pin URL은 백엔드만 결정.
- **세션**: 서버 생성 불투명 UUID. 쿠키 `HttpOnly`·`Secure`·`SameSite=Lax`·`Path=/`.
- **폴링**: 조회는 항상 `200` — 처리 실패는 본문 `job_status=failed` + `failure_code`로 표현 (HTTP 레벨과 본문 상태 레벨 구분).
- **재시도**: 자동 재시도 금지. `failed`+`retryable=true`일 때만 사용자가 명시적으로 재시도 (`max_attempts=3`).
- **스키마 참조**: `input-output-pydantic-schema.md` (JobEnvelope · AgentResultPayload · RoleResult)

---

## 3. MCP 도구 (LLM → 백엔드)

| 도구 | 용도 | 입력 계약 | 출력 계약 | 참조 |
| --- | --- | --- | --- | --- |
| `search_getty_aat_terms` | Getty AAT 후보 조회 (VocabularyCandidateProvider) | `query`(정규화 영문 용어) + `limit`(1~5) | `VocabularyLookup{status, terms[], limitations[]}` — `terms[].subject_uri·label·source_name·source_url` | `vocabulary-provider-seam.md` |
| `resolve_illustration_reference_plan` | Selection 검증 + Getty/정적 카드 폴백 결정 + SearchPlan 생성 | `Selection[]` (`role`·`term_id`·`evidence[]`) | `ReferenceResolution{TermResolution[], SearchPlan}` — `resolution_source`(`getty_aat`/`term_cards`/`term_source_unavailable`) + `limitation_codes` | `getty-term-resolution-pipeline.md` |
| `mcp_pinterest_links` | 선택 역할만 Pinterest 검색 계획 생성 | (스펙 기준 역할 선택) | 역할별 검색 링크; 도구 전체 불가 시 `fallback_queries`만 | `06_트레이싱_정의.md` §2 |

### 확정 원칙 (머지 스펙)

- MCP는 **임시 용어·검색 URL을 만들지 않는다.** 임시 후보와 유무 판정은 서버(결정론 코드)만 한다.
- `resolution_source`는 API `reason_codes`에 넣지 않고, `limitation_codes`는 문자열 변환 없이 보존한다.
- Getty의 동적 label은 Pinterest 링크 생성에 사용하지 않는다 (정적 `query_fragment`만).
- 브라우저는 MCP·LLM SDK·비밀값을 직접 호출하지 않는다 — `/mcp`는 공개 데모용 무제한 노출 금지.

---

## 4. 트레이싱 span ↔ 엔드포인트/도구 대응

| span | 대응 | 남기는 값 |
| --- | --- | --- |
| `api_agent` | HTTP API (세션·메시지·job 조회) | 상태 코드 · 스키마 통과 · request_id |
| `llm_interpret` | 기본 LLM 해석 호출 | 모델 · 프롬프트 버전 · 재시도 · 지연 |
| `mcp_getty_terms` | `resolve_illustration_reference_plan` / `search_getty_aat_terms` | tool명 · 성공/폴백/실패 · `resolution_source` |
| `mcp_pinterest_links` | `mcp_pinterest_links` | 입력 role 수 · fallback 여부 |
| `response_validate` | 최종 응답 검증 | `output_schema_valid` · 링크 역할 수 |

---

## 5. 회의 확정 사항

| # | 결정 포인트 | 결과 (2026-09-22 회의 기준) |
| --- | --- | --- |
| 1 | 공개 HTTP API 목록 | **PR #12 채택 (비동기)** — 표 2장 기준으로 고정 |
| 2 | 소유권 미노출 404 | `404`로 존재 여부 미노출 유지 (타인 접근 포함) |
| 3 | MCP 도구 목록 확정 | **3개** — 도구별 span(트레이싱)과 일치 |
| 4 | MCP Spec 분리 | 별도 문서에서 도구명·입출력·전송 방식 확정 (PR #12 Out of Scope와 일치) |
| 5 | `retryable`·`retry_after_ms` | 폴링 본문(`job_status·failure_code`) — HTTP 200 유지 |

---

## 6. Next Task

1. 확정 5건 → 엔드포인트 총괄 표 1장을 `api-contract.md`(PR #12) 확정 안에 반영
2. MCP Spec 신규 작성: 도구 3개명·입출력·전송 방식 (FastMCP Streamable HTTP) + 접근 제어 정책
3. `mcp_server/server.py`의 `example_tool` → 실제 도구 3개로 교체 (`resolve_illustration_reference_plan`·`search_getty_aat_terms`·`mcp_pinterest_links`)
4. 평가셋: HTTP API 오류코드(401/404/409/422)·폴링 상태 전이 케이스 포함 (9/23 마일스톤)