# Spec — Booru 태그 참고용 TERM_CARD 실험 후보 검토

> **상태: 완료.** 이 문서는 후보 검토 단계의 원래 범위를 기록한다. 검수 완료 8개 후보는 2026-09-23에 로컬 활성 카탈로그로 승격됐으며, 현재 승격 계약과 결과는 `docs/specs/term-card-candidate-data-promotion.md`를 따른다. 아래의 비활성 상태·ID 비중복·무변경 검증은 **승격 전 후보 검토 시점의 이력**이며, 현재 작업 트리나 이 PR의 최종 상태를 판정하는 규칙이 아니다.

## Why

- **페르소나**: 캐주얼 캐릭터 일러스트 레퍼런스를 찾는 초보자와, TERM_CARD를 검수하는 팀 구성원
- **상황**: 현재 런타임 카탈로그의 74개 카드는 모두 사람 검수를 거쳐 활성화되어 있다. 새 용어를 추가하기 전에 외부 태그 체계가 일반적인 영문 검색어 후보를 보완하는지 작은 규모로 검토하려 한다.
- **문제**: 외부 Booru 태그를 그대로 카드나 런타임 검색어에 넣으면, 팀의 검수 책임·카탈로그 단일 원본·외부 데이터 미저장 계약이 흐려질 수 있다.
- **측정 지표(후보 검토 시점)**: 기존 활성 카드와 평가 JSONL의 `term_id` 중복 0건, 검수 유지 후보 8건 모두 런타임 비활성, 검수 후 자동 승격 0건

## Goal

- `pose` 6건과 `view` 2건으로 구성된 검수 완료 후보 8건을 별도 JSON 파일에 기록한다.
- 후보 파일은 검수 완료 시점·유지 후보 수·제외 후보 수를 기록하고, 개별 후보의 검수 상태를 `reviewed`로 표시한다.
- 각 후보에는 활성 카드 승격 시 fallback으로 쓸 `source_answer_draft`를, 파일 최상단에는 `active_term_feedback`과 같은 형식의 `active_term_feedback_draft`를 기록한다.
- **Out of Scope(후보 검토 시점)**: 기존 5개 역할 JSON·`index.json`·API·MCP·Skill·평가셋 변경, 런타임 로드, Pinterest 또는 Booru 호출, 이미지·게시물·태그 원문·프롬프트 저장, 자동 승격. 이후 승인된 데이터 승격 범위는 별도 Spec에서 관리한다.

## What

**Happy Path**

1. 작성자는 활성 74개 카드와 `evals` JSONL에서 기존 `term_id`를 수집한다.
2. 사람 검수는 초안 10건 중 현재 사용하지 않는 2건을 제외하고 8건을 유지한다.
3. 각 유지 후보는 역할, 한·영 라벨, 팀이 작성한 `candidate_query_fragments`, `source_answer_draft`, 관찰 기준, 혼동 금지 조건, `reviewed` 상태를 가진다.
4. 파일의 `review_summary`는 검수 완료일, 유지 8건, 제외 2건을 기록한다.
5. `active_term_feedback_draft`는 유지 후보별 쉬운 뜻, 선택 근거, Pinterest 검색 안내, 확인 지점, 혼동 안내, 추가 질문을 모두 기록한다.
6. 검수 완료 후보는 별도 데이터 승격 변경에서 API 계약·Skill·평가셋 검토를 거쳐 활성 역할 JSON으로 승격한다. 이 후속 결과는 `term-card-candidate-data-promotion.md`에 기록한다.

**Edge Cases**

| # | 상황 | 처리 방식 |
|---|---|---|
| EC-01 | 후보 `term_id`가 기존 카드 또는 평가셋에 있음 | 해당 후보를 유지하지 않고 검수에서 제외한다. |
| EC-02 | 외부 태그 조회가 timeout·TLS 오류·차단으로 실패함 | 후보의 외부 교차검증 상태를 `not_verified`로 기록하고, 검수자에게 성공으로 표시하지 않는다. |
| EC-03 | 후보가 일상어 감정·스타일·작가명처럼 구체 시각 단서가 아님 | 후보에서 제외한다. |
| EC-04 | 후보가 기존 활성 카드와 같은 물리적 자세·시점을 뜻함 | 별도 후보로 만들지 않고 중복으로 판단한다. |
| EC-05 | 후보 파일이 런타임 index에 연결됨 | 검증 실패로 처리하고 index 변경을 되돌린다. |

## How

