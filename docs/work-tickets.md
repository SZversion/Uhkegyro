# 작업 티켓 (UH케그려)

> **성격**: 전체 작업 목록 단일 원본. 최신 main(PR #15~#21 머지 기준)의 통합 스펙(`docs/specs/api-contract.md`·`mcp-contract.md`·`term-card-catalog.md`·`contract-evaluation-variants.md`)과 백엔드·평가셋 실제 상태를 반영한다.
> **전제** (현행 통합 계약 기준):
> - 전송: `POST /api/agent` 단일 엔드포인트(`202` + `JobEnvelope queued`) + `GET /api/jobs/{job_id}` 폴링. 세션 쿠키는 서버가 발급·재사용하고, 수동 retry 엔드포인트는 없다. 자동 재시도는 최초 실행 포함 최대 3회(`LLM_*`·`SEARCH_*`·`JOB_INSTANCE_INTERRUPTED`만).
> - 용어 원본: **팀 검수 TERM_CARD JSON 카탈로그 단일** — Getty·외부 어휘 API·폴백 LLM 사용 안 함. 시작 검증 실패 시 fail-closed.
> - 검색: **Pinterest API 실사용(확정 대기), 미승인 시 자체 DB/링크 전용 폴백** (`PinterestSearchProvider` 교체 가능).
> - 평가: 원문 30건 + 계약 변형 70건 = 100건 이상 계약 준수 평가.
> **마일스톤**: ✅ 9/23 문제 정의+평가셋 30건 달성 · 9/24~27 추석 개인 작업 · **10/8(목) 최종 마감**.
> **상태 표기**: ⬜ 미착수 / 🚧 진행 / ✅ 완료 / 🔒 대기(선행 머지·결정 의존)
> **담당**: 아래 담당 열은 스펙·README 역할을 근거로 한 **제안**이다. T39에서 회의로 확정한다.

## 0. 선행 머지 (의존 블로커) — **전체 완료 ✅**

| PR | 내용 | 상태 | 영향 |
| --- | --- | --- | --- |
| PR #9 `YTH01/docs/frontend-api-contract` | 프론트-백엔드 비동기 계약 (구) | ✅ **MERGED** (9/21) | 이후 PR #19의 `api-contract.md`로 대체됨 |
| PR #12 `KHS03/docs/api-contract` | 구 동기/보류 수정안 | ✅ **MERGED** (9/21) | PR #15·#18 채택으로 흡수 완료 |
| PR #15 `OSC04/docs/self-managed-term-card-db` | 자체 TERM_CARD DB 계약 | ✅ **MERGED** (9/22) | 용어 원본·비동기 계약의 근거 |
| PR #16 `YTH02/docs/meeting-2026-09-22-specs` | 회의 스펙 6종 초안 | ✅ **CLOSED** (미머지) | PR #18로 대체 |
| PR #17 `YTH03/docs/work-tickets` | 작업 티켓 반영 (260922 확정 기준) | ✅ **MERGED** (9/22) | 본 문서 최초 반영 |
| PR #18 `YTH04/docs/meeting-2026-09-22-specs` | 회의 확정 스펙 6종 (PR #16 대체) | ✅ **MERGED** (9/22) | T01~T05 산출물 반영 |
| PR #19 `KHS04/docs/document-consolidation` | 문서 통합 — 구 스펙 12종 삭제, `api-contract`·`mcp-contract`·`term-card-catalog`·`contract-evaluation-variants` 신규 | ✅ **MERGED** (9/22) | 현행 통합 스펙의 근거 |
| PR #20 `YTH04/free-tier-sqlite-setup` | GCP+Cloud Run 분리 배포 + MCP 구현 + Neon | ✅ **MERGED** (9/23) | 백엔드 골조·MCP 도구·배포 설정 반영 |
| PR #21 `OSC05/docs/evaluation-contract-alignment` | 평가셋 30건 + 계약 변형 70건 | ✅ **MERGED** (9/23) | T31 완료 |
| PR #22 `YTH05/spec-ref-path-update` | 스펙 참조 경로 정리 | ✅ **CLOSED** (미머지) | PR #19가 대체 처리 |

> **백엔드 구현(T13~) 선행 조건 모두 충족** — 즉시 착수 가능

## 1. 문서·스펙

| 티켓 | 작업 | 상세 | 산출물 | 의존 | 일정 | 담당(제안) | 상태 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T01 | 회의 확정 사항 기록 | 260922 6개 안건(Pydantic 실패상태·관측·신뢰경계·엔드포인트·출처) 스펙화 | PR #18 스펙 6종 | 회의 | 회의 당일 | YTH | ✅ |
| T02 | 입출력 Pydantic 스키마 표 | `AgentRequest`·`JobEnvelope`·`AgentResult`·`ReferencePlan`·`TermResult`·`PinResult`·`InterpretationOutput` + enum — `api-contract.md`에서 흡수·확정 | `docs/specs/api-contract.md` | T01 | 회의 직후 | YTH | ✅ |
| T03 | 실패 상태 정의 정합 | job 상태 7종·`agent_status` 5종·failure code 13종·사유 코드 8종 — `api-contract.md`에서 통합 정리 | `docs/specs/api-contract.md` | T01, T02 | 회의 직후 | YTH | ✅ |
| T04 | **통합 계약 정합화** | PR #19 통합 후 티켓·README·SDD가 `api-contract.md`·`mcp-contract.md`·`term-card-catalog.md` 기준과 일치하는지 확인 | `docs/specs/api-contract.md` | T01~T03, PR #19 | 즉시 착수 가능 | YTH | ✅ (본 문서 갱신 반영) |
| T05 | 신뢰 경계 | 신뢰 출처 4종 등급·게이트, `<untrusted_data>`(외부 원문 프롬프트 주입 금지), 인젝션 방어 평가 케이스 | `docs/specs/trust-boundary.md` | T01 | 회의 직후 | YTH | ✅ |
| T06 | **Pinterest API 전환 스펙 정합화** | 링크 전용→API/자체 DB 전환 여부 결정 + 반영 (`PIN_SEARCH_UNAVAILABLE` 해제 여부, Pin URL·원격 썸네일 정책) | `PRD.md`·`SDD.md`·`NOT_BUILD.md`·`README.md` | 팀/강사님 결정 필요 | 결정 후 즉시 | YTH | 🔒/⬜ |
| T07 | MCP Spec | `get_active_term_card(term_id)`·Streamable HTTP·접근 제어·fail-closed | `docs/specs/mcp-contract.md` | T02 | PR #19로 반영 | KHS | ✅ |
| T08 | README 갱신 | API 상태표·검색 방식 확정분·팀/역할·출처 검증 상태·MCP 연결 방법·로컬 실행 반영 | `README.md` | T01~T07 | 상시 | 공동 | ⬜ |

## 2. 데이터·도메인

| 티켓 | 작업 | 상세 | 산출물 | 의존 | 일정 | 담당(제안) | 상태 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T09 | TERM_CARD 승인 기준 수립 | 승인 절차·검토 이력 규정, 활성 카드 검증, 승인 전 "미완성 카탈로그" 표기 유지 | 승인 기준 문서 | — | 9/23 | OSC | ⬜ |
| T10 | 자체 카탈로그/폴백 설계 | Pinterest API 미승인 대비 폴백. 저장 범위는 `pin_url`+Pin `status`만(이미지 금지). Getty 잔재(`VocabularyCandidateProvider`)는 쓰지 않음 | 카탈로그 확장 계획 · `PinterestSearchProvider` 교체 계약 | T06 결정 후 | 9/25 | OSC+YTH | ⬜ |
| T11 | Getty AAT 라이선스 확인 | 런타임 의존 없음 → **참고 자료 가치 추적 목적으로만** 공식 문서 확인·기록 | 스펙·README 기록 | — | 배포 전 | YTH | ⬜ |
| T12 | LICENSE 추가 결정 | 저장소 `LICENSE` 종류·적용 범위(코드/카드/문서) 결정 | `LICENSE` (추가 시) | — | 9/26 | 팀 | ⬜ |

## 3. 백엔드 구현

| 티켓 | 작업 | 상세 | 산출물 | 의존 | 일정 | 담당(제안) | 상태 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T13 | LLM 스키마·계약 모델 구현 | `AgentRequest`·`JobEnvelope`·`AgentResult`·`ReferencePlan`·`TermResult`·`PinResult`·`InterpretationOutput`·enum — `api-contract.md` §What 기준 | `backend/schemas/` | T02 | 연휴 전 | YTH | ⬜ |
| T14 | `services/llm.py` 기본 해석 LLM | Structured Output(`InterpretationOutput={interpretation_state, selections, unresolved_constraints, clarifying_question}`), 스키마 위반 시 `LLM_INVALID_STRUCTURED_OUTPUT`, `max_retries=0`, Langfuse trace | `backend/services/llm.py` | T13 | 연휴 전 | YTH | ⬜ |
| T15 | 사전 안전 검사 | 인젝션·비밀값 추출·유해 입력 → `completed + unsafe_input`(`UNSAFE_INPUT`), LLM·도구 미호출, 원문 미반복 | 안전 검사 모듈 | T13 | 연휴 전 | YTH | ⬜ |
| T16 | 카탈로그 조회·장애 처리 | `term-card-catalog.md` 기반 조회·resolver 검증. 저장소 전체 불능은 `failed` + 운영 원인 기록(`CONFIGURATION_ERROR` 계열). **Getty·폴백 LLM 없음** | 조회·장애 처리 로직 | T13, T14 | 연휴 전 | YTH | ⬜ |
| T17 | 결정론 코드 | 카탈로그 repository(활성 카드 로드), resolver(role·조건 검증), URL builder(`query_fragments` urlencode·역할 순서), response assembler(`agent_status` 5종·사유 코드·보안 필터 조립) | `backend/services/` 모듈 | T13, T14 | 연휴 전 | YTH | ⬜ |
| T17b | 카탈로그 repository 구현 | `term-cards/` JSON → 시작 시 검증·활성 카드 사전 적재(term-card-catalog.md), 실패 시 ready 불가 | `backend/mcp/server.py`·repository | T17, PR #19 | **일부 구현됨 **(PR #20) | YTH | 🚧 |
| T17c | 단위·계약 테스트 (pytest) | resolver·URL builder·검증(422/추가 필드)·쿠키 소유권 등 `api-contract.md` AC 기반 테스트 — DoD·평가 스크립트(T32)의 근거 | `backend/tests/` | T17 | 연휴~ | YTH | ⬜ |
| T18 | FastAPI 라우트 | `POST /api/agent`(202+queued job, 쿠키 발급/재사용)·`GET /api/jobs/{job_id}`(200 `JobEnvelope`) + HttpOnly 쿠키 검증 + `422`/`401`/`404` + `request_id` | `backend/main.py`·routers | T13, T17 | 연휴 전 | YTH | ⬜ |
| T19 | 세션·job 저장 | Neon PostgreSQL(로컬 `DATABASE_URL` 필수) 세션/메시지/job 상태 저장, 1개월 보관·만료 삭제. 이미지·LLM 원문 미저장 | 저장소 모듈·DB 초기화 | T18 | 배포 전 | YTH | ⬜ |
| T19b | job executor·recovery | worker(job 상태 7종 전이), 자동 재시도(최초 포함 3회, `LLM_*`·`SEARCH_*`·`JOB_INSTANCE_INTERRUPTED` only), 결정적 실패 즉시 종결 | job executor 모듈 | T17b, T18 | 연휴~ | YTH | ⬜ |

## 4. MCP

| 티켓 | 작업 | 상세 | 산출물 | 의존 | 일정 | 담당(제안) | 상태 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T20 | MCP 실제 도구 | `get_active_term_card(term_id)` 구현 — 활성 카드 읽기 전용 반환·`not_found`→`TERM_NOT_ACTIVE`·fail-closed | `backend/mcp/server.py` | T07, T17 | PR #20으로 구현 | KHS | ✅ |
| T20b | MCP 호출 증거 | `mcp-contract.md` AC-04 — README에 `/mcp` 연결 방법·도구 목록·`found`/`not_found` 실제 호출 결과·데모 기록 | README·데모 | T20 | 배포 전 | KHS | ⬜ |
| T21 | MCP 접근 제어 | Cloud Run IAM(`--no-allow-unauthenticated` + invoker binding) 적용, README에 인증 방식 문서화 | 접근 제어 + README | T20 | Partially in PR #20 | KHS | 🚧 |

## 5. Pinterest API

| 티켓 | 작업 | 상세 | 산출물 | 의존 | 일정 | 담당(제안) | 상태 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T22 | Trial 등록·OAuth 플로우 | `boards:read`/`pins:read`, Privacy URL(`surf7978.github.io/proj2-4web/privacy-policy.html`) 입력 → access_token 발급 | OAuth 코드 | — | 계속 (FY 준비 완료) | YTH | 🚧 |
| T22b | `.env` 토큰 변수 반영 | Pinterest access token 관련 변수명을 `.env.example`에 추가 (모의 값 미포함) | `.env.example` | T22 | T22와 병행 | YTH | ⬜ |
| T23 | `GET /v5/search/pins` 테스트 | 응답 파싱, 역할별 최대 8 Pin URL 추출, rate limit 확인, `PIN_SEARCH_UNAVAILABLE` 폴백 확인 | 테스트 결과·샘플 | T22 | 9/25~ | YTH | ⬜ |
| T24 | Standard 승인 준비 | 데모 영상·Developer Guidelines 준수, 미승인 시 T10 폴백으로 전환 결정 | 승인 문서 | T23 | 배포 전 | YTH | ⬜ |

## 6. 프론트·UI

| 티켓 | 작업 | 상세 | 산출물 | 의존 | 일정 | 담당(제안) | 상태 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T25 | Next.js UI 기본 | `POST /api/agent` 제출(쿠키 포함), job polling 클라이언트, 상태 5종 화면, `/mcp`·LLM SDK 직접 호출 금지 | `frontend/` | T18 | 연휴 중 | ⬜ (회의 확정) | ⬜ |
| T26 | 검색 결과 렌더링 | 역할별 섹션, 최대 8 Pin, 원격 썸네일은 원본 `pin_url` 링크로 표시, 빈 결과·검색 미수신·삭제 Pin 표시 | 렌더링 컴포넌트 | T25, T23 | 연휴 중 | ⬜ (회의 확정) | ⬜ |
| T27 | 프론트 검증·데모 | 정상/실패 경로 동작 확인, 데모 영상(정상+실패) | 데모 영상 | T25, T26 | 10/8 전 | ⬜ (회의 확정) | ⬜ |

## 7. 인프라·배포

| 티켓 | 작업 | 상세 | 산출물 | 의존 | 일정 | 담당(제안) | 상태 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T28 | Docker 재현 확인 | `docker compose up --build` → `/health`·`/docs`, 10분 내 기동 검증, README 절차 갱신 | compose·README 절차 | T18 | 배포 전 | 공동 | ⬜ |
| T29 | Cloud Run 배포 | PR #20 기반 배포 설정 확정(api/mcp 분리, IAM, Secret Manager, CORS). `/mcp`·LLM SDK 비노출 확인 | 배포 URL | T18~T21, T28 | 배포 전 | 공동 | ⬜ |
| T30 | 실데이터 배포 후 재현 검증 | 새 환경에서 전체 재현(README §"로컬 실행" 갱신) | README 실측 결과 | T28, T29 | 배포 전 | 공동 | ⬜ |

## 8. 관측·평가

| 티켓 | 작업 | 상세 | 산출물 | 의존 | 일정 | 담당(제안) | 상태 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T31 | 평가셋 작성 | 원문 30건(`evals/dataset.jsonl`)+계약 변형 70건(`contract-variants.jsonl`) — 정상/경계/실패 유도, 공개 계약 준수 | `evals/dataset.jsonl`·`contract-variants.jsonl` | T02~T06 | **PR #21 9/23 완료** | 공동 | ✅ (Langfuse Dataset 미등록) |
| T32 | 평가 실행 스크립트 | 배치 실행, 계약 준수율(≥100건)·준수(스키마/역할/URL) 자동 판정, T17c 테스트 기반 | `evals/run_evals.py` | T31, T17 | 연휴~ | YTH | ⬜ |
| T33 | Langfuse 세팅·프롬프트 등록 | 프롬프트 `uhkegryo-interpreter-v1` (label: production, 폴백 없음), trace 필수 5종·금지 2종, Dataset 등록, retry event, stdout 구조화 로그 동일 | Langfuse 대시보드 | T14, T15 | 연휴~ | KHS+YTH | ⬜ |
| T34 | 지표 측정 | p50/p95 지연·요청당 비용·모델 2종 비교·개선 전후 2회+ 재측정 (폴링 최종 결과 수신 시점 기준) | 측정 기록 | T32, T33 | 연휴~ | 공동 | ⬜ |
| T35 | 규칙·사람 판정 기록 | 사람 의미 판정 0~2점(용어 연결·모호성·링크 분리) | 판정 결과 | T31, T32 | 10/8 전 | OSC | ⬜ |
| T36 | EVAL_REPORT.md 작성 | 7개 섹션(관측·프롬프트·평가셋·개선 전후·비용·운영 지표·출시 게이트)+약점 | `EVAL_REPORT.md` | T32~T35 | 10/8 전 | 공동 | ⬜ |
| T37 | 출시 게이트 판정 | 스키마 통과 ≥95%·p95≤10초(목표 7초)·오작동 0·비용 게이트 | 게이트 결과 | T34 | 10/8 전 | 공동 | ⬜ |

## 9. 기타·완료분

| 티켓 | 작업 | 상세 | 산출물 | 일정 | 상태 |
| --- | --- | --- | --- | --- | --- |
| T38 | 개인정보처리방침·GitHub Pages | `surf7978/proj2-4web` 배포 (Privacy URL `surf7978.github.io/proj2-4web/privacy-policy.html`) | `privacy-policy.html` | 완료 | ✅ |
| T39 | 팀 역할 분담 확정 | 위 담당(제안)을 회의로 확정, README 팀원 표·역할과 정합 | `roles.md` 또는 회의 결정 기록 | 회의에서 확정 | ⬜ |

## 순서 규칙

1. **선행 머지: 모두 완료 ✅** — PR #15 → #18 → #19(통합 스펙) → #20(백엔드·MCP) → #21(평가셋)
2. T01~T08(스펙) → T13~T19(백엔드) → T20~T27(MCP·Pinterest·프론트) → T28~T37(배포·평가).
3. Pinterest API 승인 지연 시 T23 대신 T10(폴백)으로 병행하고, 미승인 결정은 `docs/work-tickets.md`·README에 기록한다.
4. 팀원 한 명이 이 티켓의 작업 브랜치를 딸 때는 `docs/github-workflow.md` 브랜치 규칙을 따른다.
5. 스펙을 바꾸거나 추가하는 작업은 먼저 해당 `docs/specs/{feature}.md`를 갱신한 뒤 구현하고, 구현이 계약을 바꾸면 같은 변경에서 문서를 함께 갱신한다(AGENTS.md).