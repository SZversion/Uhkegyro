# 작업 티켓 — UH케그려

## 기준 문서

- 제품: `docs/PRD.md`
- 아키텍처: `docs/SDD.md`
- 공개 API·Pydantic·상태: `docs/specs/api-contract.md`
- TERM_CARD JSON: `docs/specs/term-card-catalog.md`
- MCP 도구: `docs/specs/mcp-contract.md`
- 보안: `docs/specs/trust-boundary.md`
- 관측: `docs/specs/observability-and-prompt-versioning.md`

## 남은 구현 작업

| 작업 | 산출물 | 선행 조건 |
| --- | --- | --- |
| JSON 카탈로그 loader·시작 검증 | backend catalog service | `term-card-catalog.md` |
| FastMCP 활성 카드 조회 도구·`/mcp` 접근 제어 | mcp server, 호출 증거 | `mcp-contract.md`, JSON 카탈로그 loader |
| 세션·job 영속화 | PostgreSQL storage | `session-job-persistence.md`, `api-contract.md` |
| PostgreSQL job worker | worker/lease recovery | `postgres-job-worker.md`, `api-contract.md` |
| OpenRouter LLM adapter | model configuration·structured output | `openrouter-llm-adapter.md`, `api-contract.md` |
| failure code·관측 | worker/trace | `api-contract.md`, 관측 Spec |
| Next.js UI | frontend | `api-contract.md` |
| PinterestCrawlerProvider | 서버 Playwright 공개 검색·Pin ID widget 조회 | `pinterest-widget-crawler.md`, `api-contract.md` |

## 출시·협업 추적

> 아래 항목은 이전 전체 티켓에서 누락되지 않도록 유지하는 추적 항목이다. 현재 기능 Spec과 충돌하는 과거 Pinterest API·별도 Pin 저장소·원문 비보관 정책은 복원하지 않는다.

| 티켓 | 작업 | 산출물 | 현행 기준·의존 | 상태 |
| --- | --- | --- | --- | --- |
| T12 | LICENSE 종류와 코드·TERM_CARD JSON·문서 적용 범위를 팀이 결정 | 루트 `LICENSE` 또는 의도적 미추가 결정 기록 | 팀 결정 | ⬜ 미착수 |
| T32 | 평가 실행 스크립트로 원문 30건과 계약 변형 70건을 실행하고 계약 준수 결과를 산출 | `evals/run_evals.py` | `contract-evaluation-variants.md`, backend 구현 | ⬜ 미착수 |
| T33 | Langfuse Prompt 등록, trace 필수 필드와 Dataset 연결을 실제 환경에서 검증 | Langfuse 설정 증거 | `observability-and-prompt-versioning.md`, `prompt-interpreter-v0.md`, T32 | ⬜ 미착수 |
| T34 | p50/p95 지연, 요청당 비용, 모델 비교를 측정 | 측정 기록 | `observability-and-prompt-versioning.md`, T32, T33 | ⬜ 미착수 |
| T36 | 평가·관측·비용·실패 사례·출시 판정을 한 보고서에 기록 | `EVAL_REPORT.md` | `docs/SCAFFOLD.md`, T32~T35 | ⬜ 미착수 |
| T37 | 계약 테스트, 측정 결과, 비용과 운영 기준으로 출시 가능 여부를 판정 | 출시 게이트 결과 | `docs/SCAFFOLD.md`, T34, T36 | ⬜ 미착수 |
| T39 | 제안된 역할을 팀 회의로 확정하고 README와 일치시킴 | 역할 결정 기록과 README 갱신 | 팀 회의 | ⬜ 미착수 |
| 10/8 마일스톤 | 최종 제출 전 T32~T37·T39 상태를 점검 | 마일스톤 점검 기록 | 2026-10-08, 위 티켓 | ⬜ 예정 |

## 운영 원칙

- TERM_CARD는 JSON 카탈로그만 사용하며 DB 적재·외부 어휘 조회를 하지 않는다.
- Agent worker는 활성 카드 조회에 `get_active_term_card(term_id)`만 사용하고, 브라우저는 `/mcp`를 직접 호출하지 않는다.
- 사용자 retry endpoint와 버튼은 없다. 일시 오류는 서버가 자동 재시도하고, 모호성은 다음 사용자 메시지로 보완한다.
- `PinterestCrawlerProvider`는 서버에서 활성 카드의 `query_fragments`만 사용해 공개 검색을 수행하고, 모든 수집 Pin ID를 widget endpoint로 조회한다. 브라우저 직접 호출·Pinterest API v5·외부 본문 LLM 입력은 금지한다.
