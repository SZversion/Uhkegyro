# 익명 세션과 Job 영속화

## Why

익명 사용자는 쿠키로 자신의 job 이력만 조회해야 하며, Pin 결과를 별도 자산으로 축적하지 않는다. 비동기 job의 상태와 최종 결과를 Neon PostgreSQL에 보관해 worker 재시작 뒤에도 polling을 보장한다.

## Goal

- Neon PostgreSQL과 `asyncpg`로 `sessions`·`jobs`만 관리한다.
- 세션 쿠키는 활동마다 90일 연장하고, DB session 행은 마지막 활동 뒤 3개월에 자동 삭제한다.
- job 결과에는 사용자 원문과 `pin_id`·`pin_url`·`status`를 보관하되 `thumbnail_url`은 보관하지 않는다.

## What

`sessions`는 `session_id` UUID PK, 고유 `session_token_hash`, `created_at`, `last_activity_at`을 가진다. `jobs`는 `job_id` UUID PK, `session_id` FK `ON DELETE CASCADE`, `request_text`, `request_text_hash`, `idempotency_key_hash`, `idempotency_expires_at`, `status`, `attempt=0`, `max_attempts=3`, `lease_expires_at`, `next_retry_at nullable timestamptz`, `succeeded`, `final_payload_json`, `created_at`, `updated_at`, `completed_at`을 가진다. 신규 job의 `next_retry_at`은 `null`이다.

수락한 `request_text`는 연결 session이 삭제될 때까지 job에 보관한다. `succeeded`와 `final_payload_json`은 진행 중에는 모두 `null`, 성공이면 각각 `true`와 `thumbnail_url`을 제거한 `AgentResult`, 실패면 `false`와 `failure` 객체다. 성공 payload는 `pin_id`·`pin_url`·`status`를 유지한다.

`Idempotency-Key`는 UUID 헤더다. 같은 세션·같은 키·10분 이내·같은 `request_text_hash`면 기존 job을 반환한다. 같은 키와 다른 원문은 `409 IDEMPOTENCY_KEY_CONFLICT`다. 10분이 지나면 같은 키는 새 job을 만들 수 있다.

## How

- 배포 환경의 `DATABASE_URL`은 Secret Manager에서 주입한 Neon `postgresql+asyncpg://...?...sslmode=require` 연결 문자열이다. 로컬 개발은 같은 형식의 `.env` 값만 사용한다.
- 원문 쿠키 토큰은 DB에 저장하지 않고 SHA-256 해시로 `sessions.session_token_hash`를 조회한다.
- 유효 세션의 API 활동마다 `last_activity_at`과 쿠키 `Max-Age=90일`을 갱신한다.
- 1일마다 `last_activity_at`이 3개월보다 오래된 session 행을 삭제한다. FK cascade로 연결 job과 그 `request_text`도 함께 삭제한다. users, messages, search_results, Pin 전용 테이블은 만들지 않는다.
- idempotency 판정과 job 생성은 같은 PostgreSQL transaction에서 session별 advisory lock으로 직렬화한다.
- migration은 `jobs.next_retry_at timestamptz NULL DEFAULT NULL`을 추가하고 기존 행은 `null`로 둔다. worker claim은 queued job에 한해 `next_retry_at IS NULL OR next_retry_at <= now()`를 만족할 때만 허용한다.
- `GET /api/jobs/{job_id}`는 소유 세션만 읽을 수 있고, 소유하지 않은 경우 `JOB_NOT_FOUND`를 반환한다.

## AC

- GIVEN: 쿠키가 없는 요청, WHEN: 유효한 Agent 요청을 수락, THEN: 세션과 queued job을 만들고 90일 쿠키를 발급한다.
- GIVEN: 같은 세션·키·원문이 10분 안에 재전송, WHEN: 요청 수락, THEN: 새 job 없이 기존 job을 반환한다.
- GIVEN: 같은 세션·키와 다른 원문, WHEN: 요청 수락, THEN: `409 IDEMPOTENCY_KEY_CONFLICT`를 반환한다.
- GIVEN: 성공 job, WHEN: 저장, THEN: `thumbnail_url` 없이 Pin ID·URL·상태가 포함된 payload와 `succeeded=true`를 저장한다.
- GIVEN: session 행 삭제, WHEN: transaction이 완료, THEN: 연결된 job 행도 없다.
- GIVEN: 마지막 활동 후 3개월이 지난 session, WHEN: 보관 정리 작업이 실행, THEN: session·연결 job·`request_text`가 함께 삭제된다.
- GIVEN: 신규 job, WHEN: 저장한다, THEN: `next_retry_at=null`이며 즉시 claim할 수 있다.
- GIVEN: retry를 예약한 queued job, WHEN: `next_retry_at` 전 worker가 claim한다, THEN: claim하지 않는다.
