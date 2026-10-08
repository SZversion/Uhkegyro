# 승인 역할 검색 완료 후 즉시 종료

## Why

- 페르소나·상황: 레퍼런스 검색 결과를 기다리는 사용자와 검색 지연을 분석하는 개발자.
- 문제: 모든 승인 역할을 처리한 뒤에도 추가 도구 선택 LLM 호출을 기다린다.
- 지표: 모든 역할 처리 완료 후 추가 LLM 호출 및 mcp-post-search-decision 관측 0건.

## Goal

- 현재 응답의 도구·병렬 검색·Widget 처리를 모두 마친 뒤, 남은 승인 역할이 없으면 검색 루프를 종료한다.
- 기존 검색 결과·재시도·오류·병렬 처리 계약을 유지한다.
- 범위 밖: API/DB/UI, 검색 엔진·MCP gateway, 대화 기억·레퍼런스 갱신, 배포. 검색 판단과 도구 선택 분리 계약은 [도구 선택 라운드 Spec](./search-tool-selection-rounds.md)을 따른다.

## What

1. 매 라운드 시작에 미완료 역할을 계산하고, 없으면 LLM 호출과 판단 관측을 생략한다.
2. 성공과 정상 빈 결과는 완료다. 장애는 판단 후 continue 및 재선택을 거쳐 최대 3회 시도하며 1초·2초 대기하고, 소진 뒤 완료다.
3. 최초 선택 응답 실행 뒤 미완료 역할이 있으면 post-search 판단을 한다. continue일 때 별도 도구 선택·인자 복구·재시도를 이어간다.
4. 같은 응답에 이미 선택된 검색 외 도구도 기존 순서로 모두 실행한다.
5. 설정 오류·취소와 승인 역할 검색 누락의 실패 분류를 보존한다.

## How

- worker의 pending 계산 직후 빈 목록이면 break한다. execute/flush 중간에는 종료 조건을 넣지 않는다.
- 검색 도구 선택 span은 최초 한 번 호출하고, 후속 호출은 continue 판단 뒤에만 생성한다. 각 mcp-tool-selection은 최초 purpose=tool_selection, 후속 purpose=tool_reselection이며 required=True, call_round/pending_roles/call_count/selected_roles를 유지한다. pending이 남은 라운드 경계에서만 mcp-post-search-decision span을 생성한다.
- 판단 호출은 명시적 continue/stop JSON을 검증한다. 필수 승인 역할이 남아 있는 stop은 기존 LLM_INVALID_STRUCTURED_OUTPUT으로 처리한다. worker 도구 선택 프롬프트는 미완료 역할의 승인 검색에 초점을 둔다.
- 기존 outcomes 등록 조건, Semaphore(3), 전체 MCP 16회 한도, 작업 회수와 결과 조립을 유지한다.
- 최종 도구 결과도 messages에 원래 순서·tool_call_id로 보존하지만 완료 후 LLM에 재전송하지 않는다.
- 과거 trace는 삭제하지 않는다. 모든 역할이 완료된 신규 흐름에는 mcp-post-search-decision이 없고, 미완료 역할 경계에서만 판단 trace가 생긴다.
- API·공개 타입 변경과 migration은 없다. 실제 운영 성능 개선 폭은 별도 배포 검증 대상이다.

## AC

- AC-01: Given 단일 또는 여러 승인 역할, When 모두 처리 완료, Then 추가 LLM 호출과 mcp-post-search-decision 관측은 0건이며 결과는 유지된다.
- AC-02: Given 느린 병렬 검색·Widget과 같은 응답의 검색 외 도구, When 검색 종료, Then 모든 작업이 완료되고 기존 실행 순서·tool_call_id와 실행 자리 반환이 유지된다.
- AC-03: Given 빈 결과와 일시 장애, When 처리, Then 빈 결과는 재검색하지 않고 장애만 최대 3회 및 1초·2초 대기로 재시도하며 소진 후 추가 판단 없이 부분 결과를 조립한다.
- AC-04: Given 잘못된 인자 또는 검색 누락, When 미완료 역할 처리, Then 기존 복구와 LLM_INVALID_STRUCTURED_OUTPUT 분류를 유지한다.
- AC-05: Given 설정 오류·취소·동시 Job, When 실행 중단 또는 종료, Then 기존 오류 분류·작업 회수·공유 한도와 trace 연결을 유지한다.
