# Langfuse 관측 속성 & 프롬프트 버전 규칙 — 강사님 회의(2026-09-22) 접수·확정

**팀**: 4조 (UH케그려)
**작성일**: 2026-09-22
**작성자**: 윤태현 (YTH)
**상태**: 강사님 회의(2026-09-22) 반영 · 트레이싱 계약 확정 · 프롬프트 네이밍·필수/금지 속성 합의 반영
**근거 문서**:
- 확정: `260921 강사님회의/06_트레이싱_정의.md` — 트레이싱 3층·trace 구조·기록 필드·span 배정
- 합의 대상: 안건 3 (Langfuse 관측 속성 & 프롬프트 버전)
- `docs/SDD.md` §6 — 관측·보안·검증
- `EVAL_REPORT.md` §1~2 — 관측·프롬프트 운영 채점 항목

---

## 1. 한눈에 보기

| 항목 | 상태 |
| --- | --- |
| 트레이싱 3층 (Langfuse / stdout / 집계) | **확정** (06 문서) |
| 요청 단위 trace 구조 (5 span) | **확정** (06 문서) |
| 기록 필드 20종 + 개인정보 제한 | **확정** (06 문서) |
| 재시도 trace 가시성 정책 | **확정** (max_retries=0, retry event) |
| 프롬프트 네이밍 규칙 | 합의 필요 — 제안 `uhkegryo-{역할}-v{n}` |
| trace 필수/금지 속성 목록 | 합의 필요 — 제안 필수 5종 / 금지 2종 |
| 관측 구현 책임자 | 합의 필요 — Langfuse(김호섭)·백엔드(윤태현) 병행 지명 |

---

## 2. 트레이싱 3층 (확정 — 06 문서)

| 층 | 무엇을 남기나 | 기록 주체 |
| --- | --- | --- |
| Langfuse trace | 요청 단위로 LLM generation · MCP tool · API span을 하나로 묶는다 | Langfuse Python SDK v4 (OpenAI wrapper) |
| 구조화 stdout 로그 | 같은 데이터를 JSON 라인으로 남겨 파일·수집 도구(GELF 등)로 전달한다 | 백엔드 로거 |
| (비식별) 집계 | user/session 해시로 "누가 얼마나 썼나"를 사람 축으로 집계한다 | Langfuse metadata |

> Langfuse와 stdout은 같은 이벤트를 가져야 한다. 어느 한쪽만 남고 다른 쪽에 없으면 "트레이스가 안 보인다"와 "로그가 없다"로 갈린다.

---

## 3. 요청 단위 trace 구조 (확정 — 06 문서 §2)

```
POST /api/agent (비동기 채택 시: /api/sessions/{id}/messages, /api/jobs/{id} 조회 포함)
  ├─ span: api_agent            (status 200/202/422/503, latency)
  ├─ span: llm_interpret        (attempt 1..n)
  │    └─ event: retry          (attempt, error_type, backoff_ms)   ← 재시도마다 1건
  ├─ span: mcp_getty_terms      (tool_name, tool_latency_ms, 성공/폴백/실패)
  ├─ span: mcp_pinterest_links  (선택 역할만 검색 계획 생성)
  └─ span: response_validate    (output_schema_valid, 링크 역할 수)
```

- 재시도가 일어나면 그 사실이 trace 안에서 보여야 한다 (결과만 남기지 않는다).
- MCP span은 `resolve_illustration_reference_plan` / `search_getty_aat_terms` / `mcp_pinterest_links`로 분리해 LLM 지연과 분리한다 (도구명은 스펙 기준·구현 시 확정).

---

## 4. 기록 필드 20종 (확정 — 06 문서 §3)

| 필드 | 형식 | 의미 |
| --- | --- | --- |
| timestamp | ISO 8601 | 요청·오류를 시간순 추적 |
| request_id | uuid | 서버 생성, 응답에도 동일 값 |
| user_id_hash | sha256 | anonymous_user_id 해시 (원문 미저장) |
| session_id_hash | sha256 | session_id 해시 |
| model | str | 사용 모델 (gpt-4.1-mini 등) |
| prompt_version | str | Langfuse Prompt 버전 (label: production) |
| attempt | int | 최초 1부터 재시도마다 증가 |
| event | str | `llm_interpret` / `retry` / `mcp_call` / `api_agent` / `response_validate` |
| error_type | str \| null | `schema_violation` / `timeout` / `5xx` / `429` / `mcp_timeout` / `mcp_error` / `none` |
| backoff_ms | int \| null | 재시도 전 대기 (안 하면 null) |
| latency_ms | int | 서비스 단계별 지연 (LLM/MCP 분리) |
| input_length | int | request_text 자릿수 |
| output_schema_valid | bool | 최종 응답이 Pydantic 스키마 통과 여부 |
| tool_name | str \| null | `resolve_illustration_reference_plan` / `search_getty_aat_terms` / `mcp_pinterest_links` |
| tool_latency_ms | int \| null | MCP 도구 단독 지연 |
| resolution_source | str \| null | `getty_aat` / `term_cards` (폴백 여부) |
| retry_occurred | bool | 재시도 있었는지 집계용 |
| (보완 추가) job_id | str \| null | 비동기 채택 시 작업 식별자 연결 |
| (보완 추가) failure_code | str \| null | `JOB_TIMEOUT` / `INSTANCE_INTERRUPTED` / `PROCESSING_ERROR` |
| (보완 추가) agent_status | str \| null | 최종 사용자 상태 6종 |

