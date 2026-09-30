# Interpreter v1 출력 구조 전달

## Why

- 페르소나: 레퍼런스 UI에서 자연어 요청을 제출하는 사용자
- 상황: OpenRouter 호출은 성공하지만 `selections`가 배열이 아닌 출력이 생성된다.
- 문제: v0 파일의 JSON 계약과 예제는 adapter가 읽는 System message 밖에 있어 실제 모델 입력에는 포함되지 않는다.
- 지표: 실제 System message의 필수 출력 필드 누락 0건.

## Goal

- v1의 단일 System message에 selection 항목의 구조와 두 해석 상태의 JSON 형태를 전달한다.
- 실제 OpenRouter 호출을 Pydantic과 resolver로 검증한다.
- Out of Scope: 로컬 LLM 설치, provider rate limit 해제, 출력 자동 보정, API schema 변경, 무제한 재시도.

## What

- v0를 보존하고 `uhkegryo-interpreter-v1`을 새 버전으로 제공한다.
- `selections`와 `evidence`는 배열이고 selection은 `{role, term_id, evidence, confidence}`임을 명시한다.
- 선택 상태와 질문 상태를 각각 하나의 JSON 예제로 설명한다. 예제 ID는 실제 후보가 아니며 활성 카드의 ID로 대체해야 한다.
- 잘못된 출력은 기존 검증에서 거부한다. HTTP 429 및 timeout 정책은 기존 계약을 따른다.

## How

- 새 파일 `prompts/uhkegryo-interpreter-v1.md`의 `System message` 코드 펜스 안에 출력 구조와 예제를 둔다. loader는 기존 두 메시지 추출 방식을 유지한다.
- Docker image에 v0와 v1을 모두 포함한다.
- 최신 main의 `session_context`, `source_job_id`, `context_updates` 계약과 Memory classify·summarize·answer 지시문을 유지한다. v1의 출력 예제에도 nullable 출처와 조건 변경 배열을 포함한다.
- v1 활성화 시 `INTERPRETER_PROMPT_PATH=./prompts/uhkegryo-interpreter-v1.md`, `INTERPRETER_PROMPT_VERSION=uhkegryo-interpreter-v1`을 함께 지정한다.
- v1 단계에서는 기존 `response_format=json_object`, SDK 내부 재시도 0회, `InterpretationOutput` 및 resolver 검증을 유지한다. 코드 유래 strict schema로의 전환은 [구조화 출력 Skill Spec](./structured-output-skill.md)에 기록한다.
- 원본 모델 출력은 영구 저장하지 않는다. 로컬 검증에서는 오류 위치와 타입만 출력한다.

## AC

- GIVEN v1 파일, WHEN loader가 System message를 읽으면, THEN selection의 네 필드와 배열 타입 및 두 상태 예제가 실제 메시지에 포함된다.
- GIVEN System message 안의 선택·질문 예제, WHEN 예제 JSON을 검증하면, THEN 모두 `InterpretationOutput`을 통과한다.
- GIVEN `selections=null` 또는 객체, WHEN 기존 출력 검증을 수행하면, THEN `LLM_INVALID_STRUCTURED_OUTPUT`으로 거부한다.
- GIVEN Docker image, WHEN v1 경로를 설정하면, THEN 해당 파일을 읽고 v1을 trace 버전으로 사용한다.
