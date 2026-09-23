# Spec — 검수 완료 TERM_CARD 후보의 로컬 카탈로그 승격

## Why

- **페르소나**: 캐주얼 캐릭터 일러스트 레퍼런스를 찾는 초보자와, 팀 TERM_CARD 카탈로그를 관리하는 검수자
- **상황**: `pose` 6개와 `view` 2개 후보는 사람 검수와 초보자 UX 초안을 마쳤지만 현재 index 밖의 후보 파일에 있어 Agent가 선택할 수 없다.
- **문제**: 검수 완료 후보를 활성 역할 JSON·초보자 피드백·Skill에 같은 상태로 옮기지 않으면, 용어 선택·검색 계획·화면 설명이 서로 다른 카탈로그를 보게 된다.
- **측정 지표**: 활성 카드 74→82, 전역 `term_id` 중복 0건, 신규 8개 모두 활성 조건 충족, 신규 8개 모두 초보자 UX 필드 완결, 후보 파일의 승격 기록 1건

## Goal

- `pose` 후보 6개를 `pose.json`에, `view` 후보 2개를 `view.json`에 팀 관리 활성 카드로 추가한다.
- `index.json`의 카운트·버전·초보자 피드백을 82개 활성 카드 상태로 동기화한다.
- 후보 파일은 검수·승격 이력으로 남기되, 런타임 loader의 입력으로 만들지 않는다.
- **Out of Scope**: backend·MCP·LLM·Pinterest URL 생성 코드 구현, 외부 Booru 호출, 평가 실행, Git commit·push·Pull Request 생성

## What

**Happy Path**

1. 검수 완료 후보 8개를 역할별 활성 JSON에 추가한다.
2. 각 카드에 `source_type=team_card`, `query_fragments`, `source_answer_draft`, 검수자·검수일, 활성 상태를 기록한다.
3. `index.json`의 `active_term_feedback`에 후보의 초보자 UX 초안을 동일한 `term_id`로 추가한다.
4. index의 활성 카드 수와 역할별 카드 수, 버전·검수 범위를 갱신한다.
5. 후보 파일에는 어떤 후보가 어느 역할 JSON으로 승격됐는지 기록한다.
6. JSON·전역 ID·피드백 연결·활성 상태를 정적 검증한다.

**Edge Cases**

| # | 상황 | 처리 방식 |
|---|---|---|
| EC-01 | 신규 `term_id`가 기존 활성 카드와 중복 | 해당 카드를 추가하지 않고 검증 실패로 처리한다. |
| EC-02 | 후보의 초보자 UX 초안이 누락·빈 값 | 활성 피드백으로 복사하지 않고 검증 실패로 처리한다. |
| EC-03 | 후보 파일을 index category에 추가하려 함 | 후보 파일은 이력용이므로 추가하지 않고 검증 실패로 처리한다. |
| EC-04 | 외부 태그 원문·게시물·이미지 정보를 활성 카드로 옮기려 함 | 활성 카드에는 팀 작성 용어·설명·검색 조각만 옮기고 외부 메타데이터는 제외한다. |
| EC-05 | 런타임 코드가 아직 카탈로그를 읽지 않음 | 데이터 승격 결과만 검증하고, 런타임 호출 검증은 별도 구현 Spec으로 남긴다. |

## How

- **승격 대상**: `pose_hands_on_hips`, `pose_arms_crossed`, `pose_hands_behind_back`, `pose_hand_on_chin`, `pose_hand_on_chest`, `pose_salute`를 `pose.json`에, `view_over_the_shoulder`, `view_full_body`를 `view.json`에 추가한다.
- **카드 변환**: 후보의 `candidate_query_fragments`는 활성 카드의 `query_fragments`로 복사한다. `source_type`은 `team_card`, `source_category_id`는 `booru_crosscheck_candidates_reviewed`, `reviewed_by`는 기존 카탈로그와 같은 `오세창`, `reviewed_at`은 `2026-09-23`으로 기록한다. `runtime_eligible=true`, `mvp_status=active_in_current_contract`, `review_status=reviewed`로 설정한다.
- **외부 데이터 경계**: `crosscheck`, 외부 조회 상태, 외부 게시물·이미지·위키·프롬프트·작가·작품·인물 태그는 활성 역할 JSON과 index 피드백에 복사하지 않는다.
- **초보자 UX**: 후보 파일의 `active_term_feedback_draft` 8개를 index의 `active_term_feedback`으로 복사한다. 키는 활성 카드 ID와 정확히 일치하고, `plain_meaning_ko`, `selection_reason_template_ko`, `pinterest_search_notice_ko`, `reference_checkpoints_ko`, `common_confusion_ko`, `clarifying_question_ko`, `review_status`를 모두 유지한다.
- **카탈로그·문서 갱신**: index의 `dataset_version`은 `0.8-json-runtime-catalog-reviewed`, `card_count`는 82, pose·view 카테고리 수는 58·11로 바꾼다. `SOURCE_PROVENANCE.md`와 `skills/SKILL.md`의 활성 카드 수·승격 기록도 82개에 맞춘다.
- **후보 이력**: 후보 파일은 index에 넣지 않고 `promotion`에 승격 일자, 대상 ID, 역할별 대상 파일, 이 변경이 데이터 카탈로그만 갱신했다는 사실을 기록한다.
- **검증 한계**: backend와 MCP가 아직 카탈로그 loader를 구현하지 않았으므로, 이번 변경은 JSON 데이터 계약의 정적 검증까지만 수행한다.

## AC (Given-When-Then)

**AC-01 · 신규 활성 카드 추가**

- GIVEN: 검수 완료 후보 8개와 기존 활성 역할 JSON
- WHEN: 역할별 JSON의 모든 카드를 수집한다
- THEN: 총 82개이고 신규 8개의 `term_id`는 전역 고유하며 `runtime_eligible=true`, `mvp_status=active_in_current_contract`, `source_type=team_card`다

**AC-02 · 초보자 UX 연결**

- GIVEN: 신규 활성 카드와 `index.json`의 `active_term_feedback`
- WHEN: 신규 8개 ID별 피드백을 확인한다
- THEN: 각 ID에 여섯 가지 초보자 UX 필드와 `review_status=reviewed`가 비어 있지 않다

**AC-03 · 카탈로그 메타데이터 동기화**

- GIVEN: index와 역할별 JSON
- WHEN: card_count와 category card_count를 실제 카드 수와 비교한다
- THEN: index는 82, pose는 58, view는 11이며 후보 파일은 index category에 없다

**AC-04 · 외부 데이터와 런타임 코드의 경계**

- GIVEN: 신규 활성 카드·index 피드백·후보 이력 파일
- WHEN: 외부 메타데이터와 변경 파일을 검사한다
- THEN: 활성 카탈로그에 외부 게시물·이미지·위키·프롬프트·작가·작품·인물 태그가 없고, backend·MCP 코드는 변경되지 않는다
