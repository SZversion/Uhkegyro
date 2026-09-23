# PostgreSQL Job Worker

## Why

별도 큐 없이도 비동기 Agent job을 안전하게 실행하고, worker 중단이나 일시적 외부 장애 뒤에 중복 처리 없이 회복해야 한다.

## Goal

- PostgreSQL `jobs`를 polling queue로 사용한다.
- 전체 동시 실행은 기본 5개이며 같은 세션에서는 하나만 실행한다.
- worker 중단 job은 최대 3회 안에서 재실행한다.

## What

worker는 1초마다 처리 가능한 queued job 또는 lease가 만료된 running job을 찾는다. claim 성공 시 status를 `running`으로 바꾸고 30초 lease를 설정한다. 실행 중 10초마다 heartbeat로 lease를 30초 뒤로 연장한다.

같은 session의 queued job은 더 이른 미종결 job이 있으면 claim하지 않는다. lease 만료 job은 중간 실행을 이어가지 않고 처음부터 재실행하며 `attempt`를 1 증가한다. `attempt=3` 뒤 회복 가능한 실패는 `failed`와 `JOB_INSTANCE_INTERRUPTED` 또는 실제 최종 failure code로 종결한다.

## How

- claim은 `FOR UPDATE SKIP LOCKED` transaction으로 수행해 worker 둘이 같은 job을 얻지 못하게 한다.
- `WORKER_CONCURRENCY` 기본값은 5이며 worker가 동시에 보유한 lease 수를 제한한다.
- worker는 상태를 `queued → running → validating → searching → rendering → completed|failed`로만 전이한다.
- LLM·crawler·widget의 회복 가능한 오류는 현재 attempt 안에서 자동 재시도하지 않고 job attempt 하나를 소진한다. 구성·DB migration·코드 오류는 즉시 `failed`다.
- 완료·실패 저장에 성공한 뒤 lease를 제거한다.

## AC

- GIVEN: queued job 두 개가 같은 세션에 있다, WHEN: worker가 claim, THEN: 먼저 생성된 job만 running이 된다.
- GIVEN: 서로 다른 세션의 queued job 여섯 개, WHEN: 기본 worker가 polling, THEN: 동시에 running인 job은 최대 다섯 개다.
- GIVEN: running job의 heartbeat가 10초마다 성공, WHEN: 30초가 경과, THEN: lease는 만료되지 않는다.
- GIVEN: worker가 heartbeat 없이 중단, WHEN: 30초 lease가 만료, THEN: 다른 worker는 attempt를 1 증가해 job을 처음부터 재실행한다.
- GIVEN: 세 번째 attempt가 회복 가능한 오류로 끝남, WHEN: worker가 종결, THEN: job은 failed이며 더 이상 claim되지 않는다.
