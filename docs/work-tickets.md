# 작업 티켓 (UH케그려)

> **성격**: 260922 강사님회의 확정 기준으로 반영한 전체 작업 목록. Obsidian `260922 작업기록/작업_티켓_초안.md`를 이 저장소의 계약 기준(PR #15·#16)에 맞춰 정합시킨 단일 원본이다.
> **전제** (260922 강사님회의 권장안 기준):
> - 전송: 비동기(`202` + `GET /api/jobs/{job_id}` 폴링), 자동 재시도 없음 (`max_attempts=3`, 사용자 수동 retry).
> - 용어 원본: **자체 TERM_CARD DB 단일** — Getty·외부 어휘 API·폴백 LLM 사용 안 함.
> - 검색: **Pinterest API 실사용(확정 대기), 미승인 시 자체 DB/링크 전용 폴백** (`PinterestSearchProvider` 교체 가능).
> **마일스톤**: 9/23 문제 정의+평가셋 30건 · 9/24~27 추석 개인 작업 · 10/8(목) 최종 마감.
> **상태 표기**: ⬜ 미착수 / 🚧 진행 / ✅ 완료 / 🔒 대기(선행 머지·결정 의존)
> **담당**: 아래 담당 열은 스펙·README 역할을 근거로 한 **제안**이다. T39에서 회의로 확정한다.

## 0. 선행 머지 (의존 블로커)

| PR | 내용 | 상태 | 영향 |
| --- | --- | --- | --- |
| PR #15 `OSC04/docs/self-managed-term-card-db` | 자체 TERM_CARD DB 계약 (현행 계약 문서 `illustration-reference-current-failure-state-contract.md` 포함) | 🔒 open | 자체 DB·비동기 계약의 근거 |
| PR #16 `YTH02/docs/meeting-2026-09-22-specs` | 강사님회의 확정 스펙 6종 | 🔒 open (리뷰 대기) | 표 아래 T01·T02·T03·T05 산출물 |
| PR #12 `KHS03/docs/api-contract` | 구 동기/보류 수정안 | 🔒 결정 필요 | PR #15·#16 채택 후 폐기(흡수) 처리 결정 |

> 백엔드 구현(T13~)은 위 머지 이후 "현행 계약 스펙 반영" 작업과 함께 시작한다.

## 1. 문서·스펙

| 티켓 | 작업 | 상세 | 산출물 | 의존 | 일정 | 담당(제안) | 상태 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T01 | 회의 확정 사항 기록 | 260922 6개 안건(Pydantic 실패상태·관측·신뢰경계·엔드포인트·출처)을 스펙 6종으로 산출 | PR #16 스펙 6종 | 회의 | 회의 당일 | YTH | ✅ (머지 🔒) |
| T02 | 입출력 Pydantic 스키마 표 | `JobEnvelope`·`AgentMessageRequest`·`AgentResult`·`ReferencePlan`·`TermResult`·`PinResult`·`InterpretationOutput` + enum 정의, PR #15 정합 | `docs/specs/input-output-pydantic-schema.md` | T01 | 회의 직후 | YTH | ✅ (머지 🔒) |
| T03 | 실패 상태 정의 정합 | 비동기 전면 반영, 3축(job/사용자 의미 5종/Pin status) + `JobFailure`(`JOB_TIMEOUT`·`INSTANCE_INTERRUPTED`·`PROCESSING_ERROR`) | `docs/specs/failure-state-definition.md` | T01, T02 | 회의 직후 | YTH | ✅ (머지 🔒) |
| T04 | **frontend-api async 정합화** | `POST /api/agent`(동기) → 세션·job 계약 교체, 쿠키/폴링/오류코드(401/404/409/422) 반영 | `docs/specs/frontend-api-contract.md` | 🔒 T01, T02 (PR #15·#16 머지 후) | PR 머지 직후 | YTH | 🔒/⬜ |
| T05 | 신뢰 경계 1장 | 신뢰 출처 4종 등급·게이트, `<untrusted_data>`(외부 원문 프롬프트 주입 금지), 인젝션 방어 평가 케이스 | `docs/specs/trust-boundary.md` | T01 | 회의 직후 | YTH | ✅ (머지 🔒) |
| T06 | **Pinterest API 전환 스펙 정합화** | 링크 전용→API/자체 DB 전환 여부 결정 + 반영 (`AC-06`·`PINTEREST_RESULTS_UNAVAILABLE` 해제 여부, Pin URL·원격 썸네일 정책, embedPin 유지) | `PRD.md`·`SDD.md`·`NOT_BUILD.md`·`README.md` | 🔒 결정 대기 | 결정 후 | YTH | 🔒/⬜ |
| T07 | MCP Spec 신규 | 자체 TERM_CARD DB 조회 + 검색 provider 중계 도구(2~3개 예상)·입출력·전송(FastMCP Streamable HTTP)·접근 제어. **Getty 도구 없음** | `docs/specs/mcp-contract.md` | T02 | 9/25 | KHS | 🚧 |
| T08 | README 갱신 | API 상태표·검색 방식 확정분·팀/역할·출처 검증 상태·로컬 실행 반영 | `README.md` | T01~T07 | 상시 | 공동 | 🔒/⬜ |

> 문서·스펙 카탈로그: 실패 상태 이전 문서(`illustration-reference-failure-state-contract.md`, 폐기 표기)와 PR #15 기준 현행 계약 문서의 중복·대체 관계는 T04에서 함께 정리한다.

## 2. 데이터·도메인

| 티켓 | 작업 | 상세 | 산출물 | 의존 | 일정 | 담당(제안) | 상태 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T09 | TERM_CARD 승인 기준 수립 | 승인 절차·검토 이력 규정, 활성 20 카드 검증, 승인 전 "미완성 카탈로그" 표기 유지 | 승인 기준 문서 | — | 9/23 | OSC | ⬜ |
| T10 | 자체 DB 카탈로그 설계(폴백 준비) | Pinterest API 미승인 대비 카탈로그. 저장 범위는 `pin_url`+Pin `status`만(이미지 금지), `render_status` 연계. `VocabularyCandidateProvider`(Getty 잔재)는 쓰지 않음 | 자체 DB 카탈로그 스키마 · `PinterestSearchProvider` 교체 계약 | 🔒 T06 | 9/25 | OSC+YTH | ⬜ |
| T11 | Getty AAT 라이선스 확인 | 런타임 의존 없음 → **참고 자료 가치 추적 목적으로만** 공식 문서 확인·기록 | 스펙·README 기록 | — | 배포 전 | YTH | ⬜ |
| T12 | LICENSE 추가 결정 | 저장소 `LICENSE` 종류·적용 범위(코드/카드/문서) 결정 | `LICENSE` (추가 시) | — | 9/26 | 팀 | ⬜ |

## 3. 백엔드 구현

| 티켓 | 작업 | 상세 | 산출물 | 의존 | 일정 | 담당(제안) | 상태 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T13 | LLM 스키마·계약 모델 구현 | Pydantic 모델 전 세트(요청·`JobEnvelope`·`AgentResult`·`ReferencePlan`·`TermResult`·`PinResult`·`InterpretationOutput`·enum) | `backend/schemas/` | T02 | 연휴 전 | YTH | ⬜ |
| T14 | `services/llm.py` 기본 해석 LLM | Structured Output(`InterpretationOutput`), 스키마 위반 1회 재시도, OpenRouter, `max_retries=0`, Langfuse trace 필수 5종·금지 2종 | `backend/services/llm.py` | T13 | 연휴 전 | YTH | ⬜ |
| T15 | 사전 안전 검사 | 인젝션·비밀값 추출·유해 입력 → `unsafe_input`, LLM·도구 미호출, 원문 미반복(`PROMPT_INJECTION_ATTEMPT` 등) | 안전 검사 모듈 | T13 | 연휴 전 | YTH | ⬜ |
| T16 | (재정의) 자체 TERM_CARD DB 조회·장애 처리 | DB 카드 조회·resolver 검증, 저장소 전체 불능은 `failed` job + `TERM_CARD_STORE_UNAVAILABLE`(운영자 오류, 응답 enum 아님). **Getty·폴백 LLM 없음** | 조회·장애 처리 로직 | T13, T14 | 연휴 전 | YTH | ⬜ |
| T17 | 결정론 코드 | card repository(활성 20 로드), resolver(role·`confidence_gate`·`requires_*` 검증), URL builder(`query_fragments` urlencode·역할 순서), response assembler(상태 5종·`reason_codes`·출처 조립) | `backend/services/` 모듈 | T13, T14 | 연휴 전 | YTH | ⬜ |
| T17b | 자체 TERM_CARD DB repository | 시드 JSON(`term-cards/`)→DB 적재 전환(JSON 유지 vs DB 도입 결정 포함), 시작 시 카드 수·필수 필드 검증, 실패 시 ready 불가 | DB repository 모듈 | T17, PR #15 | 연휴~ | YTH | ⬜ |
| T17c | 단위·계약 테스트 (pytest) | resolver·URL builder·검증(422/추가 필드)·쿠키 소유권 등 AC 기반 테스트 — DoD·평가 스크립트(T32)의 근거 | `backend/tests/` | T17 | 연휴~ | YTH | ⬜ |
| T18 | FastAPI 라우트 | `POST /api/sessions`·`POST /api/sessions/{id}/messages`(202+job)·`GET /api/jobs/{id}`·`POST /api/jobs/{id}/retry` + HttpOnly 쿠키 소유권 + 401/404/409/422 + `request_id` | `backend/main.py`·routers | T13, T17 | 연휴 전 | YTH | ⬜ |
| T19 | 세션·job 저장 | Cloud SQL(또는 로컬 대체) 세션/메시지/검색결과/작업 상태 저장, 1개월 보관·만료 삭제. 이미지·LLM 원문 미저장 | 저장소 모듈 | T18 | 배포 전 | YTH | ⬜ |
| T19b | job executor·recovery | worker(job 상태 전이), lease·보증 한도(`JOB_TIMEOUT`·`INSTANCE_INTERRUPTED`), `attempt`/`max_attempts=3` 집행 | job executor 모듈 | T17b, T18 | 연휴~ | YTH | ⬜ |

## 4. MCP

| 티켓 | 작업 | 상세 | 산출물 | 의존 | 일정 | 담당(제안) | 상태 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T20 | MCP 실제 도구 | MCP Spec 확정 후 자체 TERM_CARD DB 조회·검색 provider 중계 도구로 교체. **`search_getty_aat_terms` 등 Getty 도구 없음** (span: `mcp_pinterest_links` 등) | `mcp_server/server.py` | T07, T17 | 9/25~ | KHS | ⬜ |
| T21 | MCP 접근 제어 | 토큰/허용 클라이언트 정책 구현·문서화, 무제한 공개 금지 | 접근 제어 + README | T20 | 배포 전 | KHS | ⬜ |

## 5. Pinterest API

| 티켓 | 작업 | 상세 | 산출물 | 의존 | 일정 | 담당(제안) | 상태 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T22 | Trial 등록·OAuth 플로우 | `boards:read`/`pins:read`, Privacy URL(`surf7978.github.io/proj2-4web/privacy-policy.html`) 입력 완료 → access_token 발급 | OAuth 코드 | — | 계속 (FY 준비 완료) | YTH | 🚧 |
| T22b | `.env` 토큰 변수 반영 | Pinterest access token 관련 변수명을 `.env.example`에 추가 (모의 값 미포함) | `.env.example` | T22 | T22와 병행 | YTH | ⬜ |
| T23 | `GET /v5/search/pins` 테스트 | 응답 파싱, 역할별 최대 8 Pin URL 추출, rate limit 확인, `PIN_SEARCH_UNAVAILABLE` 폴백 확인 | 테스트 결과·샘플 | T22 | 9/25~ | YTH | ⬜ |
| T24 | Standard 승인 준비 | 데모 영상·Developer Guidelines 준수, 미승인 시 T10 자체 DB로 전환 결정 | 승인 문서 | T23 | 배포 전 | YTH | ⬜ |

## 6. 프론트·UI

| 티켓 | 작업 | 상세 | 산출물 | 의존 | 일정 | 담당(제안) | 상태 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T25 | Next.js UI 기본 | 세션 생성, 쿠키 처리, 메시지 제출, 폴링 클라이언트, 상태 5종 화면, `/mcp`·LLM SDK 직접 호출 금지 | `frontend/` | T18 | 연휴 중 | ⬜ (회의 확정) | ⬜ |
| T26 | 검색 결과 렌더링 | 역할별 섹션, 최대 8 Pin, `pinit.js embedPin`(URL만·원격 썸네일 정책 반영), `no_results`/`search_error`/`deleted` 표시 | 렌더링 컴포넌트 | T25, T23 | 연휴 중 | ⬜ (회의 확정) | ⬜ |
| T27 | 프론트 검증·데모 | 정상/실패 경로 동작 확인, 데모 영상(정상+실패) | 데모 영상 | T25, T26 | 10/8 전 | ⬜ (회의 확정) | ⬜ |

## 7. 인프라·배포

| 티켓 | 작업 | 상세 | 산출물 | 의존 | 일정 | 담당(제안) | 상태 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T28 | Docker 재현 확인 | `docker compose up --build` → `/health`·`/docs`, 10분 내 기동 검증, README 절차 갱신 | compose·README 절차 | T18 | 배포 전 | 공동 | ⬜ |
| T29 | Cloud Run 배포 | Secret Manager(키 별도), CORS(localhost/Vercel), 환경변수. `/mcp`·LLM SDK 비노출 | 배포 URL | T18~T21, T28 | 배포 전 | 공동 | ⬜ |
| T30 | 실데이터 배포 후 재현 검증 | 새 환경에서 전체 재현(README §"로컬 실행" 갱신) | README 실측 결과 | T28, T29 | 배포 전 | 공동 | ⬜ |

## 8. 관측·평가

| 티켓 | 작업 | 상세 | 산출물 | 의존 | 일정 | 담당(제안) | 상태 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T31 | 평가셋 30건 작성 | EVAL-01~30 정상/경계/실패 유도(인젝션·스키마·오류코드 401/404/409/422·폴링 전이·`pending_human_review`·Pinterest API 성공/미승인) 반영, Langfuse Dataset 등록 | `evals/dataset.jsonl` | T02~T06 | **9/23** | 공동 | ⬜ |
| T32 | 평가 실행 스크립트 | 배치 실행, 계약 준수율(≥100건)·준수(스키마/역할/URL) 자동 판정, T17c 테스트 기반 | `evals/run_evals.py` | T31, T17 | 연휴~ | YTH | ⬜ |
| T33 | Langfuse 세팅·프롬프트 등록 | **프롬프트 1개** `uhkegryo-interpreter-v1` (label: production, 폴백 프롬프트 없음), trace 필수 5종·금지 2종, retry event, stdout 구조화 로그 동일 | Langfuse 대시보드 | T14, T15 | 연휴~ | KHS+YTH | ⬜ |
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

1. **선행 머지**: PR #15(자체 TERM_CARD DB) → PR #16(스펙 6종) → PR #12 처리(폐기/흡수 결정).
2. T01~T08(스펙) → T13~T19(백엔드) → T20~T27(MCP·Pinterest·프론트) → T28~T37(배포·평가).
3. Pinterest API 승인 지연 시 T23 대신 T10(자체 DB)로 병행하고, 미승인 결정은 `docs/work-tickets.md`·README에 기록한다.
4. 팀원 한 명이 이 티켓의 작업 브랜치를 딸 때는 `docs/github-workflow.md` 브랜치 규칙을 따른다.