# 관측과 프롬프트 버전 규칙

## Why

비동기 job의 자동 재시도·부분 결과·최종 실패를 안전하게 운영하려면 요청 단위로 상태와 시도 횟수를 추적해야 한다.

## Goal

- LLM 해석 프롬프트와 job 처리 경로를 안전한 trace 필드로 추적한다.
- 자동 재시도와 최종 failure code를 운영자가 구분할 수 있게 한다.
- Prompt 버전·모델·비용·지연과 30건 평가셋 품질을 같은 기준으로 비교한다.

## What

기본 해석 프롬프트 이름은 `uhkegryo-interpreter-v{n}`이고 production label을 사용한다. 모델 또는 프롬프트 변경 시 버전을 증가시킨다. `prompts/uhkegryo-interpreter-v0.md`는 v0의 저장소 검토 원본이며, 원격 Langfuse Prompt 등록 전후에 내용과 버전을 대조한다.

각 trace에는 `request_id`, `job_id`, session ID 해시, 모델 provider·name, `prompt_version`, `attempt`, `max_attempts`, 단계별 지연, 최종 `agent_status`, `failure_code`, 검색 결과 상태를 기록한다. 입력은 `request_text` 원문 대신 해시·글자 수로, LLM 출력은 원문 설명 대신 `interpretation_state`·선택된 역할·term ID·Pydantic 검증 결과로 기록한다. 호출별 input/output/total token 수와 비용을 기록하고, 평가 실행은 같은 모델·Prompt 버전별 p50/p95 지연과 요청당 비용을 집계한다.

## How

- 자동 실행 재시도는 같은 job의 `attempt=1..3`으로 기록한다. 사용자에게 재시도 진행을 표시하지 않는다.
- `LLM_*`, `SEARCH_*`, `JOB_INSTANCE_INTERRUPTED`은 각 시도의 안전한 오류 분류와 지연을 기록한다.
- 최종 `failed`에는 API와 같은 안정된 failure code를 기록한다. 운영 로그에는 안전한 오류 요약을 추가할 수 있으나 UI에 노출하지 않는다.
- 검색 재시도 소진 뒤 유효 카드가 있으면 `completed + partial_result`, `PIN_SEARCH_UNAVAILABLE`을 기록한다.
- `needs_clarification`은 실패가 아니며 새 사용자 메시지의 새 job과 연결한다.
- API 키, 세션 토큰, `anonymous_user_id` 원문, 요청 원문, 이미지 바이트, 썸네일 URL, Pin 메타데이터는 기록하지 않는다.
- Langfuse Prompt 원격 버전은 `uhkegryo-interpreter-v{n}` 이름과 version label로 관리한다. `production` label은 30건 baseline과 회귀 확인 전에는 바꾸지 않는다.

## AC

**AC-01 · 자동 재시도 관측**

- GIVEN: LLM timeout이 두 번 발생하고 세 번째 시도가 성공한다.
- WHEN: job을 종료한다.
- THEN: 같은 job ID의 attempt 1, 2, 3과 최종 성공 상태를 기록한다.

**AC-02 · 최종 실패 관측**

- GIVEN: 결정적 설정 오류가 발생한다.
- WHEN: job을 종료한다.
- THEN: failure code와 안전한 운영 요약을 기록하고 사용자 UI에는 내부 정보를 전달하지 않는다.

**AC-03 · Prompt 버전·비용·지연 연결**

- GIVEN: 동일한 30건 평가셋으로 baseline 또는 변경 후 실행을 한다.
- WHEN: 각 LLM 호출과 평가 실행을 기록한다.
- THEN: 모델 provider·name, `prompt_version`, token 수, 요청당 비용, 단계별 지연과 p50/p95를 같은 실행 기록에서 비교할 수 있다.
