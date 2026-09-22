# 평가셋

필수 조건 4 — **최소 30건**. 개선 전후를 같은 셋으로 비교합니다.

실행용 원본은 [dataset.jsonl](./dataset.jsonl)이며, 팀 검토용 요약표는
[evaluation-set.md](./evaluation-set.md)에서 확인합니다. `dataset.jsonl`의 각 줄은
독립 JSON이므로 줄바꿈·정렬을 바꾸지 않습니다.

`dataset.jsonl`은 사람·judge가 의미 품질을 검토하는 30건 원문이다. 별도의
[contract-variants.jsonl](./contract-variants.jsonl)은 원문의 고정 변형 70건으로 계약
준수만 검증한다. 두 파일을 합친 100건 평가는 개선 전후의 상태·허용 `term_id`·금지 행동·검색
계획 회귀를 비교하며, 변형 입력은 실행마다 무작위로 만들지 않는다.

## 최신 계약 기준과 이행 상태

평가의 단일 계약 기준은 최신 `main`의 `docs/specs/api-contract.md`,
`docs/specs/term-card-catalog.md`, `docs/specs/trust-boundary.md`, `docs/SDD.md`다. 이 문서는
그 계약에 맞춘 목표 평가 형식을 설명한다.

현재 두 JSONL에는 이전 동기식 계약의 `http_status`, `status`, `pinit.js_embedPin`, 이전
사유 코드가 남아 있다. 이 문서 변경만으로 그 행들이 최신 API를 검증할 수 있게 되는 것은 아니다.
실행 평가를 시작하기 전에 30개 원문과 이를 상속하는 70개 변형을 같은 데이터 변경에서 아래 계약으로
이행해야 한다.

Pin URL·상태를 세션에 저장한다는 `main`의 개요 README 설명은, Pin URL·상태를 저장하지 않는다는
`docs/SDD.md` 설명과 상충한다. API·SDD·신뢰 경계에는 이 항목의 저장 요구를 새 평가 기대값으로
고정하지 않는다. 팀이 상위 계약을 하나로 정하면 해당 항목을 별도 평가 조건으로 추가한다.

## 기준 PRD와 공개 API 계약

이 평가셋은 PRD의 사용자 흐름과 팀이 관리하는 정적 TERM_CARD 카탈로그 계약을 함께 검증한다.

- 현재 런타임 허용 `term_id`와 역할만 선택하고, 모든 카드는 `source_type=team_card`여야 한다.
- 브라우저는 `POST /api/agent`로 자연어만 전송해 `202`와 `job_status="queued"`를 받고,
  `GET /api/jobs/{job_id}` polling으로만 종결 결과를 확인한다.
- 종결 job은 `completed` 또는 `failed`다. `completed`의 `AgentResult.agent_status`는
  `success`, `needs_clarification`, `out_of_scope`, `unsafe_input`, `partial_result`만
  허용하며, `service_unavailable`은 사용하지 않는다.
- 선택 역할마다 활성 카드의 `query_fragments`만 검색하고, `TermResult.pins`는 역할별 최대
  8개다. UI는 원본 `pin_url`을 링크로 표시하고 `thumbnail_url`은 현재 응답에서만 선택적으로
  사용한다. `pinit.js`와 Pin 이미지·썸네일 URL·메타데이터의 저장 또는 재게시를 기대하지 않는다.
- 정상 0건은 `PIN_RESULTS_EMPTY`, 검색 재시도 소진은 `PIN_SEARCH_UNAVAILABLE`이며 모두
  `completed + partial_result`의 역할 결과로 표현한다. 최종 worker 실패는 `failed` job의
  안정된 `failure_code`로 확인한다.
- 후속 사용자 메시지는 기존 attempt를 재시도하지 않는 새 job이다. 브라우저는 이전 `term_id`,
  검색어, Pin URL을 요청 본문에 다시 보내지 않는다.

## JSONL 필드와 목표 형식

| 필드 | 용도 |
| --- | --- |
| `category` | `normal` · `boundary` · `failure_inducing` · `prd_flow` |
| `prd_ac` | 이전 PRD 번호 기반 추적 필드. 이행 시 최신 Spec/AC 참조로 다시 대조한다. |
| `runtime_fixture` | 테스트 double이 재현할 LLM·검색 provider·TERM_CARD·job worker 조건 |
| `expected` | 제출 응답(`202 + queued`)과 polling한 종결 `JobEnvelope`를 구분해, 선택 용어·Pin 결과·사유 코드·failure를 검증 |
| `judge` | 규칙 기반 검사를 먼저 하고, 필요할 때 설명 품질 평가를 추가한다는 뜻 |

`runtime_fixture`는 실제 외부 서비스를 조작한다는 뜻이 아니다. 테스트 double 또는
모의 응답으로 재현할 조건이며, 실제 배포 환경의 Pinterest 데이터·사용자 Pin을 기록하지 않는다.

## 측정 축과 판정

| 축 | 판정 | 점수 |
| --- | --- | --- |
| 비동기 API·선택 정확성 | `202` 제출, job polling, 종결 상태, 활성 `term_id`, 역할, 금지 용어, 사유 코드, failure를 규칙 기반 검사 | 통과/실패 |
| 레퍼런스 흐름 정확성 | `query_fragments` 전용 검색, 역할별 최대 8개 Pin, `available`·`thumbnail_unavailable`·`deleted`, 팀 카드 검수 정보를 규칙 기반 검사 | 통과/실패 |
| 초보자 안내 품질 | 쉬운 설명·선택 근거·관찰 지점·혼동 안내·추가 질문의 충실도를 0~2점으로 평가 | 0/1/2 |

세 번째 축의 judge는 생성 모델과 다른 모델 또는 사람 검토자로 운영한다. judge는 응답 속도나
길이를 높게 평가하지 않고, 응답 안의 근거를 먼저 찾아 점수와 이유를 함께 남긴다. 실제 모델과
judge는 구현 후 Langfuse Dataset 실행 기록과 `EVAL_REPORT.md`에 명시한다.

## 구성

| 종류 | 왜 필요한가 |
|---|---|
| 정상 케이스 | 비동기 제출 뒤 검증된 TERM_CARD와 Pin 결과를 조립하는 기본 흐름 확인 |
| 경계 케이스 | 모호·상충 입력에 `needs_clarification`과 질문 하나를 반환하는지 확인 |
| 실패 유도 | 범위 밖·안전 위반 요청에서 LLM·검색 호출 없이 종결하는지 확인 |
| PRD 흐름 | queue/polling·Pin 0건·삭제·검색 오류·새 job·카탈로그 검증·worker 실패를 확인 |

**잘 되는 것만 모으면 평가가 아니라 자랑입니다.** 실패 사례를 반드시 넣으세요.

## 만드는 시점

**프로젝트 초반(9/23까지)에 만듭니다.** 나중에 만들면 이미 튜닝된 결과에 맞춰집니다.
추석 연휴(9/24~27) 전에 문제 정의와 이 평가셋이 확정돼 있어야 연휴 동안 각자 진행할 수 있습니다.

## 판정 방식

정확 일치 · 스키마 통과 여부 · 규칙 기반 채점 · LLM-as-judge 모두 가능합니다.
다만 **어떤 방식이고 그 방식의 한계가 무엇인지** 리포트에 적어야 합니다.

> LLM-as-judge를 쓴다면 생성 모델과 판정 모델을 같은 것으로 두지 마세요. 후한 점수가 나옵니다.
