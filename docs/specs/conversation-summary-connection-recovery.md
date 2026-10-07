# 요약 DB 연결 정리
## Why
배포 이미지 Python 3.12.15 / asyncpg 0.31.0에서 닫혔지만 아직 붙어 있는 proxy를 그냥 반환하면 슬롯 유실 타이밍을 재현했다. 요청 기반 요약은 LLM 중 연결을 잡지 않으며 짧은 DB 작업의 정리만 유지한다.
## Goal
닫힌 연결을 pool release 전에 명시적으로 정리하고 정상 연결은 재사용한다. 풀 수·연결 수·드라이버 변경은 제외한다.
## What
정상 종료는 기존 release/reset을 사용한다. 닫힌 연결은 terminate한다. 이미 해제된 proxy는 중복 정리하지 않는다. 요약 시작/재시도/소유권은 conversation-summary-background.md를 따른다.
## How
- summary_snapshot, 작업 claim, 결과 저장, claim 해제의 짧은 DB 작업은 summary_connection을 사용한다.
- context 종료 시 공개 is_closed()를 검사하고 닫힌 연결에만 terminate()를 호출한다. 이미 해제된 proxy의 InterfaceError는 무시하고 작업의 원래 예외는 유지한다.
- LLM 중에는 연결/트랜잭션/advisory lock을 점유하지 않는다. 내부 holder/queue를 조작하거나 공용 풀 전체를 종료하지 않는다.
- 검증은 격리 로컬 PostgreSQL과 LLM 대역에서만 실행한다.
## AC
- Given 정상/대상 없는 조회, When 완료, Then 같은 열린 연결을 재사용한다.
- Given 이미 해제된 proxy와 작업 예외, When 정리, Then 원래 예외를 보존한다.
- Given pool max_size=1 또는 10과 요약 LLM 대기, When 모든 슬롯을 동시에 acquire, Then 모든 슬롯을 시간 제한 안에 사용하고 결과 저장도 성공한다.
