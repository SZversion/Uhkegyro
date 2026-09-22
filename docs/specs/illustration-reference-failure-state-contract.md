# Illustration Reference Failure State Contract — 비동기 모델

> 기존 동기 `POST /api/agent`와 6상태 단일 응답 모델을 폐기하고, 서버 발급 HttpOnly 쿠키·비동기 job 모델로 대체한다. 최종 공개 API는 별도 API 명세서에서 확정하며 PRD·SDD를 우선한다.

## 상태 계층

- 작업 envelope의 `job_status`: `queued`, `running`, `validating`, `searching`, `rendering`, `completed`, `failed`.
- 결과 payload의 `agent_status`: `success`, `needs_clarification`, `partial_result`, `out_of_scope`, `unsafe_input`, `service_unavailable`.
- 별도 `needs_clarification` boolean 필드는 사용하지 않는다. `agent_status=needs_clarification`이면 카드·링크 조립을 중단하고 질문을 반환한다.
- `job_status=failed`이면 `result=null`이며 `failure_code`, `user_message`, `retryable`을 반환한다.

## 실패·재시도

- `JOB_TIMEOUT`: `retryable=true`.
- `INSTANCE_INTERRUPTED`: `retryable=true`.
- `PROCESSING_ERROR`: `retryable=false`.
- 재시도 가능한 작업은 `attempt`를 증가시키며 `max_attempts=3` 후 `retryable=false`로 종결한다.
- 사용자의 재시도는 새 작업을 만들고 기존 작업과 원인·입력을 연결한다. 무제한 자동 재시도는 허용하지 않는다.

## 입력·세션 경계

클라이언트는 자연어 텍스트만 전달하고, 서버는 HttpOnly 쿠키와 세션 소유권을 검증한다. 클라이언트가 `role`, `term_id`, 검색어, Pin URL을 직접 지정하지 못한다. 역할은 `body`, `pose`, `view`, `perspective`, `layout`으로 제한한다.
