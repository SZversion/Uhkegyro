> **2026-09-21 폐기됨:** 이 출처 보강 작업은 되돌렸으며 외부 어휘 메타데이터를 다시 추가하지 않는다. 현재 TERM_CARD 계약은 `docs/specs/self-managed-term-card-store.md`를 따른다.

# Getty AAT TERM_CARD 보강 (historical)

## Why

- **페르소나**: 캐주얼 캐릭터 일러스트 레퍼런스 Agent의 용어 카드와 출처를 관리하는 팀원.
- **상황**: 체형·포즈·시점·원근·구도 카드를 검토할 때, 팀 내부 검색어만으로는 용어의 출처와 의미 범위를 일관되게 확인하기 어렵다.
- **문제**: Getty AAT의 표준 용어·URI·범위 설명을 카드에 남기지 않으면 이후 MCP 조회와 자체 DB 실험에서 같은 의미의 용어를 재매핑해야 한다.
- **측정 지표**: 신규 4개 후보 카드에 Getty AAT ID·선호 용어·URI·출처가 모두 있고, 기존 후보/활성 카드 중 직접 대응하는 10개 카드가 동일 형식의 출처 정보를 가지며, 74개 카드의 역할별 수와 index가 일치한다.

## Goal

- **해결 목표**: Getty AAT와 직접 대응하는 일러스트 레퍼런스 용어를 기존 5개 역할 파일에 보강하고, 각 카드가 Getty URI 및 한국어 매핑 설명을 가진다.
- **성공 기준**: `body` 6개, `pose` 52개, `view` 9개, `perspective` 5개, `layout` 2개로 총 74개 카드가 조립되며, 추가 카드와 기존 후보는 `runtime_eligible=false`를 유지한다.
- **Out of Scope**: 후보 카드 승격, 활성 20개 카드의 선택 조건 변경, Pinterest 검색 실행, Getty MCP 실제 호출, 이미지·본문 수집, API·UI·DB 구현, 장르 또는 역할 추가.

## What

**Happy Path**

1. 관리 도구가 `term-cards/index.json`과 5개 역할 파일을 읽는다.
2. 각 Getty 연계 카드는 `getty_aat.aat_id`, `preferred_label`, `uri`, `source_attribution`, `mapping_note`로 출처와 프로젝트 매핑 범위를 제공한다.
3. 새 `body_human_proportion`, `perspective_one_point`, `perspective_two_point`, `layout_composition`은 후보 카드로 저장되고 현재 MVP 선택 대상에서는 제외된다.
4. 기존 후보 포즈·시점 카드와 활성 원근 카드 중 Getty AAT에 직접 대응하는 항목은 기존 검색 조각과 선택 조건을 보존한 채 출처만 보강한다.

**Edge Cases**

| # | 상황 | 처리 방식 |
|---|---|---|
| EC-01 | Getty AAT에 정확히 대응하는 용어가 없음 | 새 카드를 만들지 않고 기존 `team_card`를 유지한다. |
| EC-02 | Getty 용어가 프로젝트 카드보다 넓거나 좁음 | `mapping_note`에 범위 차이를 적고, 기존 검색 조각·confidence gate를 바꾸지 않는다. |
| EC-03 | 후보 카드의 출처는 있으나 팀 검수가 끝나지 않음 | `reviewed_by`·`reviewed_at`을 `null`로 두고 `runtime_eligible=false`를 유지한다. |
| EC-04 | index 수와 역할 파일 카드 수가 다름 | 검증 오류로 처리하고 카드를 부분 로드하지 않는다. |
| EC-05 | Getty 서비스가 timeout 또는 미존재를 반환함 | 런타임은 자체 TERM_CARD를 사용하며, 이 정적 출처 메타데이터만으로 외부 호출 성공을 주장하지 않는다. |

## How

- 대상 데이터: `docs/domains/illustration-reference/term-cards/{body,pose,view,perspective,layout}.json`과 `index.json`.
- 외부 출처: Getty Art & Architecture Thesaurus(AAT). 카드에는 `https://vocab.getty.edu/aat/{aat_id}` URI와 `Getty Art & Architecture Thesaurus` attribution을 저장한다. Getty 용어·URI는 구조화된 출처 메타데이터로만 사용하며, Getty 이미지 또는 본문을 학습·RAG 데이터로 저장하지 않는다.
- 역할별 추가 범위: `body`에는 `human proportion`, `perspective`에는 `one-point perspective (technique)`·`two-point perspective (perspective system)`, `layout`에는 `composition (artistic arrangement)`만 추가한다. `pose`와 `view`는 이미 있는 직접 대응 후보 카드에만 Getty 메타데이터를 보강한다.
- 새 후보 상태: `candidate_body`, `candidate_perspective`, `candidate_layout`을 index의 `status_definitions`에 추가한다. 새 카드의 `review_status`는 `needs_osechang_review`이고, 검수자·검수일은 비워 둔다.
- 런타임 계약: 현재 로더는 `runtime_eligible=true && mvp_status=active_in_current_contract`만 선택한다. 이번 변경은 그 두 조건을 충족하는 새 카드를 만들지 않으며, 활성 카드의 `query_fragments`, confidence gate, 활성 상태를 변경하지 않는다.
- Pinterest 계약: 검색어는 카드의 짧은 `query_fragments`만 사용한다. 후보는 런타임에 선택되지 않으므로 링크 생성 대상도 아니다.

## AC (Given-When-Then)

**AC-01 · Getty 출처가 있는 후보 추가**

- GIVEN: 5개 역할 파일과 index가 있다.
- WHEN: Getty AAT 보강 후 카드를 조립한다.
- THEN: `body_human_proportion`, `perspective_one_point`, `perspective_two_point`, `layout_composition`은 Getty ID·선호 용어·URI·출처·매핑 설명을 가지며 `runtime_eligible=false`이다.

**AC-02 · 기존 직접 대응 카드 보강**

- GIVEN: 기존의 무릎 꿇기·걷기·달리기·측면·뒷면·조감·개미 눈높이·3점 투시·단축법·소실점 카드가 있다.
- WHEN: Getty AAT 메타데이터를 적용한다.
- THEN: 카드의 역할·`term_id`·검색 조각·confidence gate·활성 여부는 보존되고, 직접 대응하는 Getty URI와 매핑 설명이 추가된다.

**AC-03 · 후보 비노출 보존**

- GIVEN: 현재 MVP 선택 규칙이 적용된다.
- WHEN: 보강된 카드 집합을 필터링한다.
- THEN: 활성 카드는 기존과 같이 총 20개이고, 이번에 추가한 4개 후보는 LLM 허용 `term_id`와 Pinterest 검색 계획에 포함되지 않는다.

**AC-04 · index 동기화**

- GIVEN: 역할별 JSON과 index가 있다.
- WHEN: 역할별 `card_count`와 모든 카드의 고유 `term_id`를 검증한다.
- THEN: 역할별 수는 6·52·9·5·2이고 합계는 74이며, 중복 `term_id`는 0개다.
