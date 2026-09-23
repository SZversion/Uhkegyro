# UH케그려 평가셋

이 폴더는 캐주얼 캐릭터 일러스트 레퍼런스 해석 Agent의 **고정 평가 원본**을 관리한다. 결과 문장을 하나 맞히는 시험이 아니라, 사용자 입력이 현재 API 계약을 지키며 적절한 활성 TERM_CARD·질문·실패 상태로 끝나는지를 평가한다.

## 실행 원본과 범위

| 파일 | 역할 | 현재 실행 기준 |
| --- | --- | --- |
| [dataset.jsonl](./dataset.jsonl) | 30건 원문 평가셋 | baseline·개선 후 재측정에 사용하는 유일한 실행 원본 |
| [evaluation-set.md](./evaluation-set.md) | 30건 사람이 읽는 요약표 | 문항 의도와 커버리지 검토 |
| [rubric-and-baseline.md](./rubric-and-baseline.md) | rubric·baseline 기록 양식 | 사람이 채점하고 Langfuse 결과를 기록하는 기준 |
| [contract-variants.jsonl](./contract-variants.jsonl) | 70건 고정 변형 초안 | **현재 baseline에서는 제외**. 최신 비동기 API 계약 이행 뒤 별도 PR에서 활성화 |

`dataset.jsonl`의 각 줄은 독립 JSON이다. 줄 순서와 ID는 개선 전후 비교를 위해 고정하며, 입력·기대값을 바꾸면 dataset 버전과 변경 이유를 함께 기록한다.

## 단일 계약 기준

평가 원본은 다음 문서를 따른다.

- `docs/specs/api-contract.md`: `POST /api/agent`의 `202 + queued`, polling한 종결 `JobEnvelope`, 상태·사유 코드·실패 코드
- `docs/specs/term-card-catalog.md`: 시작 검증, 활성 TERM_CARD, `query_fragments` 전용 검색
- `docs/specs/mcp-contract.md`: `get_active_term_card(term_id)`의 활성 카드 조회 경계
- `docs/specs/trust-boundary.md`: 입력·검색 provider 결과와 비밀값의 신뢰 경계
- `skills/SKILL.md`: 도메인 용어·추론·질문 규칙

각 문항은 제출 단계와 종결 단계를 분리해 평가한다.

```text
POST /api/agent
  -> 202 + job_status="queued"
  -> GET /api/jobs/{job_id} polling
  -> completed + AgentResult 또는 failed + failure
```

## 30건 커버리지

| 구분 | 수 | 평가 목적 |
| --- | ---: | --- |
| `normal` | 10 | 명확한 일상어를 활성 `body`·`pose`·`view`·`perspective`·`layout` 카드로 역할 분리 |
| `boundary` | 6 | 모호·상충·부정 조건에서 추측 대신 질문 하나 또는 제한된 선택 |
| `failure_inducing` | 6 | 이미지 생성·분석·다운로드·비밀 노출·프롬프트 주입을 도구 호출 없이 종결 |
| `prd_flow` | 8 | Pin 0건·삭제·timeout, 후속 job, MCP 근거, 구조화 출력 재시도, worker 중단 |
| **합계** | **30** | 정상·경계·실패 유도와 운영 흐름을 같은 원본으로 반복 측정 |

## JSONL 필드

| 필드 | 역할 |
| --- | --- |
| `id` | `EVAL-01`부터 `EVAL-30`까지의 고정 식별자 |
| `category`, `complexity` | 커버리지·난이도별 결과를 나누기 위한 분류 |
| `input`, `session_context` | 사용자 입력과 필요한 최소 대화 맥락. `session_context`는 서버 측 맥락이며 브라우저 요청 본문이 아니다. |
| `runtime_fixture` | LLM·MCP·검색 provider·worker의 테스트 double 조건. 실제 Pinterest 데이터나 사용자 Pin을 저장하지 않는다. |
| `expected.submission` | 반드시 먼저 확인할 `202 + queued` 제출 계약 |
| `expected.terminal` | polling 뒤 확인할 `completed` 또는 `failed` 종결 계약 |
| `required_selections`, `forbidden_term_ids` | 활성 카드 선택·금지 선택 검증 기준 |
| `reference_plan`, `tool_calls` | 선택 역할·검색 조각·MCP·검색 호출 경계 |
| `clarifying_question` | 질문 수·쉬운 언어 여부와, 경계 문항에서 반드시 확인할 도메인 단서 |
| `judge` | 규칙 검사 뒤 사람 또는 생성 모델과 다른 judge가 평가할 품질 축 |
| `why` | 기대값을 정한 도메인·계약 근거 |

## 판정 순서

1. **결정론 검사**: JSON/Pydantic, 제출·종결 상태, 활성 term ID, 역할, reason code, 도구 호출, Pin 최대 8개를 검사한다.
2. **정성 검사**: 결정론 검사를 통과한 원문 문항에 한해 용어 적절성·초보자 안내·추가 질문을 0~2점으로 평가한다.
3. **기록**: 모든 실행은 [rubric-and-baseline.md](./rubric-and-baseline.md)의 run metadata와 문항별 근거를 남긴다.

LLM-as-judge를 사용할 때는 생성 모델과 다른 모델 또는 사람 검토자를 사용한다. judge는 답변 길이나 자신감이 아니라 응답에 있는 입력 근거와 카드 기반 설명을 먼저 적고 점수를 매긴다.

## 실행 전 체크

1. 30줄을 독립 JSON으로 파싱하고 ID가 유일한지 확인한다.
2. `required_selections`와 `forbidden_term_ids`가 현재 활성 TERM_CARD에 맞는지 확인한다.
3. `runtime_fixture`를 실제 외부 네트워크가 아닌 테스트 double로 재현한다.
4. 30건을 Langfuse Dataset으로 등록하고, dataset 버전·Git commit·TERM_CARD catalog version·프롬프트 버전을 baseline에 기록한다.
5. 모델 또는 프롬프트 변경은 한 번에 하나만 하고, 같은 30건을 다시 실행해 회귀 문항을 기록한다.

현재 `contract-variants.jsonl`은 이전 동기식 계약의 필드를 포함한 보관용 초안이다. 이를 현재 30건과 합쳐 100건 평가라고 주장하지 않으며, 이행 전에는 Langfuse Dataset·출시 게이트·baseline 수치에 사용하지 않는다.
