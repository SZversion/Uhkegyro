# 도메인 지식 출처 정리 (라이선스) — 강사님 회의(2026-09-22) 접수·확정

**팀**: 4조 (UH케그려)
**작성일**: 2026-09-22
**작성자**: 윤태현 (YTH)
**상태**: 강사님 회의(2026-09-22) 반영 · 출처별 검증·라이선스 담당자·데드라인 지정 필요
**근거 문서**:
- `README.md` §"도메인 데이터와 출처 경계" — TERM_CARD JSON·Pinterest 출처 경계
- `NOT_BUILD.md` — 수집·저장·재게시 금지 범위
- `docs/specs/getty-term-resolution-pipeline.md`·`vocabulary-provider-seam.md` — Getty 라이선스 확인 필요 명시
- PRD — "승인된 출처만 완료 카탈로그로 주장한다"

---

## 1. 한눈에 보기

| 출처 | 형태 | 검증·라이선스 상태 | 출력 표시 |
| --- | --- | --- | --- |
| TERM_CARDS_MASTER_100_DRAFT.json | 팀 카드 (100개 / 활성 20, v0.2-draft) | **승인 기준 미정**, 원저작·출처 처리 미확인 | term ID·설명·query_fragment |
| Getty AAT (SPARQL) | 외부 API | **라이선스 미확인** — 배포 전 공식 문서 재확인 필요 | `getty_aat` URI·label·출처 (카드 기록값) |
| Pinterest Pin URL | 외부 링크만 | 이미지 저장·스크래핑 금지, 링크만 저장 | 공식 `embedPin` 미리보기 |
| LLM 폴백 임시 후보 | 임시 | **자동 저장 금지**, 사람 검토 게이트 필수 | `llm_fallback` 출처 + 명시 한계 문구 |
| 경쟁 분석·페르소나 | 문서/사람 | 자체 관찰 — 출처 표기 원칙만 | (문서 전용) |
| LICENSE 파일 | — | **저장소에 없음** — 추가 여부 미결 | — |

---

## 2. 출처별 상세

### 2-1. TERM_CARDS_MASTER_100_DRAFT.json (팀 카드 — 단일 원본)

- 100장, 현재 활성 20 (body 5 · pose 7 · view 4 · perspective 3 · layout 1), 버전 `0.2-draft`
- 런타임 조건: `runtime_eligible=true` **&&** `mvp_status=active_in_current_contract`
- 역할: LLM 출력·화면 피드백·Pinterest 검색어의 single source of truth
- 확인 필요:
  - 카드 승인 기준 (누가·어떤 절차로 승인하는가)
  - 원저작·출처 필드 처리 (인용 표기, 검토 이력)
  - 승인되지 않은 카드를 "완료 카탈로그"로 주장하지 않는다는 규칙 유지

### 2-2. Getty AAT (SPARQL)

- 용도: 선택 카드의 용어 출처 근거 (전문 용어 라벨·URI)
- 계약 제약: `VocabularyCandidateProvider` 교체 지점 — 후보의 `source_name`·`source_url`은 공급자가 제공, 서버는 Getty로 고정 표기하지 않음
- **라이선스 미확인**: 배포 전 Getty 공식 문서로 재확인 필요 (getty 스펙 명시)
- 금지: Getty label·URI를 Pinterest 검색어로 사용하거나 LLM 프롬프트·RAG에 자동 주입

### 2-3. Pinterest Pin URL

- 용도: 사용자가 외부에서 원본을 직접 확인하는 탐색 대상
- 정책: URL만 세션 저장, 이미지·썸네일·메타데이터 수집/저장/재게시/스크래핑 금지
- 렌더링: 공식 `pinit.js` `embedPin`만 사용. Pin 삭제·네트워크 오류 분리가 불가하면 `render_error`로 처리
- Pinterest API(Partner Search)는 **팀 승인 + API 접근 승인** 후 별도 기능 Spec에서만 활성화 (`PINTEREST_RESULTS_UNAVAILABLE` 예약 코드)

### 2-4. LLM 폴백 임시 후보

- 조건: Getty·팀 카드 모두 해당 역할 용어를 제공하지 못할 때만 3rd LLM 폴백 1회 호출
- 정책: `temporary=true`·`requires_human_review=true`·`source_label_ko="임시 용어 후보"`·`source_notice_ko` 필수
- 금지: 자동 저장(카드·Skill·DB·평가셋 정답), `getty_aat`·`term_cards` 출처로 표시
- 사람 검토 게이트 후에만 카탈로그 승인 가능

### 2-5. LICENSE 파일

- 현재 저장소에 `LICENSE` 없음
- 추가 여부·라이선스 종류(예: 오픈소스 vs 내부용)를 결정해야 함 — 팀 코드·카드 데이터·문서 모두에 적용 범위 확인

---

## 3. 응답의 출처 필드 (항상 반환)

| 출처 필드 | 값 | 표시 |
| --- | --- | --- |
| `getty_aat` | `{subject_uri, label, source_name, source_url}` | 용어와 함께 (카드 기록값 그대로) |
| `term_cards` | 팀 카드 label·관찰 기준 | 출처 라벨·한계와 함께 |
| `llm_fallback` | 임시 후보 + `requires_human_review` | **"검증된 출처가 아닌 임시 후보" 경고 문구 필수** |

> 출처 필드는 "이 이미지/용어가 추천·저작권을 보증한다"로 오해되지 않도록, 출처와 한계를 항상 함께 표시한다. 원칙: **승인된 출처만 완료 카탈로그로 주장한다.**

---

## 4. 담당자·데드라인 (제안)

| # | 항목 | 담당(제안) | 데드라인(제안) |
| --- | --- | --- | --- |
| 1 | TERM_CARDS 승인 기준 수립 (승인 절차·검토 이력) | 오세창 (도메인) | 9/23 (평가셋과 함께) |
| 2 | Getty AAT 라이선스 재확인 (공식 문서) | 윤태현 (백엔드) | 배포 전 (10/8 마감 전) |
| 3 | Pinterest 렌더링·API 승인 조건 정리 | 김호섭 (프런트·MCP) | 예비 문서 9/25 |
| 4 | LLM 폴백 사람 검토 게이트 정의 | 오세창 + 윤태현 | 9/23 |
| 5 | `LICENSE` 추가 여부·종류 결정 | 팀 회의 | 9/26 이전 |
| 6 | 응답 출처 필드 복합 상시 반환 명세 | 윤태현 (스키마) | 스키마 확정 PR과 동시 |

### 추가 합의 포인트

| # | 결정 포인트 | 옵션 | 권장 |
| --- | --- | --- | --- |
| 7 | 카드 승인 전 "미완성 카탈로그" 표기 | README·EVAL에 상태 명시 유지 | 유지 (승인된 출처만 완료로 주장) |
| 8 | Getty 라이선스 결과가 부정적일 때 | 폴백·교체(자체 DB)로 전환 | `VocabularyCandidateProvider` 계약으로 교체 가능 — 교체 시점 정의 |

---

## 5. Next Task

1. 담당자·데드라인 확정 → README에 출처별 검증 상태 표 갱신
2. Getty AAT 라이선스 공식 문서 확인 → 결과를 스펙·README에 기록
3. `LICENSE` 추가 판단 (추가 시 저장소에 반영)
4. 응답 출처 필드 3종 스키마 반영 (`input-output-pydantic-schema.md`의 `getty_aat` 참조 — `RoleResult`와 정합화)
5. 평가셋: 출처 필드·임시 후보 한계 표시 케이스 포함 (9/23 마일스톤)