# 도메인 지식 출처 정리 (라이선스) — 강사님 회의(2026-09-22) 접수·확정 (PR #15 정합)

**팀**: 4조 (UH케그려)
**작성일**: 2026-09-22
**작성자**: 윤태현 (YTH)
**상태**: 강사님 회의(2026-09-22) 반영 · 출처별 검증·라이선스 담당자·데드라인 지정 필요 · **PR #15 정합**
**근거 문서**:
- `README.md` §"도메인 데이터와 출처 경계" — 자체 TERM_CARD DB·Pinterest 출처 경계
- `NOT_BUILD.md` — 수집·저장·재게시 금지 범위
- `docs/specs/self-managed-term-card-store.md`·`term-card-category-split.md` — 자체 TERM_CARD DB·시드 자료 계약
- PRD — "승인된 출처만 완료 카탈로그로 주장한다"

---

## 1. 한눈에 보기

| 출처 | 형태 | 검증·라이선스 상태 | 출력 표시 |
| --- | --- | --- | --- |
| 역할별 카드 JSON → 자체 TERM_CARD DB | 팀 카드 (시드 74개 / 활성 20, v0.6-self-managed-term-card-store-draft) | **승인 기준 미정**, 원저작·출처 처리 미확인 | `term_id`·설명·`query_fragments` |
| Getty AAT | 조사 참고 자료 | **런타임 데이터 아님** — DB·MCP 응답·LLM 입력·사용자 화면에 저장·표시 금지 | 없음 |
| Pinterest Pin URL | 외부 링크 + 응답 전용 원격 썸네일 | 이미지 저장·스크래핑 금지, `pin_url`·상태만 저장 | 원본 `pin_url` 링크 · 원격 썸네일(`thumbnail_url`) |
| 경쟁 분석·페르소나 | 문서/사람 | 자체 관찰 — 출처 표기 원칙만 | (문서 전용) |
| LICENSE 파일 | — | **저장소에 없음** — 추가 여부 미결 | — |

---

## 2. 출처별 상세

### 2-1. 자체 TERM_CARD DB (팀 카드 — 런타임 단일 원본)

- 시드 자료: `term-cards/index.json` + index가 열거한 5개 역할 파일(`body`/`pose`/`view`/`perspective`/`layout`), 총 74개 고유 카드, 버전 `0.6-self-managed-term-card-store-draft`
- 런타임 단일 원본: 구현 후 자체 TERM_CARD DB. 역할별 JSON은 DB 적재 전 검수·시드 입력이며, 런타임 요청마다 읽지 않는다.
- 현재 활성 20: body 5 · pose 7 · view 4 · perspective 3 · layout 1. 런타임 조건: `runtime_eligible=true` **&&** `mvp_status=active_in_current_contract`
- 역할: LLM 출력·화면 피드백·Pinterest 검색어의 runtime single source of truth
- 확인 필요:
  - 카드 승인 기준 (누가·어떤 절차로 승인하는가)
  - 원저작·출처 필드 처리 (인용 표기, 검토 이력)
  - 승인되지 않은 카드를 "완료 카탈로그"로 주장하지 않는다는 규칙 유지

### 2-2. Getty AAT (조사 참고 자료)

- 용도: 팀이 용어를 조사할 때 참고하는 자료일 뿐 **서비스 데이터 출처가 아님**
- 계약 제약: Getty 객체·ID·URI·귀속·scope note를 역할별 JSON·자체 DB·MCP 응답·LLM 입력·사용자 화면에 저장하거나 표시하지 않는다. Getty API·SPARQL·웹 호출은 하지 않는다.
- 기존 진행 중이던 라이선스 확인은 참고 자료 가치 추적 목적으로만 유지 (런타임 의존 없음)

### 2-3. Pinterest Pin URL · 원격 썸네일

