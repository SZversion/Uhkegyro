# OpenRouter LLM Adapter

## Why

Agent는 provider별 코드 변경 없이 model을 교체하면서도, 허용된 term 후보만 구조화 출력으로 받아야 한다.

## Goal

- OpenRouter를 단일 LLM provider로 사용한다.
- 배포 환경의 `LLM_MODEL`만 바꿔 model을 교체한다.
- 180초 안에 계약된 구조화 출력만 worker에 반환한다.

## What

adapter 입력은 사용자 원문과 활성 TERM_CARD 후보 경계다. 출력은 `InterpretationOutput={interpretation_state, selections, unresolved_constraints, clarifying_question}`이며 각 selection은 `{role, term_id, evidence, confidence}`다. adapter는 검색 URL·Pin·최종 Agent 상태를 만들지 않는다.

## How

- `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`, `LLM_MODEL`은 환경 변수로 읽고 코드에는 model명을 하드코딩하지 않는다.
- 호출 timeout은 180초다. timeout, 429, 일시 5xx, 계약 불일치 JSON은 회복 가능한 job attempt 실패다.
- API 키는 trace·로그에 기록하지 않는다. 사용자 원문은 Langfuse trace에만 기록하며 LLM 원본 응답은 저장하지 않는다.
- resolver가 adapter 출력을 JSON 카탈로그와 대조해 활성 term·역할·조건을 검증한다.

## AC

- GIVEN: `LLM_MODEL` 값 변경, WHEN: adapter를 재시작, THEN: 코드 변경 없이 새 model로 요청한다.
- GIVEN: 180초 timeout, WHEN: worker가 처리, THEN: 해당 attempt는 `LLM_TIMEOUT`으로 회복 처리한다.
- GIVEN: 계약 밖 term ID가 포함된 구조화 출력, WHEN: resolver가 검증, THEN: 후보를 사용하지 않고 `LLM_INVALID_STRUCTURED_OUTPUT`으로 처리한다.
- GIVEN: 정상 구조화 출력, WHEN: resolver가 처리, THEN: adapter는 최종 상태나 검색 URL을 결정하지 않는다.
