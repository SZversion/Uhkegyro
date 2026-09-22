# 일러스트 레퍼런스 Agent 기반 — 비동기 모델

> 이 문서는 기존 동기 `POST /api/agent` 초안을 최신 비동기 모델로 대체한 문서다. 공개 API의 최종 경로·필드·상태는 별도 API 명세서에서 확정하며, PRD·SDD를 우선한다.

## 모델

- 서버가 발급한 HttpOnly 쿠키로 세션 소유권을 검증한다.
- 사용자는 자연어 텍스트만 입력한다. `role`, `term_id`, 검색어, Pin URL은 클라이언트가 보내지 않는다.
- 메시지 제출은 즉시 완료 응답이 아니라 작업을 만들고 `job_status`를 조회하는 비동기 흐름이다.
- `job_status`는 작업 envelope에, `agent_status`는 결과 payload에 둔다. 추가 `needs_clarification` boolean은 사용하지 않는다.
- TERM_CARD의 활성 카드만 사용하며 백엔드가 역할·활성 여부·confidence/requires를 검증한다.
- 검색은 검증된 `query_fragments`로 역할별 수행하고 최대 8개 Pin URL을 반환한다. 이미지는 저장하지 않는다.

## 작업 실패와 재시도

`JOB_TIMEOUT`과 `INSTANCE_INTERRUPTED`는 기본 `retryable=true`로 시작한다. `PROCESSING_ERROR`는 기본적으로 재시도하지 않는다. 재시도 가능한 작업은 `attempt`를 기록하고 `max_attempts=3`에서 종료한다. 실패 envelope는 `result=null`, `failure_code`, `user_message`, `retryable`을 포함한다.