**개인정보·보안 제한 (확정)**: 요청 원문(`request_text` 전문)은 트레이스 본문 대신 해시 또는 제한 정보(길이·term ID)만 남긴다. name·email·로그인·원문 이미지·API 키는 어떤 로그에도 저장하지 않는다. 테스트용 평가셋 문장만 Dataset에 넣는다.

---

## 5. 프롬프트 네이밍 규칙

### 5-1. 규칙

```text
{서비스}-{역할}-v{n}
```

| 프롬프트 | 이름 제안 | 용도 |
| --- | --- | --- |
| 기본 해석 LLM | `uhkegryo-interpreter-v1` | 일상어 → 활성 term_id·역할 구조화 (`InterpretationOutput`) |
| 폴백 LLM | `uhkegryo-fallback-v1` | 카드·Getty 모두 불가 시 임시 후보 (`FallbackTermOutput`) |

- label: `production` 로 고정
- 사용 모델 변경, 프롬프트 변경은 `v{n}` 증가로 추적
- `prompt_version` 필드에 항상 기록 (trace 필수 속성)

### 5-2. EVAL_REPORT.md §2 요구사항 (함께 채움)

| 항목 | 내용 |
| --- | --- |
| Langfuse Prompt로 관리하는 프롬프트 수 | 2 (interpreter · fallback) |
| 현재 서비스 중인 버전 | `uhkegryo-interpreter-v1` · `uhkegryo-fallback-v1` |
| 배포 없이 교체·롤백한 사례 | 구현 후 기록 (EVAL_REPORT에 반영) |

---

## 6. trace 필수/금지 속성

### 필수 5종

| # | 속성 | 근거 |
| --- | --- | --- |
| 1 | 요청 ID (`request_id`) | EVAL_REPORT §1 — 요청 단위 추적 |
| 2 | job/session ID (해시) | 트레이싱 정의 §1 집계 + EVAL_REPORT §1 `user_id`·`session_id` |
| 3 | 모델 (`model`) | EVAL_REPORT §1 — 모델별 비교 |
| 4 | 프롬프트 버전 (`prompt_version`) | EVAL_REPORT §2 — 운영/롤백 판단 |
| 5 | 계약 통과 여부 (`output_schema_valid`) | 평가 지표 "계약 준수율" |

### 금지 2종

| # | 속성 | 이유 |
| --- | --- | --- |
| 1 | 요청 원문 `request_text` 전문 | 개인정보·민감 입력; 길이·해시·term_id로 대체 |
| 2 | 비밀값 (API 키·토큰·서비스 계정 등) | 노출 시 즉시 폐기 대상 |

> 보충: 프롬프트·trace에 외부 데이터 원문(GGetty 후보·Pin URL)을 주입하지 않는다. `<untrusted_data>` 래핑 + 출처 필드(`subject_uri`·`label`·`source_url`)만 남긴다 (신뢰 경계와 연동).

---

## 7. 실패 경로에서도 남는 것 (확정 — 06 문서 §5)

| 실패 | trace에 남는 것 |
| --- | --- |
| LLM 스키마 위반 → 재시도 | `llm_interpret` attempt 1 실패 → `retry` event(`schema_violation`, backoff 0) → attempt 2 |
| 타임아웃 → 재시도 2회 | `retry` event ×2 (backoff 1000→2000) → 503 |
| 5xx · 429 | `retry` event (5xx 1회 backoff 1000, 429는 Retry-After 또는 3000→6000) |
| MCP Getty 조회 실패 | 200 유지 + `mcp_getty_terms` span 폴백(`resolution_source=term_cards`, limitation 기록) |
| MCP 도구 전체 불가 | 200 유지 + mcp span 실패 + `fallback_queries`만 반환 |
| 검증 실패 (허용 term 위반) | `response_validate=false` + 503 |
| 작업 실패 (비동기) | `job_id` + `failure_code` + `retryable` 기록 (+ 필요 시 `agent_status`) |

> 포기(모든 재시도 실패)는 503이며, 지어낸 용어·링크를 내보내지 않는 원칙이 trace에 그대로 보인다. SDK 기본 재시도가 trace를 삼키지 않도록 `max_retries=0`을 명시한다.

---

## 8. 회의 확정 사항 (5건)

| # | 결정 포인트 | 결과 (2026-09-22 회의 기준) |
| --- | --- | --- |
| 1 | 프롬프트 목록·개수 | **2개** (`interpreter`, `fallback`) |
| 2 | 네이밍 규칙 | `uhkegryo-{역할}-v{n}` (label: production) |
| 3 | `session_id`/`user_id` 해시 원천 | **비동기 세션 모델 기준으로 표기 정합화** (06 문서 `anonymous_user_id` 문구 갱신) |
| 4 | 관측 구현 책임자 | Langfuse(김호섭) · 백엔드(윤태현) 병행 — `llm.py` 구현과 동시 지정 |
| 5 | `job_id`·`failure_code`·`agent_status` 필드 추가 | **추가 채택** (비동기 모델에서 trace↔job 연결 필수) |

---

## 9. Next Task

1. 위 확정 5건 → `06_트레이싱_정의.md`에 프롬프트 네이밍·필수/금지 속성·`job_id` 필드 연결 반영 (PR)
2. Langfuse Prompt 2개 등록: `uhkegryo-interpreter-v1`, `uhkegryo-fallback-v1` (label: production)
3. `backend/services/llm.py` 구현 시 trace 필수 5종·금지 2종·`max_retries=0`·retry event 반영 → stdout 구조화 로그 동일 이벤트
4. 진행 지연·실패 케이스 평가 후 trace 스크린샷 + 프롬프트 교체·롤백 사례 → `EVAL_REPORT.md` §1~2 기록