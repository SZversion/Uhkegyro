# Worker Pinterest 검색 단계 연결 (작업 13)

## Why

- **페르소나**: 그림 레퍼런스를 찾는 사용자.
- **상황**: Worker가 LLM 후보를 resolver로 검증하고도 현재 Pinterest 검색 결과 없이 Job을 완료한다.
- **문제**: 결과에 실제 Pin과 검색 장애 사유가 없어 UI가 참고 자료를 보여 주지 못한다.
- **측정 지표**: 검증된 검색 가능 카드가 결과로 선택되면 각 역할 검색 결과와 reason code가 완료 Job에 반영된다.

## Goal

- resolver 검증을 통과한 TERM_CARD의 `query_fragments`로 Worker가 Pinterest provider를 호출한다.
- provider 결과를 `RoleSearchOutcome`으로 모아 response assembler에 전달한다.
- 검색 장애 결과는 역할별 최대 3회 조회하며, 최종 장애는 `PIN_SEARCH_UNAVAILABLE`, 정상 빈 결과는 `PIN_RESULTS_EMPTY`로 구분한다.
- **범위 밖**: Pinterest 공개 검색·Widget 구현 변경, LLM 재시도 정책 변경, 실패 코드 공개 문구 변경(작업 15), UI 구현.

## What

1. Worker가 `searching` 상태로 전환한 뒤 resolver가 선택한 유효 TERM_CARD마다 해당 역할과 카드의 `query_fragments`만 provider에 전달한다.
2. 성공한 검색의 Pin과 정상 빈 검색 결과를 각각 provider 결과 그대로 보존한다. `PIN_RESULTS_EMPTY`는 재조회하지 않는다.
3. `PIN_SEARCH_UNAVAILABLE`이면 같은 역할 검색을 총 3회까지 시도하고 첫 번째·두 번째 장애 뒤 각각 1초·2초 기다린다. 이후에도 실패하면 해당 역할의 마지막 unavailable 결과를 유지하고 다른 역할 검색을 계속한다.
4. 역할별 결과를 response assembler에 전달한다. 다른 역할에 결과가 있으면 결과는 `partial_result`가 되며 unavailable 역할의 Pin 목록은 비어 있다. 모든 역할의 정상 빈 검색은 `PIN_RESULTS_EMPTY`를 집계한다.
5. clarification 또는 유효한 검색 카드가 없는 결과는 Pinterest provider를 호출하지 않는다. 직접 검색 금지 카드도 resolver가 유효 검색 대상으로 전달하지 않는다.
6. provider의 예기치 않은 예외는 내부 코드 오류 경계에 맡기며 `PIN_SEARCH_UNAVAILABLE`로 숨기지 않는다.

## How

- Worker 생성자에 `PinterestProvider` 선택적 의존성을 주입한다. 실제 `run_worker`는 [SearXNG 검색 provider](./searxng-pinterest-search.md)를 `PinterestWidgetProvider`로 감싼다.
- 역할 검색 순서는 resolver가 반환한 카드 순서를 따른다. provider 입력은 `ValidatedTerm.selection.role` 및 `tuple(ValidatedTerm.card["query_fragments"])`다. LLM 원문이나 추가 free-text는 입력하지 않는다.
- 역할당 최대 검색 호출은 3회다. retryable outcome은 `code == ReasonCode.PIN_SEARCH_UNAVAILABLE`일 때뿐이며 backoff는 호출 후 1,000ms, 2,000ms다. `PIN_RESULTS_EMPTY` 및 Pin별 Widget 접근 불가(`deleted`)는 재시도하지 않는다.
- `run_once(search_outcomes=...)`에 결과가 직접 주어진 경우 기존 테스트 seam과 호출 계약을 유지하고 provider를 다시 호출하지 않는다.
- 검색 outcome의 조립과 공개 reason code는 기존 `assemble` 및 `RoleSearchOutcome` 계약을 재사용한다. 썸네일 비저장 규칙은 작업 12를 따른다.

## AC

**AC-01 · 유효 카드 검색 호출**

- GIVEN: resolver가 검색 가능한 카드 하나 이상을 승인한다.
- WHEN: Worker가 `searching` 단계에 진입한다.
- THEN: 각 승인 역할과 그 카드의 `query_fragments`만 provider에 전달하고 결과를 완료 payload에 반영한다.

**AC-02 · 빈 결과와 검색 장애 구분**

- GIVEN: provider가 한 역할에 `PIN_RESULTS_EMPTY`, 다른 역할에 `PIN_SEARCH_UNAVAILABLE`을 반환한다.
- WHEN: Worker가 역할 결과를 조립한다.
- THEN: 빈 결과는 재시도 없이 `PIN_RESULTS_EMPTY`로 남고, unavailable 결과는 최대 세 번 조회 후 `PIN_SEARCH_UNAVAILABLE`로 남는다.
- AND THEN: 두 reason code는 TermResult와 AgentResult에 계약대로 집계된다.

**AC-03 · 부분 검색 성공**

- GIVEN: 한 역할 검색은 성공하고 다른 역할 검색은 세 번 모두 unavailable이다.
- WHEN: Worker가 Job을 조립한다.
- THEN: 성공한 Pin을 유지하고 장애 역할에는 빈 pins와 `PIN_SEARCH_UNAVAILABLE`을 넣어 `partial_result`를 완료한다.

**AC-04 · 검색 불필요 상태**

- GIVEN: resolver가 clarification 결과 또는 검색 가능한 카드를 하나도 승인하지 않는다.
- WHEN: Worker가 Job을 처리한다.
- THEN: Pinterest provider는 호출되지 않는다.
