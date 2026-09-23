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
| `POST /api/agent`·job route와 worker | FastAPI routes/worker | `api-contract.md` |
| 자동 재시도·failure code 관측 | worker/trace | `api-contract.md`, 관측 Spec |
| Next.js UI | frontend | `api-contract.md` |
| 검색 provider | provider adapter | 승인된 provider 계약 확정 후 |

## 운영 원칙

- TERM_CARD는 JSON 카탈로그만 사용하며 DB 적재·외부 어휘 조회를 하지 않는다.
- Agent worker는 활성 카드 조회에 `get_active_term_card(term_id)`만 사용하고, 브라우저는 `/mcp`를 직접 호출하지 않는다.
- 사용자 retry endpoint와 버튼은 없다. 일시 오류는 서버가 자동 재시도하고, 모호성은 다음 사용자 메시지로 보완한다.
- Pinterest 크롤링은 이 티켓과 현재 제품 계약의 범위 밖이다.