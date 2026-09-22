# 자체 관리 TERM_CARD 저장소 전환

## Why

- **페르소나**: 일러스트 레퍼런스 Agent의 용어 데이터와 검수 기준을 관리하는 팀원.
- **상황**: 프로젝트는 팀이 작성·검수한 용어를 자체 TERM_CARD DB에서만 사용하기로 결정했다. Getty는 용어 조사 시 참고한 자료일 뿐 서비스 데이터가 아니다.
- **문제**: 역할별 JSON을 런타임 원본으로 계속 쓰면 검수 이력·변경·세션 저장과 분리되고, 실제 사용하지 않는 외부 출처 메타데이터를 저장하면 서비스 데이터처럼 보이게 한다.
- **측정 지표**: 시드 JSON과 자체 DB의 Getty 관련 필드·레코드는 0건이며, 총 74개 고유 카드·활성 20개를 유지한다.

## Goal

- **해결 목표**: 자체 TERM_CARD DB를 런타임 용어 선택의 단일 원본으로 명확히 하고, 역할별 JSON은 검수·시드 입력으로만 사용한다.
- **성공 기준**: PRD·SDD·사용자 안내가 자체 DB만 런타임 출처로 설명하며, 후보·활성 카드의 선택 조건은 바뀌지 않는다. Getty 데이터·URI·귀속 정보는 서비스 데이터와 화면에 없다.
- **Out of Scope**: Getty API·SPARQL·웹 스크래핑·Getty 데이터 적재, 카드 자동 생성·승격, Pinterest 검색 구현, 기존 term ID·검색 조각·confidence gate 변경. 실제 PostgreSQL 테이블·마이그레이션·repository 구현은 별도 구현 작업이다.

## What

**Happy Path**

1. 배포·시드 적재 작업이 `term-cards/index.json`과 index에 나열된 5개 역할 JSON을 검증한다.
2. 검증된 카드의 용어·설명·검색 조각·선택 조건을 자체 TERM_CARD DB에 적재한다.
3. 활성 조건 `runtime_eligible=true && mvp_status=active_in_current_contract`를 통과한 20개 카드만 LLM 허용 목록·Pinterest 검색 계획에 사용한다.
4. 런타임 Card repository는 자체 TERM_CARD DB만 조회한다. Getty 데이터·외부 어휘 API·SPARQL·웹 호출은 하지 않는다.

**Edge Cases**

| # | 상황 | 처리 방식 |
|---|---|---|
| EC-01 | 시드 JSON 또는 자체 DB에 Getty 데이터·외부 출처 유형이 남음 | 데이터 검증 오류로 처리하고 배포 후보에서 제외한다. |
| EC-02 | index가 가리키는 역할 파일이 없거나 카드 수가 다름 | 시드 적재를 중단하고 `TERM_CARD_STORE_UNAVAILABLE` 또는 검증 오류로 처리한다. |
| EC-03 | 후보 카드가 아직 사람 검수를 받지 않음 | `runtime_eligible=false`를 유지하고 활성 허용 목록에 넣지 않는다. |
| EC-04 | 자체 TERM_CARD DB가 비어 있거나 연결할 수 없음 | 결과·링크를 만들지 않고 `service_unavailable`과 `TERM_CARD_STORE_UNAVAILABLE`로 처리한다. |
| EC-05 | 팀 카드에 없는 용어를 사용자가 요청함 | 새 term ID·검색어를 자동 생성하지 않고 추가 질문 또는 `pending_human_review`를 반환한다. |

## How

- **런타임 저장소 경계**: 자체 TERM_CARD DB가 유일한 런타임 저장소다. 역할별 JSON은 DB 적재 전 검수·시드 입력이며, 요청마다 읽거나 디렉터리를 자동 탐색하지 않는다.
- **과거 마스터 경계**: `TERM_CARDS_MASTER_100_DRAFT.json`은 과거 초안 경로를 위한 `deprecated_term_card_store_pointer`다. 이 파일은 index에 포함하지 않으며, 어떤 카드 로더도 직접 읽지 않는다.
- **카드 형식**: 시드 JSON과 자체 DB 카드의 `source_type`은 `team_card`다. Getty 객체·ID·URI·label·attribution 필드는 저장하지 않는다. `term_id`, 역할, 검색 조각, 관찰 기준, `confidence_gate`, `requires_all_of`, `requires_any_of`, 검수 상태를 보존한다.
- **데이터 거버넌스**: 후보 카드는 `review_status=needs_osechang_review` 또는 기존 검수 상태를 보존하되, 사람 검수·API 계약·Skill·평가셋 갱신 전에는 승격하지 않는다. index의 `dataset_version`으로 데이터 계약 변경을 기록한다.
- **현재 부족분**: 실제 PostgreSQL 테이블·마이그레이션·시드 적재·repository·스키마 버전 검증·관리자 변경 이력은 구현되지 않았다. 이번 변경은 구현 전 데이터·문서 계약 정리다.
- **실패 계약**: 카드 저장소를 읽지 못하면 `TERM_CARD_STORE_UNAVAILABLE`, 카드 자체가 없으면 `TEAM_TERM_CARD_UNAVAILABLE`을 사용한다. Getty 관련 실패 코드는 사용하지 않는다.

## AC (Given-When-Then)

**AC-01 · 자체 관리 카드만 사용**

- GIVEN: index와 5개 역할 JSON이 있다.
- WHEN: 시드 적재와 카드 저장소 검증을 수행한다.
- THEN: 모든 카드의 `source_type`은 `team_card`이고 Getty 관련 키·레코드는 0개다.

**AC-02 · 데이터 불변성**

- GIVEN: 전환 전 역할별 카드 집합이 있다.
- WHEN: 자체 DB 적재 전후 카드 집합을 비교한다.
- THEN: 총 카드 수는 74개, 고유 `term_id`는 74개, 현재 활성 카드는 20개로 유지된다.

**AC-03 · 외부 조회 미사용**

- GIVEN: 유효한 활성 term ID가 있다.
- WHEN: 용어·검색 계획을 조립한다.
- THEN: 자체 TERM_CARD DB만 참조하며, Getty 데이터·외부 어휘 API·SPARQL·provider 폴백을 호출하지 않는다.

**AC-04 · 자체 DB 경계 공개**

- GIVEN: PostgreSQL 컨테이너가 존재하지만 TERM_CARD 테이블과 repository가 없다.
- WHEN: 팀원이 자체 DB 전환 범위를 확인한다.
- THEN: 런타임 자체 DB·시드 적재·repository가 미구현이라는 사실과 별도 작업이 Spec에 명시된다.
