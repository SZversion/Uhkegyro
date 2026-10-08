# 승인 역할 검색 완료 후 즉시 종료

## Why

- 페르소나·상황: 레퍼런스 검색 결과를 기다리는 사용자와 검색 지연을 분석하는 개발자.
- 문제: 검색 판단과 재선택 LLM 호출이 검색 실행·재시도를 지연시킨다.
- 지표: 검색 흐름에서 도구 선택 LLM 호출 1회, post-search decision LLM 호출 0회.

## Goal

- 현재 응답의 도구·병렬 검색·Widget 처리를 모두 마친 뒤, 남은 승인 역할이 없으면 검색 루프를 종료한다.
- 기존 검색 결과·재시도·오류·병렬 처리 계약을 유지한다.
- 범위 밖: API/DB/UI, 검색 엔진·MCP gateway, 대화 기억·레퍼런스 갱신, 배포. 검색 판단과 도구 선택 분리 계약은 [도구 선택 라운드 Spec](./search-tool-selection-rounds.md)을 따른다.

## What

1. 도구 선택은 한 번만 하고, 선택 응답의 모든 호출을 실행한다.
2. resolver 승인 검색이 선택에서 빠지면 worker가 코드로 호출한다.
3. 성공과 정상 빈 결과는 완료다. 장애는 코드가 해당 역할을 최대 3회 시도하며 1초·2초 대기하고, 소진 뒤 완료한다.
4. tool selection에는 Pinterest 검색 도구만 제공하며, 검색 외 도구는 실행하지 않는다.
5. 설정 오류·취소와 승인 역할 검색 누락의 실패 분류를 보존한다.

## How

- worker는 최초 `mcp-tool-selection` 응답을 전부 실행한 뒤 아직 검색되지 않은 승인 역할을 직접 호출한다.
- `PIN_SEARCH_UNAVAILABLE`인 역할만 코드 재시도하며 총 3회, backoff 1,000ms·2,000ms다. `PIN_RESULTS_EMPTY`는 완료로 보고 재시도하지 않는다.
- 검색 재시도에는 LLM 판단·도구 재선택이 없고, worker의 `mcp-code-search-attempt` trace가 시도 역할과 횟수를 기록한다.
- 기존 outcomes 등록 조건, Semaphore(3), LLM 선택 응답의 MCP 도구 한도, 작업 회수와 결과 조립을 유지한다. 코드 검색 시도는 역할별 최대 3회로 제한한다. MCP 목록에 다른 도구가 있어도 LLM에 노출하거나 실행하지 않는다.
- 과거 trace는 삭제하지 않는다. 신규 검색 흐름에는 mcp-post-search-decision generation이 없다.
- API·공개 타입 변경과 migration은 없다. 실제 운영 성능 개선 폭은 별도 배포 검증 대상이다.

## AC

- AC-01: Given 단일 또는 여러 승인 역할, When 검색을 실행, Then tool selection은 한 번이며 decision 호출은 없고 결과는 유지된다.
- AC-02: Given MCP에 Pinterest 검색 외 도구가 등록됨, When tool selection을 수행한다, Then 검색 도구만 노출·실행하고 나머지는 호출하지 않는다.
- AC-03: Given 빈 결과와 일시 장애, When 처리, Then 빈 결과는 재검색하지 않고 장애만 코드로 최대 3회 및 1초·2초 대기로 재시도하며 소진 후 부분 결과를 조립한다.
- AC-04: Given 잘못된 인자 또는 선택 누락, When 미완료 역할 처리, Then 선택된 호출을 실행하고 빠진 승인 검색은 worker가 실행한다.
- AC-05: Given 설정 오류·취소·동시 Job, When 실행 중단 또는 종료, Then 기존 오류 분류·작업 회수·공유 한도와 trace 연결을 유지한다.
