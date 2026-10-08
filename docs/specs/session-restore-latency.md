# 세션 복원 레이턴시 개선

## Why
브라우저 시작 시 쿠키 소유자의 세션 목록과 대화 이력을 복원하는 동안 여러 API 요청과 Pinterest 위젯 요청이 이어져 첫 화면이 늦게 준비된다. 특히 사용자가 당장 보지 않는 과거 Job의 썸네일까지 동기적으로 다시 조회한다.

## Goal
- 초기 복원은 세션 목록 조회 1회와 최신 세션의 최신 Job만으로 화면을 준비한다.
- 과거 대화는 사용자가 이전 기록을 요청하거나 다른 세션을 열 때 복원한다.
- 여러 Job의 소유권 확인과 DB 조회는 세션 이력 API의 한 묶음 쿼리로 처리한다.
- Pinterest 위젯 요청은 앱 프로세스에서 연결을 재사용한다.
- 쿠키 소유권 확인, 세션 만료, 결과·Pin 데이터 보존 경계는 유지한다.

## What
1. 초기 `GET /api/sessions/bootstrap?limit=100`은 쿠키를 확인해 생성 시각 내림차순 세션 목록, 최신 세션 ID, 그 세션의 최신 Job 하나, 과거 Job 존재 여부를 반환한다. 알 수 없는 쿠키는 기존 세션 API와 같이 401을 반환하며 세션이 없는 유효 소유자는 빈 목록을 받는다.
2. 초기 화면은 최신 Job 하나만 대화로 복원한다. 해당 세션에 더 오래된 Job이 있으면 `이전 대화 불러오기` 동작으로 이력을 요청한다. 세션 목록에서 다른 세션을 열면 그 세션의 대화를 불러온다.
3. `GET /api/sessions/{session_id}/jobs`는 소유권 검사와 Job 페이지 조회를 한 SQL 쿼리에서 수행한다. 각 페이지는 완료 Job들의 Pin ID를 한 요청 안에서 썸네일로 보강한다. 프론트는 페이지 단위로 API를 호출하며 Job마다 `/api/jobs/{job_id}`를 호출하지 않는다.
4. 최신 Job 단건 보강과 세션 이력 페이지 보강은 동일한 프로세스 수준 `httpx.AsyncClient` 연결 풀을 사용한다. 앱 종료 시 닫는다.
5. 실패·취소된 세션 복원은 현재 복원 오류 동작을 따른다. 과거 기록 로딩 실패 시 이미 표시된 최신 Job은 유지하고 다시 요청할 수 있게 한다.

## How
- `SessionRepository.bootstrap(token, limit)`은 소유자 조회, 세션 목록, 최신 세션 선택, 최신 Job 선택 및 과거 Job 존재 확인을 단일 PostgreSQL 문장으로 반환한다. 최신 세션은 생성 시각 내림차순 첫 항목이다. 활성 세션의 `last_activity_at` 갱신도 이 문장에서 수행한다.
- `JobRepository.history_for_owner(token, session_id, limit, offset)`은 `anonymous_owners`, `sessions`, `jobs`를 조인해 쿠키 소유자와 세션을 확인하고 Job 페이지를 한 번의 DB 왕복으로 가져온다. 소유하지 않거나 만료된 세션은 기존 404 계약을 유지한다.
- 새 응답 계약: bootstrap은 `{items, session_id, latest_job, has_older_jobs}`를 반환한다. `latest_job`은 기존 Job envelope 필드에 `request_text`, `created_at`을 더한 객체 또는 `null`이다.
- `GET /api/sessions/{session_id}/jobs`의 `{items}` 계약과 limit/offset 페이지 크기 100을 유지한다. 이력 페이지 요청은 쿠키 검증과 조회를 합친다.
- 프론트 `loadInitialConversation`은 bootstrap만 호출한다. 세션 복원은 이력 페이지를 순차 조회하고 각 페이지 응답을 바로 사용한다. 초기 복원에는 이전 세션 이력이나 이전 Job 재조회가 포함되지 않는다.
- 위젯 클라이언트는 FastAPI lifespan에서 생성·종료되며 API route, term search, background worker가 같은 프로세스 단일 인스턴스를 쓴다. 테스트용 사용자 주입 JSON loader는 그대로 지원한다.
- Pin 썸네일 URL과 이미지 바이트는 계속 DB에 저장하지 않는다.

## AC
- Given 유효 쿠키와 여러 세션, When 앱이 처음 로드되면, Then bootstrap 요청 1회로 생성 시각 최신 세션 목록과 최신 Job 하나를 표시한다.
- Given 최신 세션에 과거 Job이 있음, When 초기 화면이 준비되면, Then 과거 Job은 자동 재조회하지 않고 `이전 대화 불러오기` 동작을 제공한다.
- Given 사용자가 이전 대화 불러오기를 선택함, When 이력을 가져오면, Then Job별 상세 요청 없이 페이지당 한 번의 이력 요청으로 대화를 복원한다.
- Given 사용자가 다른 세션을 엶, When 그 세션 이력을 가져오면, Then 기존 세션 소유권 검증을 유지하고 페이지별 Job 묶음을 반환한다.
- Given 쿠키 소유자가 아닌 세션 ID, When 이력 endpoint를 호출하면, Then Job 데이터 없이 기존 404 계약을 반환한다.
- Given 두 번 이상의 위젯 요청, When 같은 API 프로세스에서 처리되면, Then 두 요청이 같은 HTTP client 연결 풀을 사용한다.
- Given 앱 종료, When lifespan이 끝나면, Then 공유 HTTP client가 닫힌다.
- Given 과거 이력 요청 실패, When 기존 최신 Job이 화면에 있음, Then 최신 Job을 지우지 않고 재시도 가능한 오류를 표시한다.
