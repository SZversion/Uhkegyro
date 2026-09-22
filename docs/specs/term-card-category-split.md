# TERM_CARD 카테고리 파일 분리

## Why

- **페르소나**: 캐주얼 캐릭터 일러스트 레퍼런스 Agent의 도메인 카드와 검수 데이터를 관리하는 팀원.
- **상황**: 단일 JSON에서 현재 MVP에 필요한 체형·포즈·시점·원근·구도 카드를 함께 수정한다.
- **문제**: 역할별 검수·변경 범위를 빠르게 확인하기 어렵고, 서로 다른 역할의 카드 수정 충돌 가능성이 크다.
- **측정 지표**: 분리 뒤 index 카드 수 74개, `term_id` 중복 0개, 역할별 카드 수와 활성 카드 수가 index와 일치한다.

## Goal

- **해결 목표**: 현재 MVP 선택 역할(`body`, `pose`, `view`, `perspective`, `layout`)별 JSON 5개와 이를 나열하는 단일 index를 만든다.
- **성공 기준**: index의 역할별 `card_count` 합계가 74이고, 포함된 카드의 원래 필드·값·검수 상태·활성 조건이 보존된다.
- **Out of Scope**: 카드 내용·전문용어·검수 결과 변경, 후보 카드 승격, `detail`·`intent`·`style` 역할 보관·분리, LLM·MCP·Pinterest·UI 구현, 자체 DB의 실제 schema·migration·seed runner 구현.

## What

**Happy Path**

1. 시드 적재 도구는 `term-cards/index.json`을 읽는다.
2. index의 `categories` 순서대로 역할별 파일을 검증해 하나의 시드 카드 집합으로 조립한다.
3. 자체 TERM_CARD DB에 적재된 뒤 `runtime_eligible=true && mvp_status=active_in_current_contract` 조건을 적용한 카드만 런타임 선택 후보가 된다.

**Edge Cases**

| # | 상황 | 처리 방식 |
|---|---|---|
| EC-01 | index에 적힌 파일이 없음 | 시드 적재를 중단하고 `TERM_CARD_STORE_UNAVAILABLE` 운영자 오류로 처리한다. |
| EC-02 | index의 `card_count`와 실제 파일 수가 다름 | 검증 오류로 처리하고 카드를 부분 로드하지 않는다. |
| EC-03 | 역할 파일의 카드 `role`이 파일 역할과 다름 | 검증 오류로 처리한다. |
| EC-04 | 여러 파일에 같은 `term_id`가 있음 | 검증 오류로 처리한다. |
| EC-05 | 비활성 후보 카드가 포함됨 | 저장은 허용하되 현재 선택 후보로 노출하지 않는다. |

## How

- 기준 index: `docs/domains/illustration-reference/term-cards/index.json`
- 역할 파일: `body.json`, `pose.json`, `view.json`, `perspective.json`, `layout.json`
- index는 기존 전역 메타데이터·초보자 피드백·활성 용어 피드백·상태 정의와 카테고리 파일 목록만 가진다.
- 역할 파일은 `role`, `card_count`, `cards`만 가진다. 포함된 카드 객체의 필드와 값은 분리 전 원본에서 기계적으로 이동한다.
- `detail`, `intent`, `style`은 `candidate_only_roles`였으므로 현재 MVP dataset과 index의 `categories`에서 제외한다. 같은 5개 역할 안의 `runtime_eligible=false` 후보 카드는 유지하되 현재 선택 후보로 노출하지 않는다.
- 이전 `TERM_CARDS_MASTER_100_DRAFT.json` 경로는 새 index를 가리키는 비카드 리다이렉트 JSON으로만 남긴다. 카드 로더의 입력으로 사용하지 않는다.
- 시드 적재 도구는 index에 있는 파일만 읽는다. 디렉터리 전체 탐색으로 임의 JSON을 자동 로드하지 않는다. 런타임 Card repository는 JSON을 읽지 않고 자체 TERM_CARD DB만 조회한다.
- Getty 데이터는 역할별 JSON·index·자체 TERM_CARD DB에 넣지 않는다. Getty는 용어 조사 시 참고한 자료일 뿐 런타임 데이터가 아니다.
- index의 `source_documents`는 저장소에 실제 존재하는 `SOURCE_PROVENANCE.md`만 가리킨다. 기존 작업 초안 파일명은 그 문서에서 이력으로만 기록하며, 누락된 파일 경로를 데이터 계약에 넣지 않는다.
- 이 분리만으로 현재 공개 API·LLM 출력 계약·실패 상태·Pinterest 검색 조각은 변경하지 않는다.

## AC (Given-When-Then)

**AC-01 · 역할별 파일 조립**

- GIVEN: 유효한 `index.json`과 5개 역할 파일이 있다.
- WHEN: 시드 적재 도구가 index의 `categories`를 순서대로 읽는다.
- THEN: 총 74개의 고유 `term_id` 카드가 조립되어 자체 TERM_CARD DB 적재 후보가 되고 역할별 수가 index와 일치한다.

**AC-02 · 활성 카드 보존**

- GIVEN: 분리 전 활성 카드 조건이 적용돼 있다.
- WHEN: 자체 TERM_CARD DB의 적재 카드 집합을 필터링한다.
- THEN: `body` 5개, `pose` 7개, `view` 4개, `perspective` 3개, `layout` 1개로 총 20개가 런타임 선택된다.

**AC-03 · 후보 카드 비노출**

- GIVEN: `runtime_eligible=false`인 후보 카드가 역할 파일에 있다.
- WHEN: 현재 MVP 선택 후보를 만든다.
- THEN: 후보 카드는 화면·LLM 허용 `term_id`·Pinterest 검색 계획에 포함되지 않는다.

**AC-04 · 파일 불일치 차단**

- GIVEN: index의 수 또는 파일 역할과 실제 카드가 일치하지 않는다.
- WHEN: 시드 적재 도구가 검증한다.
- THEN: 부분 결과를 만들지 않고 적재를 중단한다. 런타임에는 마지막으로 검증된 자체 TERM_CARD DB만 사용한다.