- 용도: 사용자가 외부에서 원본을 직접 확인하는 탐색 대상. UI는 원격 `thumbnail_url`을 원본 `pin_url` 링크로만 표시
- 정책: `pin_url`·Pin 상태만 세션 이력(1개월) 저장. 이미지 바이트·썸네일 URL·메타데이터 수집/저장/재게시/스크래핑 금지
- 스토어 정책: 검색 provider 반환 `status`는 `available` / `thumbnail_unavailable` / `deleted` — `thumbnail_unavailable`은 원본 링크만, `deleted`는 링크·썸네일 미표시
- Pinterest 검색 provider(Partner Search)·비즈니스 계정은 미확인 — `PinterestSearchProvider` 교체 가능 인터페이스 유지 (`PIN_SEARCH_UNAVAILABLE` 예약 코드)

### 2-4. 폴백 임시 용어

- **PR #15 계약에서 제거**: 폴백 LLM `FallbackTermOutput`·임시 후보 자동 생성은 사용하지 않는다.
- 자체 TERM_CARD DB에 없는 표현은 새 용어를 만들지 않고 추가 질문 또는 `pending_human_review` 상태로 처리한다. 자동 저장 금지.

### 2-5. LICENSE 파일

- 현재 저장소에 `LICENSE` 없음
- 추가 여부·라이선스 종류(예: 오픈소스 vs 내부용)를 결정해야 함 — 팀 코드·카드 데이터·문서 모두에 적용 범위 확인

---

## 3. 신뢰할 데이터와 한계 표시

| 데이터 | 근거 | 표시 |
| --- | --- | --- |
| 자체 TERM_CARD DB 카드 | 팀 검수 카드의 `label_ko`·`explanation_ko`·`look_for` | 용어·설명·확인 지점과 함께 |
| Pinterest 검색 결과 | provider 반환 `pin_url` + `thumbnail_url`(응답 전용) | 원본 Pin 링크·원격 썸네일 (`thumbnail_unavailable`/`deleted` 상태 구분) |

> 출처 필드는 "이 이미지/용어가 추천·저작권을 보증한다"로 오해되지 않도록, 출처와 한계를 항상 함께 표시한다. 원칙: **승인된 출처만 완료 카탈로그로 주장한다.** Getty·외부 어휘 주입은 없다.

---

## 4. 담당자·데드라인 (제안)

| # | 항목 | 담당(제안) | 데드라인(제안) |
| --- | --- | --- | --- |
| 1 | TERM_CARD 승인 기준 수립 (승인 절차·검토 이력) | 오세창 (도메인) | 9/23 (평가셋과 함께) |
| 2 | 자체 TERM_CARD DB schema·적재·repository 구현 계획 | 윤태현 (백엔드) | 10/8 마감 전 |
| 3 | Pinterest 렌더링·provider 승인 조건 정리 (원격 썸네일 정책 포함) | 김호섭 (프런트·MCP) | 예비 문서 9/25 |
| 4 | `pending_human_review` 검토 게이트 정의 | 오세창 + 윤태현 | 9/23 |
| 5 | `LICENSE` 추가 여부·종류 결정 | 팀 회의 | 9/26 이전 |
| 6 | Pin `status`·썸네일 표시 규칙 스키마 반영 | 윤태현 (스키마) | 스키마 확정 PR과 동시 |

### 추가 합의 포인트

| # | 결정 포인트 | 옵션 | 권장 |
| --- | --- | --- | --- |
| 7 | 카드 승인 전 "미완성 카탈로그" 표기 | README·EVAL에 상태 명시 유지 | 유지 (승인된 출처만 완료로 주장) |
| 8 | Pinterest 검색 API 미승인 시 | 자체 DB 검색어 링크만 제공, provider 미구현 | `PinterestSearchProvider` 교체 가능 유지 — 시점 정의 |

---

## 5. Next Task

1. 담당자·데드라인 확정 → README에 출처별 검증 상태 표 갱신
2. 자체 TERM_CARD DB schema·시드 적재 계획 확정 (SDD §4와 연동)
3. `LICENSE` 추가 판단 (추가 시 저장소에 반영)
4. Pin `status`·원격 썸네일 표시 규칙을 `input-output-pydantic-schema.md`(PinResult)와 정합화
5. 평가셋: 출처 필드·Pin 상태 구분·`pending_human_review` 케이스 포함 (9/23 마일스톤)