# MCP 도구 선택 호출 라운드 분리

## Why

- **페르소나**: 승인된 카드의 레퍼런스 검색을 기다리는 사용자.
- **상황**: Worker는 resolver가 검색 역할과 정확한 query_fragments를 이미 승인했어도 매 검색 라운드마다 도구 목록 중 다음 호출을 LLM이 고르게 한다.
- **문제**: 검색 결과가 나온 뒤에도 도구 선택을 위해 불필요한 LLM 대기와 비용이 발생하고, trace에서 계속 판단과 실행 선택이 한 호출로 섞인다.
- **측정 지표**: 첫 도구 선택은 작업당 1회. 승인 역할이 모두 완료된 뒤 추가 LLM 호출 0회. 후속 도구 선택은 명시적 continue 판단 뒤에만 수행한다.

## Goal

- 최초 `mcp-tool-selection` 호출에서 고른 모든 MCP 호출을 실행하고, 후속 판단이 필요할 때만 `mcp-post-search-decision`으로 continue/stop을 판정한다.
- continue인 경우 별도 `mcp-tool-selection` 호출로 다음 도구를 고른다.
- 역할별 Pinterest 장애 재시도 최대 3회 및 1초·2초 대기, 검색 병렬 한도 3개, 결과·오류 계약을 유지한다.
- **범위 밖**: 공개 API/응답 스키마, DB, UI, MCP gateway의 연결·인증 방식, 공용 interpreter 출력, 검색 외 도구의 실행 순서, 배포.

## What

**정상 흐름**
1. 최초 선택 LLM 호출이 등록 MCP 도구 호출을 선택한다.
2. Worker는 선택된 호출을 원래 순서 규칙대로 실행한다. 연속된 독립 검색은 병렬로 실행하며 각 Widget 처리까지 마친다.
3. 모든 승인 역할이 완료되면 판단·선택 추가 호출 없이 종료한다.
4. 승인 역할이 남으면 도구 결과를 포함한 대화로 판단 전용 LLM 호출을 한다.
5. 판단이 continue면 별도 도구 선택 LLM 호출을 거쳐 남은 역할·필요한 도구를 실행한다. 반복 시에도 동일한 판단-선택 순서를 따른다.

| 상황 | 처리 |
|---|---|
| 정상 검색 성공 또는 정상 빈 결과 | 역할 완료. Pin/Widget 결과 보존. 빈 결과는 재시도하지 않음 |
| Pinterest 일시 장애 | 역할 미완료 상태로 판단 후 재선택. 최대 3회, 첫 두 장애 뒤 1초·2초 대기 |
| 장애 세 번 소진 | `PIN_SEARCH_UNAVAILABLE`로 역할 완료, 기존 부분 결과 조립 |
| 승인 역할 검색 누락 또는 판단 stop 중 필수 역할 미완료 | 기존 `LLM_INVALID_STRUCTURED_OUTPUT` 처리 |
| 잘못된 인자·중복 역할 | 기존 검증·오류 반환·복구 규칙 유지 |
| 검색 외 도구 포함 | 같은 응답에 선택된 모든 도구를 기존 순서대로 실행 |
| 설정 오류·취소 | 기존 오류 분류, task 정리 및 검색 실행 자리 반환 |

## How

