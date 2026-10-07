# 요약 연결 단절 후 DB 풀 복구
## Why
긴 대화를 사용하는 사용자는 요약과 무관하게 답변을 받아야 한다. 배포 이미지의 Python 3.12.15 / asyncpg 0.31.0에서 요약 LLM 대기 중 DB 연결을 종료하고 즉시 계속 진행하면, 닫힌 연결의 슬롯이 풀에 반환되지 않는 타이밍을 재현했다. 반복 단절 후 풀의 가용 슬롯이 10→0으로 줄고 다음 DB 작업이 대기했다. 잠금 누적과 구분해 슬롯 반환 및 후속 실행을 측정한다.
## Goal
요약에 사용한 닫힌 연결을 풀에 반환하기 전에 명시적으로 정리하여 후속 DB 작업과 요약이 재개되게 한다. 정상 요약·중복 실행 차단·기존 오류 전파·기억 저장 동작을 유지한다. 별도 풀, 드라이버 업데이트, API/DB 스키마/모델/검색/배포 변경은 제외한다.
## What
정상 작업은 기존 풀 반환·reset을 사용한다. 연결 단절 시 닫혔지만 아직 풀에 붙어 있는 연결을 terminate하여 슬롯을 반환한다. 이미 풀 proxy가 해제된 경우에는 중복 정리하지 않는다. unlock 실패·취소·대상 없음 경로도 같은 정리 경계를 거친다. 요약 결과가 저장되지 않은 단절은 원본 backlog에서 재개한다.
## How
- PR #124의 ec8391e 위에 변경을 추가한다. 사용자 명시 요청에 따라 이번 PR은 400줄 제한의 예외로 처리한다.
- refresh_once의 pool.acquire 전체를 async context manager로 감싼다. acquire 이후 try-lock부터 조회·LLM·저장·unlock까지 기존 로직은 유지한다.
- yield의 finally에서 공개 is_closed()를 검사하고 닫힌 연결이면 공개 terminate()를 호출한다. 이 동기 정리는 원래 pool context의 release보다 먼저 실행한다.
- is_closed/terminate 과정에서 이미 해제된 proxy가 발생시키는 asyncpg.InterfaceError만 무시한다. 정상 작업의 오류/취소는 그대로 전파한다. 내부 holder/queue를 수정하거나 풀 전체를 종료하지 않는다.
- 열린 연결에는 terminate를 호출하지 않는다. 잠금 해제 및 기본 reset 정책은 그대로 유지한다. 연결 점유 시간이나 최대 연결 수는 변경하지 않는다.
- 로컬 PostgreSQL에서 pg_terminate_backend는 해당 격리 테스트의 요약 연결 PID만 대상으로 한다. 실제 LLM 대신 event로 대기한다. 운영 DB는 변경하지 않는다.
## AC
- Given 정상/대상 없는 실행, When 완료, Then 열린 연결은 재사용되고 다음 실행이 가능하다.
- Given 요약 LLM 대기 중 연결 단절, When 요약을 즉시 재개, Then 오류를 전파하면서 슬롯을 반환하고 같은 풀의 DB 작업과 다음 요약이 시간 제한 안에 성공한다.
- Given 최대 연결 10개에서 반복 단절, When 20번 재현, Then 풀 슬롯이 누적 유실되지 않으며 후속 DB 작업이 성공한다.
- Given unlock SQL 오류/reset 오류/취소, When 정리 완료, Then 다른 연결이 잠금을 얻고 같은 풀의 다음 요약이 가능하다.
- Given 이미 해제된 proxy, When 정리, Then 중복 정리 오류로 원래 결과나 예외를 바꾸지 않는다.
