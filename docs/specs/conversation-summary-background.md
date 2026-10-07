# 답변과 분리된 대화 요약
## Why
긴 대화를 테스트하는 사용자는 요약 LLM 때문에 답변 전 12~17초를 기다린다. 요청 재시도에서는 미저장 요약도 반복한다. 답변 경로의 summarize 호출 수와 요약 실패로 인한 요청 재시도를 측정한다.
## Goal
답변 경로의 summarize 호출은 0회다. 요약 실패는 답변 상태를 변경하지 않는다. 원본·기존 조건·확인 질문·회상 출처 검증은 유지한다. 모델·검색·UI·배포 변경은 제외한다.
## What
답변은 저장된 요약과 최근 6개 기록으로 처리한다. 별도 worker가 미요약 기록을 갱신한다. 종료·실패 후 미처리 기록은 DB에서 다시 발견한다. 중복 worker는 동시에 요약하지 않는다. 새 요청과 요약 저장이 겹쳐도 조건 및 최신 요약을 잃지 않는다.
## How
- API·DB 스키마 변경 없음. prepare는 load와 미요약 여부 조회만 수행한다. summary_incomplete를 유지한다.
- 기존 상시 worker에 전역 동시성 1인 별도 요약 루프를 추가한다. PostgreSQL advisory lock으로 replica 간 중복 실행을 막고 finally에서 해제한다. LLM 중 session row lock은 잡지 않는다.
- 닫힌 요약 연결의 슬롯 반환은 conversation-summary-connection-recovery.md를 따른다. 연결 풀 크기와 요약 동시성은 변경하지 않는다.
- 살아 있는 session의 종결 기록에서 최근 6개 밖이면서 watermark 이후인 기록을 찾는다. 실행 시점 cutoff의 원본만 대상으로 기존 출처 검증·최대 2배치·30초 제한을 사용한다.
- 성공 시 summary/summary_sources/summarized_through만 JSONB 병합한다. 최초 watermark가 그대로일 때만 저장하며 실패·취소는 저장하지 않는다. foreground 완료는 DB의 최신 요약 필드를 보존한다.
- 루프 간격: 성공/빈 조회 1초, 오류 30초. 오류에는 유형만 로그 기록한다. shutdown 시 모든 worker 루프를 취소하고 기다린 뒤 tracer를 닫는다.
- 별도 agent-job-attempt 대신 conversation-summary-background span 아래 memory-summary 및 generation을 기록한다. 기존 종결 job의 trace 정보를 사용하지만 상태는 변경하지 않는다.
## AC
- Given 긴 대화, When 새 요청, Then summarize 없이 최근 기록과 저장된 요약을 전달하고 완료한다.
- Given 미요약 기록, When 별도 worker 실행, Then 출처 검증 후 watermark를 저장하고 다시 실행해 이미 요약된 기록을 처리하지 않는다.
- Given 요약 실패/취소, When 이후 worker 실행, Then watermark는 유지되고 요청 완료 상태는 변하지 않으며 재개한다.
- Given 중복 worker, When 동시 실행, Then 하나만 LLM을 호출한다.
- Given 요약과 조건 갱신이 겹침, When 양쪽 저장 완료, Then 최신 요약과 조건을 모두 보존한다.