- 구현은 `backend/services/agent_worker.py`, `backend/services/llm.py`, 해당 Spec과 관련 테스트에 한정한다. API, DB, UI, 공개 해석 출력 타입은 변경하지 않는다.
- adapter는 기존 MCP tool-call API와 별도로 `request_mcp_search_decision(messages)`를 제공한다. 출력 계약은 JSON 객체 `{"decision":"continue"}` 또는 `{"decision":"stop"}`만 허용하며 누락·추가 키·다른 값은 `LLM_INVALID_STRUCTURED_OUTPUT`로 분류한다.
- 판단 호출은 tool calling 없이 JSON mode로 실행하고 Langfuse generation 이름 `mcp-post-search-decision`을 기록한다. 도구 선택은 `mcp-tool-selection`을 기록하며 purpose와 round를 metadata로 구분한다.
- Worker는 각 라운드 시작 시 pending을 계산한다. 빈 목록이면 판단·선택을 포함한 추가 호출 전에 종료한다. 최초 라운드에서는 판단 없이 도구 선택한다. 최초 및 후속 선택에서 반환된 호출을 전부 기존 순서 규칙으로 실행한다.
- 선택 응답 실행 완료 뒤 pending이 남으면 판단한다. continue만 후속 도구 선택을 허용한다. stop인데 승인 역할이 남았거나 검색 재시도를 수행하지 못했다면 누락 결과를 정상 완료로 취급하지 않고 기존 structured-output 오류를 낸다.
- 승인된 역할 검색과 미완료 도구 실행은 도구 선택에서 누락되지 않아야 한다. 역할별 세 번째 일시 장애는 `PIN_SEARCH_UNAVAILABLE` 결과로 완료 처리한다.
- 기존 검색 span, Widget span, retry-wait, tool_call_id 순서, semaphore(3), 총 MCP tool-call 한도, outcome 조립을 유지한다.
- 이전 trace는 삭제하지 않는다. 완료 신규 trace에는 post-search 판단과 후속 선택이 없어야 한다.

## AC (Given-When-Then)

**AC-01 · 첫 선택 뒤 모든 역할 완료**
- GIVEN: 최초 선택이 모든 승인 역할을 골랐고 검색·Widget 처리가 정상 완료된다.
- WHEN: Worker가 그 선택 응답의 모든 도구를 실행한다.
- THEN: 최초 `mcp-tool-selection`은 1회이며 post-search 판단과 후속 선택은 0회다.

**AC-02 · 일부 역할만 최초 선택**
- GIVEN: 최초 선택 이후 승인 역할이 남아 있다.
- WHEN: 검색·Widget 및 동일 응답의 기타 도구 처리가 끝난다.
- THEN: `mcp-post-search-decision`을 호출하고 continue인 경우에만 별도 `mcp-tool-selection`을 실행한다.

**AC-03 · 필수 검색 누락**
- GIVEN: 판단이 stop을 반환하거나 재선택 뒤에도 승인 역할 검색이 누락된다.
- WHEN: Worker가 결과를 검증한다.
- THEN: 누락을 성공으로 간주하지 않고 `LLM_INVALID_STRUCTURED_OUTPUT`로 실패한다.

**AC-04 · 재시도 보존**
- GIVEN: 검색 역할에 일시 장애가 발생한다.
- WHEN: 판단이 continue하고 재선택이 반복된다.
- THEN: 장애 역할만 최대 세 번 호출하고 첫 두 장애 뒤 1초·2초 기다리며, 소진 시 `PIN_SEARCH_UNAVAILABLE`과 기존 부분 결과를 보존한다.

**AC-05 · 동시 검색 및 순서**
- GIVEN: 한 도구 응답에 여러 독립 검색과 검색 외 도구가 있다.
- WHEN: Worker가 응답을 실행한다.
- THEN: 연속된 검색은 최대 3개 병렬 실행, Widget 처리가 끝날 때까지 기다리고, 검색 외 도구의 순서 경계 및 모든 tool_call_id를 보존한다.

**AC-06 · adapter 출력 검증**
- GIVEN: 판단 LLM이 continue/stop 외 값, 잘못된 JSON 또는 계약 외 필드를 반환한다.
- WHEN: adapter가 출력을 검증한다.
- THEN: `LLM_INVALID_STRUCTURED_OUTPUT`으로 분류한다.

**AC-07 · 오류 및 trace**
- GIVEN: 설정 오류, 취소 또는 모든 승인 역할 완료가 발생한다.
- WHEN: Worker가 검색 흐름을 종료한다.
- THEN: 오류·작업 정리·실행 자리 계약을 보존하고, 완료 뒤에는 선택·판단 trace span을 새로 만들지 않는다.