- **파일 경계**: 후보는 `docs/domains/illustration-reference/term-cards/candidates/booru-crosscheck-candidates.json` 한 파일에만 둔다. 이 경로는 `index.json`의 `categories`에 포함하지 않으므로 현재 loader가 읽지 않는다.
- **입력 계약**: 후보 생성 전 역할 JSON 5개에서 모든 `term_id`를, `evals/**/*.jsonl`에서 참조되는 `term_id`를 수집한다. 새 후보 ID는 두 집합 모두에 없어야 한다.
- **출력 계약**: 파일 최상단에는 `document_type`, `status`, `review_summary`, `runtime_contract`, `research_boundary`, `candidates`, `active_term_feedback_draft`를 둔다. 후보 검토 시점의 `status`는 `reviewed_not_promoted`였고, 현재 감사 파일은 승격 이력을 나타내는 `promoted_to_runtime` 상태다. `review_summary`는 유지 8건·제외 2건·검수 완료일을 기록한다. 각 후보는 `term_id`, `role`, `label_ko`, `label_en`, `candidate_query_fragments`, `source_answer_draft`, `look_for`, `confidence_gate`, `review_status`, `runtime_eligible`, `mvp_status`, `crosscheck`를 포함한다. `review_status`는 `reviewed`다. `active_term_feedback_draft`는 유지 후보의 `term_id`와 정확히 같은 키를 가지며, 각 값은 `plain_meaning_ko`, `selection_reason_template_ko`, `pinterest_search_notice_ko`, `reference_checkpoints_ko`, `common_confusion_ko`, `clarifying_question_ko`, `review_status`를 포함한다. `candidate_query_fragments`에는 검수자가 라벨 적합성을 확인한 표준 용어 조각을 둔다. 중복된 `pose reference`는 저장하지 않지만, `full body reference`처럼 `drawing` 접미사가 붙는 최종 Pinterest 검색어의 라벨 적합성을 위해 검수자가 선택한 `reference` 조각은 허용한다. `drawing` 자체는 저장하지 않으며 향후 검색 URL 생성 코드가 붙이는 책임을 가진다.
- **책임 분리**: 후보 파일은 팀 검수 입력일 뿐 `get_active_term_card` 또는 Pinterest 검색 provider의 입력이 아니다. 런타임 loader는 index가 선언한 5개 파일과 `runtime_eligible=true && mvp_status=active_in_current_contract` 조건만 신뢰한다.
- **외부 연동 및 제약**: Booru-Pictag 계열은 개발 단계에서 일반 영문 태그·별칭을 조사하는 참고 수단일 뿐 런타임 의존성이 아니다. 현재 작성 환경에서 공개 autocomplete 조회가 실패했으므로, 이 배치의 `crosscheck.status`는 `not_verified`로 고정한다. 외부 응답, 게시물 ID·URL, 이미지, 위키 본문, 프롬프트, 작가·캐릭터·저작권 태그는 파일에 저장하지 않는다.
- **검증**: JSON 파싱, 후보 수 8건, `review_summary.review_completed=true`, 후보 ID 전역 고유성, 모든 후보의 `source_answer_draft`·`review_status=reviewed`·`runtime_eligible=false`, `active_term_feedback_draft`의 키 일치와 필수 초보자 UX 필드 비어 있지 않음을 확인한다. `status=reviewed_not_promoted`, 기존 카드·평가 JSONL과의 ID 교집합 0건, `index.json`과 기존 역할 JSON 무변경은 승격 전 후보 검토 시점의 검증 기록이다. 승격 후 최종 정합성은 데이터 승격 Spec의 AC로 검증한다.

## AC (Given-When-Then)

**AC-01 · 중복 없는 실험 후보**

- GIVEN: 현재 역할 JSON 5개와 `evals` 아래의 JSONL 파일
- WHEN: 8개 검수 완료 후보의 `term_id`를 수집한다
- THEN: 후보끼리, 기존 카드와, 평가 JSONL 참조 ID와 각각 중복이 0건이다

**AC-02 · 런타임 격리**

- GIVEN: 후보 JSON 파일과 현재 `index.json`
- WHEN: index의 category 파일 목록을 확인한다
- THEN: 후보 파일은 목록에 없고, 모든 후보는 `runtime_eligible=false` 및 `mvp_status=candidate_outside_current_contract`다

**AC-03 · 외부 데이터 경계**

- GIVEN: 후보 JSON의 `research_boundary`와 각 후보의 `crosscheck`
- WHEN: 파일 내용을 검사한다
- THEN: `not_verified` 상태가 사실대로 기록되고 외부 응답·게시물·이미지·프롬프트·작가·캐릭터·저작권 태그가 저장되어 있지 않다

**AC-04 · 검수 가능한 최소 정보**

- GIVEN: 후보 JSON의 검수 완료 8개 항목
- WHEN: 검수자가 한 항목을 연다
- THEN: 역할, 한·영 용어, 중복된 `pose reference`와 `drawing`을 저장하지 않은 팀 작성 검색 조각, fallback 설명, 관찰 기준, 혼동 금지 조건, 검수 상태를 확인할 수 있다. 검수자가 최종 Pinterest 검색어 적합성을 이유로 선택한 `reference` 조각은 예외로 허용한다.

**AC-05 · 초보자 UX 초안 완결성**

- GIVEN: 후보 JSON의 `active_term_feedback_draft`
- WHEN: 유지 후보 8개와 feedback 초안의 키·필드를 비교한다
- THEN: 키가 정확히 일치하고, 각 후보에 쉬운 뜻·선택 근거·검색 안내·확인 지점·혼동 안내·추가 질문이 비어 있지 않으며 `review_status=reviewed`다
