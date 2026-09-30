# 후속 요청의 대화 맥락
## Why
EVAL-27과 확인 질문에 대한 후속 메시지는 현재 요청만으로 해석할 수 없다.
## Goal
동일 대화의 최근 6개 종결 job과 현재 조건, 미해결 질문을 해석에 연결한다. 다른 대화·외부 문서 사용은 제외한다.
## What
사용자의 명시적 조건과 수정은 역할별로 기억한다. 추천은 사용자 확정 사실로 바꾸지 않는다. 회상만으로 현재 조건을 수정하지 않는다. 안전 거절/실패 job은 조건을 갱신하지 않는다.
## How
sessions.memory_json에 constraints(role→term_id/evidence/source_job_id), pending_question, summary, summary_sources, summarized_through를 저장한다. 원본은 jobs다.
LLM 입력 session_context는 서버 전용이다. 정제된 job에는 job_id/요청/선택카드의 ID·역할·라벨/질문·안내만 포함한다. URL·Pin·썸네일은 포함하지 않는다.
InterpretationSelection.source_job_id는 nullable UUID다. null이면 현재 요청 evidence를 확인하고, 값이 있으면 같은 대화의 선행 원본 요청 또는 검증된 카드 라벨의 실제 인용인지 확인한다. source_job_id만으로 조건을 변경하지 않는다.
구조화 context_updates는 현재 요청의 명시적 근거를 가진 역할별 set/clear만 허용한다. set 카드에 resolver와 같은 활성/역할/의존 검증을 적용한다. 모호하면 기존 조건을 유지하고 질문한다.
worker는 선행 종결 job만 사용한다. job 완료와 memory_json 갱신은 attempt/상태/만료를 확인한 한 transaction이다. failed·stale attempt는 기억을 쓰지 않는다.
## AC
- Given A의 체형, When B 요청, Then A 기록은 prompt에 없다.
- Given 앞선 체형과 포즈, When 포즈만 변경 요청, Then 현재 체형을 유지하고 포즈 결과만 반환한다.
- Given 확인 질문, When 짧은 답, Then 이전 질문이 prompt에 포함된다.
- Given 타 대화 출처/없는 인용/비활성 카드, When 출력 검증, Then 결과와 기억 저장을 거부한다.
- Given stale attempt, When 완료, Then job과 memory 모두 변경되지 않는다.
