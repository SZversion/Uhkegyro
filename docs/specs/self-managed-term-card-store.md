# 자체 관리 TERM_CARD 저장소 전환

## Why

- **페르소나**: 일러스트 레퍼런스 Agent의 용어 데이터와 검수 기준을 관리하는 팀원.
- **상황**: 프로젝트는 외부 어휘 API를 조회하지 않고 팀이 관리하는 TERM_CARD만으로 용어 선택·설명·검색 계획을 제공하기로 결정했다.
- **문제**: 역할별 JSON의 일부 카드가 외부 `getty_aat` 메타데이터와 `source_type=getty_aat`를 보유하고, 제품 문서도 외부 조회·출처 표시를 현재 계약처럼 설명한다.
- **측정 지표**: 역할별 JSON과 사용 중인 데이터 index에서 `getty_aat` 키 및 `source_type=getty_aat`가 0건이며, 총 74개 고유 카드와 활성 20개가 유지된다.

## Goal

- **해결 목표**: 현재 TERM_CARD JSON을 자체 관리 정적 저장소의 단일 원본으로 명확히 하고, 모든 카드의 출처 유형을 `team_card`로 통일한다.
- **성공 기준**: 5개 역할 파일·index·PRD·SDD·사용자 안내가 외부 어휘 조회나 URI 표시를 요구하지 않으며, 후보·활성 카드의 선택 조건은 바뀌지 않는다.
- **Out of Scope**: PostgreSQL 테이블·ORM·마이그레이션·관리 UI·카드 편집 API 구현, 외부 어휘 데이터의 대체 수집, 후보 카드 승격, Pinterest 검색 구현, 기존 term ID·검색 조각·confidence gate 변경.

## What

**Happy Path**

1. 런타임은 `term-cards/index.json`과 index에 나열된 5개 역할 JSON만 읽는다.
2. 각 카드의 `source_type`은 `team_card`이고, 용어·설명·검색 조각·선택 조건은 팀이 검수하는 카드 데이터에서만 가져온다.
3. 활성 조건 `runtime_eligible=true && mvp_status=active_in_current_contract`를 통과한 20개 카드만 LLM 허용 목록·Pinterest 검색 계획에 사용한다.
4. 운영 문서는 외부 어휘 조회·URI·provider 폴백이 아닌 정적 카드 저장소 검증과 사람 검수를 설명한다.

**Edge Cases**

| # | 상황 | 처리 방식 |
|---|---|---|
| EC-01 | 역할 JSON에 `getty_aat` 키 또는 외부 출처 유형이 남음 | 데이터 검증 오류로 처리하고 배포 후보에서 제외한다. |
| EC-02 | index가 가리키는 역할 파일이 없거나 카드 수가 다름 | `STATIC_CARD_STORE_UNAVAILABLE` 또는 검증 오류로 처리하며 부분 로드하지 않는다. |
| EC-03 | 후보 카드가 아직 사람 검수를 받지 않음 | `runtime_eligible=false`를 유지하고 활성 허용 목록에 넣지 않는다. |
| EC-04 | 정적 JSON만 존재하고 PostgreSQL 저장소가 비어 있음 | 현재는 정적 저장소로 운영하고, 실제 DB 도입은 별도 Spec·마이그레이션·repository 구현으로 진행한다. |
| EC-05 | 팀 카드에 없는 용어를 사용자가 요청함 | 새 term ID·검색어를 자동 생성하지 않고 추가 질문 또는 `pending_human_review`를 반환한다. |

## How

- **현재 저장소 경계**: `docs/domains/illustration-reference/term-cards/index.json`과 index의 `categories`에 선언된 5개 JSON이 유일한 TERM_CARD 저장소다. 디렉터리 자동 탐색이나 외부 provider 조회는 하지 않는다.
- **카드 형식**: 모든 카드의 `source_type`은 `team_card`다. `getty_aat` 객체와 외부 URI·label·attribution 필드는 저장하지 않는다. 기존 `term_id`, 역할, 검색 조각, 관찰 기준, `confidence_gate`, `requires_all_of`, `requires_any_of`, 검수 상태는 보존한다.
- **데이터 거버넌스**: 후보 카드는 `review_status=needs_osechang_review` 또는 기존 검수 상태를 보존하되, 사람 검수·API 계약·Skill·평가셋 갱신 전에는 승격하지 않는다. index의 `dataset_version`으로 데이터 계약 변경을 기록한다.
- **현재 부족분**: 실제 PostgreSQL 테이블·마이그레이션·JSON repository·스키마 버전 검증·관리자 변경 이력은 구현되지 않았다. 이번 전환은 해당 구현의 선행 조건인 데이터·문서 계약 정리만 수행한다.
- **실패 계약**: 외부 어휘 서비스 실패 코드는 제거한다. 카드 저장소를 읽지 못하면 `STATIC_CARD_STORE_UNAVAILABLE`, 카드 자체가 없으면 `TEAM_TERM_CARD_UNAVAILABLE`만 사용한다.

## AC (Given-When-Then)

**AC-01 · 자체 관리 카드만 사용**

- GIVEN: index와 5개 역할 JSON이 있다.
- WHEN: 카드 저장소를 조립한다.
- THEN: 모든 카드의 `source_type`은 `team_card`이고 `getty_aat` 키는 0개다.

**AC-02 · 데이터 불변성**

- GIVEN: 전환 전 역할별 카드 집합이 있다.
- WHEN: 외부 출처 필드를 제거한다.
- THEN: 총 카드 수는 74개, 고유 `term_id`는 74개, 현재 활성 카드는 20개로 유지된다.

**AC-03 · 외부 조회 미사용**

- GIVEN: 유효한 활성 term ID가 있다.
- WHEN: 용어·검색 계획을 조립한다.
- THEN: 정적 팀 카드만 참조하며 외부 어휘 API·URI·provider 폴백을 호출하거나 반환하지 않는다.

**AC-04 · 미구현 DB 경계 공개**

- GIVEN: PostgreSQL 컨테이너가 존재하지만 TERM_CARD 테이블과 repository가 없다.
- WHEN: 팀원이 자체 DB 전환 범위를 확인한다.
- THEN: 현재는 JSON 정적 저장소라는 사실과 실제 DB 도입에 필요한 별도 작업이 Spec에 명시된다.
