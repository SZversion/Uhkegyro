# 검색 도구 선택 및 코드 재시도

## Why

- **페르소나**: 승인된 카드의 레퍼런스 검색 결과를 기다리는 사용자.
- **상황**: resolver가 검색 역할과 정확한 `query_fragments`를 승인한 뒤에도 LLM이 후속 판단과 도구 재선택을 반복한다.
- **문제**: 검색이 실제 실행되기 전에 판단·선택 호출이 반복되며 지연과 비용이 늘고, 검색 재시도 여부를 LLM이 좌우한다.
- **측정 지표**: 검색 흐름에서 LLM 호출은 최초 도구 선택 1회. Pinterest 검색의 추가 시도는 코드가 수행한다.

## Goal

- 최초 도구 선택 응답의 모든 호출을 실행한다.
- resolver가 승인한 Pinterest 검색이 선택에서 누락되면 worker가 코드로 즉시 실행한다.
- 검색 장애 역할만 최대 3회 검색하고, 정상 빈 결과와 Pin별 Widget 실패는 재시도하지 않는다.
- **범위 밖**: 공개 API/응답 스키마, DB, UI, MCP gateway 연결·인증 방식, 배포.

## What

**정상 흐름**
1. LLM이 `search_pinterest_pins` 호출을 한 번 선택한다. MCP 등록 목록에 다른 도구가 있어도 selection에 제공하지 않는다.
2. worker가 선택된 승인 검색을 실행한다. 독립 검색은 최대 3개 병렬 실행하며 각 Widget 처리를 마친다.
3. 선택에서 누락된 승인 Pinterest 역할은 worker가 정확한 resolver 승인 조각으로 검색한다.
4. `PIN_SEARCH_UNAVAILABLE` 역할만 worker가 최대 3회까지 재시도한다. 첫 두 장애 뒤 1초·2초 기다린다.
5. 모든 역할이 완료되거나 재시도가 소진되면 기존 assembler가 결과를 조립한다.

| 상황 | 처리 |
|---|---|
| 검색 성공 또는 정상 빈 결과 | 역할 완료. 정상 빈 결과는 `PIN_RESULTS_EMPTY`; 재시도하지 않음 |
| Pinterest 일시 장애 | worker가 해당 역할만 코드로 재시도. 총 3회, 첫 두 장애 뒤 1초·2초 대기 |
| 장애 세 번 소진 | `PIN_SEARCH_UNAVAILABLE`로 역할 완료하고 부분 결과 조립 |
| 검색 도구 선택 누락 | 누락된 승인 역할을 worker가 직접 검색 |
| 잘못된 인자·중복 역할 | 기존 검증·오류 복구 규칙 유지 |
| 비허용 MCP 도구 선택 | MCP로 전달하지 않고 도구 선택 실패 처리 |
| 설정 오류·취소 | 기존 오류 분류, task 정리 및 검색 실행 자리 반환 |

## How

- 검색 tool selection은 `request_mcp_tool_calls` 한 번만 호출한다. post-search decision API, LLM 호출, Langfuse generation은 사용하지 않는다.
- MCP `tools/list`에서 `search_pinterest_pins`만 LLM에 제공한다. 선택 호출에 포함된 검색만 실행하며, 예상 밖 도구 호출은 MCP gateway에 전달하지 않는다. Pinterest 인자는 resolver의 승인 역할과 `query_fragments`가 정확히 일치해야 한다.
- 최초 선택 이후 미검색 역할 및 `PIN_SEARCH_UNAVAILABLE` 역할은 worker 코드가 직접 호출한다. 임의 텍스트·승인되지 않은 query fragment는 검색에 전달하지 않는다.
- 역할별 총 검색 호출은 최대 3회, 재시도 대기는 1,000ms와 2,000ms다. `PIN_RESULTS_EMPTY`와 Widget `deleted`는 재시도하지 않는다.
- 기존 검색 span, Widget span, retry-wait, semaphore(3), LLM 선택 호출의 MCP 도구 한도, outcome 조립을 유지한다. 코드 검색은 역할당 최대 3회로 제한하고 `mcp-code-search-attempt` span으로 기록한다.

## AC (Given-When-Then)

**AC-01 · 선택된 호출 실행**
- GIVEN: 최초 선택이 MCP 도구 호출을 반환한다.
- WHEN: worker가 선택 응답을 처리한다.
- THEN: 선택된 호출을 전부 기존 순서 규칙으로 실행하고 검색 흐름에서 추가 LLM 호출은 하지 않는다.

**AC-02 · 검색 누락**
- GIVEN: 최초 선택에서 승인된 Pinterest 역할 하나 이상이 빠졌다.
- WHEN: 선택된 호출 실행이 끝난다.
- THEN: worker가 빠진 역할을 승인된 query fragments로 직접 검색한다.

**AC-03 · 코드 재시도**
- GIVEN: Pinterest 검색이 `PIN_SEARCH_UNAVAILABLE`을 반환한다.
- WHEN: worker가 검색 결과를 처리한다.
- THEN: 해당 역할만 총 최대 3회 시도하고 첫 두 장애 뒤 1초·2초 기다리며, 재시도 판단 LLM을 호출하지 않는다.

**AC-04 · 정상 빈 결과**
- GIVEN: Pinterest 검색이 정상 응답으로 결과를 반환하지 않는다.
- WHEN: worker가 결과를 처리한다.
- THEN: 해당 역할은 `PIN_RESULTS_EMPTY`로 완료하고 재시도하지 않는다.

**AC-05 · 병렬 검색과 도구 allowlist**
- GIVEN: MCP 도구 목록에 Pinterest 검색과 다른 도구가 있고 모델이 검색 외 도구를 반환한다.
- WHEN: worker가 응답을 처리한다.
- THEN: LLM에는 Pinterest 검색만 제공하고, 검색 외 호출은 실행하지 않으며 누락된 승인 검색은 worker가 코드로 실행한다.
- AND THEN: 승인된 독립 검색은 최대 3개 병렬 실행하고 각 Widget 처리가 끝날 때까지 기다린다.

**AC-06 · 재시도 소진 및 오류**
- GIVEN: 검색 장애가 세 번 발생하거나 MCP 설정 오류·취소가 발생한다.
- WHEN: worker가 검색을 종료한다.
- THEN: 장애는 `PIN_SEARCH_UNAVAILABLE` 부분 결과로 조립하고 설정 오류·취소는 기존 분류를 보존한다.
