# 요청 완료 후 필요한 대화 요약
## Why
긴 대화의 사용자는 요약 때문에 답변을 기다리거나 요청 없이 요약 비용이 발생하는 것을 원하지 않는다. 기존 1초 조회와 watermark 구간 누적 방식을 제거한다. 유휴 DB 조회·요약 호출 수, 요청 완료와 요약 시작 순서, 요약 중 DB 슬롯 가용성을 검증한다.
## Goal
새 요청 결과가 정상 저장된 이후 해당 대화에 요약할 원문이 있을 때만 실행한다. 요청/대상 없이 요약 조회 및 LLM 호출은 0회다. 워터마크·배치 순회·주기 재시도는 제거한다. 답변은 기존 요약과 최근 6개 원문으로 처리한다. UI/API/모델/배포/운영 데이터 일괄 삭제는 제외한다.
## What
요청 완료 후 최근 6개 밖 원문을 읽고 기존 요약 입력과 다르면 작업을 등록한다. 같은 대화의 대기 신호는 합친다. 백그라운드 작업은 해당 대화만 다시 확인하고 요약 전체를 재작성한다. 실패/취소/재시작은 자동 실행하지 않고 다음 완료 요청 때 다시 필요 여부를 확인한다. 짧은 대화·이미 동일한 입력·실패/stale/안전 거절 요청은 등록하지 않는다.
## How
- sessions.memory_json의 summary와 summary_sources는 유지한다. summarized_through를 읽거나 생성하지 않는다. 정상 저장 시 오래된 메타데이터를 제거하되 기존 요약 및 jobs 원문은 일괄 삭제하지 않는다.
- 오래된 종결 기록 중 가장 최근 20개를 시간순으로 정제한다. 입력은 최대 48,000자이며 초과 시 가장 오래된 기록부터 제외한다. 누락 여부를 summary_truncated에 저장하고 summary_incomplete로 본문 해석에 알린다. 오래된 원문 회상 검색은 유지한다.
- 정제된 records와 truncated의 SHA-256(summary_input_hash)을 비교하여 동일 입력의 불필요한 재작성을 생략한다. 이 값은 구간 경계가 아니며 새 요약에는 이전 summary를 넣지 않는다. LLM 호출은 한 번, 30초 제한, 출처는 이번 records에 포함된 Job ID만 허용한다.
- worker별 asyncio.Queue와 대기 session 집합을 사용한다. 완료 저장 후 필요한 경우만 등록하고 idle에서는 queue.get만 기다린다. startup 스캔·sleep·전체 대화 스캔·시간 기반 재시도 없음. 한 worker의 요약 동시성은 1개다.
- replica 중복 실행은 session별 summary_claim(token, expires_at)의 원자적 조건 UPDATE로 제어한다. 유효기간 60초, LLM 제한 30초다. 작업 소유권과 만료 시각을 확인한 결과만 저장한다. 만료·실패·종료 시 다음 요청이 재확보 가능하다. 서로 다른 replica의 다른 대화는 별도 작업이며 전역 advisory lock은 제거한다.
- 조회·claim·저장·해제는 짧은 DB 작업이다. LLM 동안 연결/트랜잭션/DB 잠금을 유지하지 않는다. 닫힌 연결 정리는 기존 summary_connection context를 짧은 DB 작업에 사용한다.
- foreground 저장은 DB의 최신 요약 필드와 작업 소유권을 보존한다. background 저장은 summary 관련 필드만 병합하고 조건/질문/Job 상태는 변경하지 않는다.
- conversation-summary-background 아래 memory-summary/generation을 기록한다. 신규 완료 Job의 trace 정보와 동일 대화 ID를 사용한다. shutdown은 요약을 취소·회수한 뒤 tracer를 닫는다.
## AC
- Given 요청이 없음, When startup 및 유휴 대기, Then 요약 DB 조회와 LLM 호출이 없다.
- Given 완료 저장된 요청과 최근 6개 밖 새 원문, When 필요 여부 확인, Then 해당 대화만 등록하고 답변은 요약 완료를 기다리지 않는다.
- Given 짧은 대화/동일 입력/실패 또는 stale 저장, When 처리, Then 요약 LLM은 호출되지 않는다.
- Given 긴 대화, When 요약 실행, Then 단일 입력으로 한 번 호출하고 watermark 없이 bounded 입력과 실제 출처를 저장한다.
- Given 같은 대화의 동시 실행 또는 만료된 소유권, When claim/저장, Then 유효한 소유자만 저장하고 이전 소유자는 최신 결과를 덮어쓰지 못한다.
- Given pool max_size=1과 LLM 대기, When 다른 DB 작업, Then timeout 없이 연결을 사용하고 foreground 완료도 가능하다.
- Given 요약 실패/취소/재시작, When 새 완료 요청이 없음, Then 자동 재시도가 없으며 기존 요약은 유지한다.
- Given 신규 요청과 요약 완료 저장이 겹침, When 저장 완료, Then 조건·질문·최신 요약과 claim이 서로 덮어써지지 않는다.
