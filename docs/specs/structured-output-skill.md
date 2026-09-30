# Structured output Skill

## Why

- 페르소나: 자연어 설명으로 역할별 레퍼런스를 찾는 사용자.
- 문제: 출력 예제가 해석 프롬프트와 섞여 관리되고, JSON mode만으로는 필드 타입을 보장하기 어렵다.
- 지표: 호출에 Skill·코드 유래 schema 누락 0건.

## Goal

- 해석 규칙과 출력 규칙을 분리하고 같은 호출에 함께 전달한다.
- `InterpretationOutput`을 schema의 단일 원천으로 유지한다.
- Out of Scope: API 필드 변경, 모델 출력 자동 보정, 별도 JSON 생성 LLM, 원격 production Prompt 변경.

## What

- v2 프롬프트는 의미 해석·카드 선택을 담당한다. 중복 역할은 구체적인 후보 하나로 선택하고 입력에 없는 역할을 추측하지 않는다.
- `skills/structured-output/SKILL.md`는 출력 형태·상태별 규칙·검증 오류의 수정 방식을 설명한다.
- Skill이 없거나 읽기 불가면 설정 오류로 호출 전에 실패한다.
- provider가 schema를 지원하지 않으면 기존 upstream 오류 정책을 적용하며 JSON mode로 자동 폴백하지 않는다.

## How

- `STRUCTURED_OUTPUT_SKILL_PATH` 기본값은 `skills/structured-output/SKILL.md`이다. Docker image에 파일을 포함한다.
- adapter는 설정된 프롬프트의 System message와 Skill의 `Runtime instructions`를 합쳐 단일 system message로 전달한다. User message에는 기존 요청과 활성 카드만 둔다.
- `InterpretationOutput.model_json_schema()`로 `response_format={type:json_schema,json_schema:{name:interpretation_output,strict:true,schema:...}}`를 만든다.
- strict object의 `required`에는 모든 properties를 넣고 `default`는 제거한다. nullable 필드는 null을 유지하며 Pydantic 필드나 모델을 바꾸지 않는다.
- OpenRouter 요청은 `provider.require_parameters=true`로 schema 지원 endpoint에 한정한다. 호출은 attempt당 1회, SDK 재시도는 0회다.
- 위 schema는 해석 호출에 적용한다. main의 대화 기억 classify·summarize·answer 호출은 각 기존 출력 계약을 유지하며 해석 schema를 적용하지 않는다. 서버가 제공하는 `session_context`와 `InterpretationOutput`의 대화 맥락 필드는 유지한다.
- v2 활성화는 Prompt 경로와 `INTERPRETER_PROMPT_VERSION`을 함께 v2로 지정한다. 서버의 Pydantic·resolver 검증은 유지한다.
- 실제 호출의 형식·카드·상태 평가와 잔여 오류는 [평가 결과](../../evals/structured-output-skill-result.md)에 기록한다. Skill 분리만으로 의미 해석 정확도를 보장하지 않으며 현재 v2는 production 활성화 전 검토 대상이다.

## AC

- GIVEN v2·Skill, WHEN adapter가 호출하면, THEN 하나의 system message에 두 규칙이 포함되고 JSON Schema는 코드의 필드·enum·범위를 반영한다.
- GIVEN Skill 파일 부재, WHEN 초기화하면, THEN `CONFIGURATION_ERROR`로 실패하며 LLM을 호출하지 않는다.
- GIVEN provider schema 응답, WHEN 검증하면, THEN 역할 중복·순서·상태 불변 조건을 계속 검증한다.
- GIVEN 실제 평가 입력, WHEN 실행하면, THEN 모델 출력 원문을 저장하지 않고 형식·카드·상태의 평가 결과를 분리한다.
