# 요청 기반 대화 요약 검증 (2026-10-07)

## 변경
기존 #124의 워터마크(summarized_through) 구간별 누적 요약과 1초/오류 30초 주기 실행을 제거했다. 새 요청 결과 저장 성공 후 해당 session에 요약 대상이 있고 입력이 달라졌을 때만 대기열에 등록한다. 대상이 없는 대화와 이미 같은 입력은 건너뛴다. 같은 대화의 대기 신호는 합친다. 서버 시작·시간 경과·다른 대화의 요청으로 자동 요약하지 않는다.

요약은 이전 summary를 합치지 않고 최근 6개 밖 원문의 스냅샷으로 한 번 재작성한다. 최근 오래된 기록 최대 20개/48,000자 제한이며 누락은 summary_truncated 및 summary_incomplete로 표시한다. 원본 회상 검색은 유지한다. summary_input_hash는 입력 동일 여부 확인용이며 구간 경계가 아니다.

LLM 대기 중 DB 연결·트랜잭션·advisory lock을 유지하지 않는다. session별 60초 소유권과 저장 시 토큰/만료 검증으로 중복 및 오래된 결과 덮어쓰기를 방지한다. LLM 제한은 30초이며 실패 후에는 다음 완료 요청 때만 다시 필요 여부를 확인한다. shutdown 때 작업을 취소·회수한다.

## 환경
운영 이미지 sha256:2b25cf67c7d248db27bc80a0d6a1565397fb963b79516e590d09dbdfe85fb7b4의 Python 3.12.15 / asyncpg 0.31.0과 별도 로컬 PostgreSQL 17을 사용했다. 코드 mount는 readonly, 실제 LLM은 대역이다. 운영 DB·Langfuse·배포에는 쓰지 않았다.

## 결과
- 발행 전 최신 main(d9f5d39) 위로 rebase 후 전체 재검증: **611 passed, 17 skipped, 1 failed** (16.53s). MCP 캐시 갱신 루프를 유지하고 요약 큐 인자만 추가했다. 기존 동일 pending_question 실패 1개 외 신규 실패는 없다.
- 전체 backend 회귀 실행: 590 passed, 17 skipped, 1 failed (15.63s). 유일한 실패는 기존 baseline에서 확인한 test_eval27_followup_preserves_body_and_pending_question의 pending_question 불일치다.
- 이후 저장 실패/stale 및 입력 문자 제한 AC 3개를 추가했다. 관련 최종 테스트: 47 passed, 1 deselected (4.65s). deselected는 위 기존 실패 1개이며 전체 suite 통과라고 보고하지 않는다.
- 요청 없는 유휴 루프: DB 접근 및 LLM 생성/호출 없음.
- 기존 미요약 데이터가 있어도 신규 완료 요청 전에는 실행 안 함.
- 완료 저장 후 요약 시작, max_size=1에서 LLM 대기 중 SELECT와 다음 요청 완료 성공.
- max_size=1/10에서 요약 LLM 대기 중 모든 DB 슬롯을 동시 acquire 성공.
- 대상 없는 session 및 동일 입력 skip, 같은 대화 동시 신호 합치기, 다른 session 요약 안 함.
- 실패 후 시간 기반 재시도 없음, 다음 요청 신호에서 재시도 가능. 취소 시 기존 요약 유지 및 claim 정리.
- 중복 claim 차단, 만료 후 새 소유자의 결과 저장, 이전 소유자의 덮어쓰기 차단.
- legacy watermark를 읽지 않고 이전 summary/summary_sources 없이 새 snapshot 요약, 조건·질문 보존.
- 긴 대화는 단일 LLM 호출, bounded 입력과 누락 표시, 원본 출처 검증 유지.

## 제한 및 상태
이 방식은 시간 기반 자동 복구를 수행하지 않는다. 재시작·실패 뒤 새 요청이 없으면 기존 요약을 사용한다. 오래된 기록이 입력 한도를 넘으면 요약은 일부 기록만 포함하며 회상은 원본을 검색한다. 정상 요약 LLM을 위한 제공자 동시 요청 제한은 여전히 답변과 공유한다. 실제 응답 지연의 개선 폭은 배포 후 트레이싱으로 측정해야 한다.

기존 요약/원본 데이터 일괄 삭제는 수행하지 않았다. 사용자가 요청한 코드·동작 교체이며 운영 데이터 삭제 범위는 확정하지 않았다. 기존 요약은 새 요약 성공 때 교체하고 폐기한 watermark 메타데이터는 정상 저장 시 제거한다. 검증 시점에는 #124 작업 worktree의 로컬 수정이며 커밋·푸시·배포하지 않았다. #124가 병합된 뒤 사용자 요청에 따라 최신 main 위의 후속 PR로 발행한다. 동일 요약 작업에 앞서 승인한 400줄 초과 예외를 적용하며 운영 배포는 제외한다.


## PR #129 리뷰 반영: 요약 출력 길이
리뷰 https://github.com/aihuman-7th/proj2-4/pull/129#issuecomment-6030325585 에 따라 SummaryOutput.text 최대 길이를 2,000자에서 600자로 줄였다. 최소 길이는 기존 1자를 유지한다. v4의 Memory summarize 지침은 필요할 때 400~600자를 목표로 하되 더 짧은 요약을 허용하고 억지로 채우지 않게 변경했다. 요약 결과는 sessions.memory_json.summary에 저장한다.

새 테스트 7개에서 실제 adapter로 1/399/400/600자 허용, 빈 출력/601자 거부, prompt에 전달되는 JSON Schema의 1~600자 제한과 안내, 과도한 출력 시 기존 summary/hash/pending_question 보존을 검증했다. 입력 길이·회상 답변 길이·기존 데이터의 일괄 삭제/잘라내기는 변경하지 않았다.

리뷰 수정 후 요약 관련/LLM adapter 회귀: **124 passed, 1 deselected** (5.38s). deselected는 위에서 기록한 기존 pending_question 실패 1개다. 이 결과는 전체 backend suite 통과를 뜻하지 않는다. 실제 배포 이미지 runtime과 격리 PostgreSQL/LLM 대역으로 실행했고 운영 DB·유료 LLM·배포에는 쓰지 않았다.
