# 일러스트 레퍼런스 Agent 현행 비동기 Job·실패 상태 계약

## Why

- **사용자**: 체형·포즈·시점·원근·구도 용어가 낯선 캐주얼 캐릭터 일러스트 초보자.
- **상황**: 용어 해석, 자체 TERM_CARD DB 검증, Pinterest 검색은 한 HTTP 요청 안에서 끝나지 않을 수 있다.
- **문제**: 정보 부족·범위 밖·부분 검색 결과·worker 실패를 모두 같은 HTTP 오류로 처리하면 사용자는 질문에 답해야 하는지, 결과를 사용할 수 있는지, job을 재시도해야 하는지 알 수 없다.
- **측정 지표**: 30건 품질 평가의 의미 결과·실패 코드 일치율 100%, 100건 계약 평가의 job 상태·필수 필드·종결 상태 처리 준수율 100%. 실제 측정값은 구현 후 `EVAL_REPORT.md`에 기록한다.

## Goal

- 공개 요청은 job을 만들고 `202`를 반환하며, 최종 의미 결과는 `completed` job에서만 제공한다.
- 사용자 의미 상태는 `AgentResult`로, 실행 실패는 `failed` job의 `failure`로 분리한다.
- LLM은 의미 해석 JSON만 만들고, 최종 역할·카드 검증·검색 계획·job 상태 전이는 서버가 결정한다.

## What

### 1. Job 상태와 전이

허용 `job_status`는 `queued`, `running`, `validating`, `searching`, `rendering`, `completed`, `failed`다. `completed`와 `failed`만 종결 상태이며, 종결 뒤 상태는 바뀌지 않는다.

```text
queued → running → validating → searching → rendering → completed
                   ↘ failed
```

`GET /api/jobs/{job_id}`는 소유자가 polling하는 조회 API다. 진행 중 job은 `result=null`, `failure=null`, `poll_after_ms=1000`을 반환한다. 종결 job은 `poll_after_ms=null`을 반환한다.

```json
{
  "job_id": "server-issued-uuid",
  "session_id": "server-issued-uuid",
  "request_id": "opaque-request-id",
  "job_status": "completed",
  "attempt": 1,
  "max_attempts": 3,
  "poll_after_ms": null,
  "retryable": false,
  "result": "AgentResult | null",
  "failure": "JobFailure | null"
}
```

### 2. 완료 job의 의미 결과

`completed` job만 아래 `AgentResult`를 가진다. `service_unavailable`은 결과 상태가 아니라 worker 실행 실패이므로 `failed` job의 `failure`로 표현한다.

```json
{
  "agent_status": "success | needs_clarification | out_of_scope | unsafe_input | partial_result",
  "reason_codes": ["ZERO_OR_MORE_REASON_CODES"],
  "reference_plan": "ReferencePlan | null",
  "clarifying_question": "string | null",
  "user_message": "사용자에게 보여 줄 짧은 안내"
}
```

- `success`, `partial_result`는 `reference_plan`을 반드시 가진다.
- `needs_clarification`은 `reference_plan=null`과 질문 하나를 가진다.
- `out_of_scope`, `unsafe_input`은 `reference_plan=null`이며, 처리할 도구를 호출하지 않는다.
- `reason_codes`에는 외부 오류 원문, 사용자 원문, 비밀값을 넣지 않는다.

```json
{
  "terms": [
    {
      "role": "body | pose | view | perspective | layout",
      "term_id": "active_term_id_only",
      "label_ko": "팀 검수 용어",
      "label_en": "standard term",
      "explanation_ko": "팀 카드에서 조립한 초보자용 설명",
      "evidence": ["사용자 입력의 짧은 근거"],
      "look_for": ["레퍼런스에서 확인할 지점"],
      "search_url": "https://www.pinterest.com/search/pins/?q=...",
      "pins": [
        {
          "pin_url": "https://www.pinterest.com/pin/...",
          "thumbnail_url": "https://provider-returned-thumbnail/... | null",
          "status": "available | thumbnail_unavailable | deleted"
        }
      ]
    }
  ],
  "unresolved_roles": ["body | pose | view | perspective | layout"]
}
```

- `terms`는 `body → pose → view → perspective → layout` 순서를 지키며 역할당 최대 하나의 검증된 활성 카드만 가진다.
- `pins`는 역할당 최대 8개다. `thumbnail_url`은 검색 provider가 반환한 응답 전용 표시 URL이며, UI는 원본 `pin_url`을 클릭 대상으로 사용한다.
- `thumbnail_url=null` 또는 `status=thumbnail_unavailable`이면 원본 Pin 링크만 표시한다. `deleted` Pin은 링크와 썸네일을 표시하지 않는다.
- 이미지 바이트·썸네일 URL·Pin 메타데이터는 DB, 세션, 로그에 저장하거나 재게시하지 않는다. Pin URL과 상태만 1개월 세션 이력에 저장한다.

### 3. 의미 상태와 사유 코드

| `agent_status` | 대표 사유 코드 | 화면 행동 |
| --- | --- | --- |
| `success` | 없음 | 선택된 역할의 용어·확인 지점·검색 결과 표시 |
| `needs_clarification` | `ABSTRACT_INTENT_ONLY`, `INSUFFICIENT_VISUAL_EVIDENCE`, `CONFLICTING_CONSTRAINTS`, `TEAM_TERM_CARD_UNAVAILABLE` | 용어·링크를 추측하지 않고 질문 하나 표시 |
| `out_of_scope` | `IMAGE_GENERATION_REQUEST`, `IMAGE_ANALYSIS_REQUEST`, `STYLE_REPLICATION_REQUEST`, `PIN_COLLECTION_REQUEST`, `UNSUPPORTED_SUBJECT` | 텍스트 기반 체형·포즈·시점·원근·구도 해석 범위 안내 |
| `unsafe_input` | `PROMPT_INJECTION_ATTEMPT`, `SECRET_EXTRACTION_ATTEMPT`, `HARMFUL_OR_ILLICIT_REQUEST` | 입력 원문을 되풀이하지 않고 안전한 범위 안내 |
| `partial_result` | `PIN_RESULTS_EMPTY`, `PIN_DELETED`, `PIN_THUMBNAIL_UNAVAILABLE`, `PIN_SEARCH_UNAVAILABLE`, `SEARCH_URL_BUILD_FAILED` | 사용 가능한 카드·썸네일·원본 링크와 빠진 이유 표시 |

### 4. 실패 job과 재시도

`failed` job은 `result=null`과 `JobFailure`를 가진다. `failure_code`는 다음 허용 enum만 쓴다.

| 코드 | 확정 조건 | `retryable` |
| --- | --- | --- |
| `JOB_TIMEOUT` | worker가 앱 관리 job 제한 시간을 넘기기 전에 중단 처리함 | `attempt < max_attempts`일 때 `true` |
| `INSTANCE_INTERRUPTED` | worker lease가 만료돼 recovery가 실행 중단 job을 `failed`로 종결함 | `attempt < max_attempts`일 때 `true` |
| `PROCESSING_ERROR` | DB·LLM·Pydantic·resolver의 처리 예외를 안전하게 분류하지 못했음 | `attempt < max_attempts`일 때 `true` |

Cloud Run 종료 자체는 HTTP 응답을 만들지 못할 수 있다. 따라서 worker는 job 상태와 lease를 영속 저장하고, recovery가 만료 lease를 발견했을 때만 `INSTANCE_INTERRUPTED`으로 종결한다. 브라우저는 다음 polling 응답에서 이 실패를 확인한다. 네트워크 오류·JSON이 아닌 5xx는 job 상태를 추측하지 않는 전송 실패 UI로 처리한다.

재시도는 자동으로 실행하지 않는다. `POST /api/jobs/{job_id}/retry`를 누를 때만 새 job을 생성하며, 원 job을 포함한 최대 시도 횟수는 `3`이다. 모든 job 실행은 `request_id`, `job_id`, `attempt`, `error_type`, `model`, `prompt_version`, `latency_ms`를 기록한다.

### 5. LLM·규칙·검색 처리

1. worker가 `queued` job을 claim하고 `running`으로 전이한다.
2. 입력 1~500자 검증 실패는 job을 만들지 않고 메시지 endpoint에서 HTTP `422`를 반환한다.
3. LLM은 `{role, term_id, evidence, confidence}` 후보와 의미 상태만 구조화 출력한다.
4. resolver가 자체 TERM_CARD DB의 활성 여부·역할·조건을 검증하고 `validating` 상태를 기록한다.
5. 단서가 없으면 `needs_clarification` 결과를 만들어 `completed`로 종결한다.
6. 범위 밖·안전 거부는 도구 호출 없이 해당 의미 결과를 만들어 `completed`로 종결한다.
7. 유효 카드마다 검색 provider에 검증된 `query_fragments`만 전달하고 `searching`·`rendering` 상태를 기록한다.
8. 검색 오류가 있어도 카드가 하나 이상 유효하면 `partial_result`로 `completed`한다. 카드·결과를 안전하게 조립할 수 없는 처리 실패는 `failed`와 `PROCESSING_ERROR`으로 종결한다.

Getty API·SPARQL·Getty 데이터 조회·임시 LLM 용어 폴백은 사용하지 않는다. 자체 TERM_CARD DB에 없는 표현은 새 용어를 만들지 않고 추가 질문 또는 `pending_human_review`로 처리한다.

## How

### 재시도 정책

| 실패 유형 | 최초 뒤 추가 시도 | 재시도 전략 | 백오프 | 포기·사용자 응답 |
| --- | ---: | --- | --- | --- |
| LLM 구조화 출력/Pydantic 위반 | 자동 0회 | 현재 job을 `PROCESSING_ERROR`으로 종결 | 없음 | 수동 재시도; 3회째면 재시도 비활성 |
| LLM timeout | 자동 0회 | 현재 job을 `JOB_TIMEOUT`으로 종결 | 없음 | 수동 재시도; 3회째면 재시도 비활성 |
| LLM 5xx·429·미완료 | 자동 0회 | 현재 job을 `PROCESSING_ERROR`으로 종결 | 없음 | 수동 재시도; 3회째면 재시도 비활성 |
| 검색 provider 오류 | 자동 0회 | 유효 카드가 있으면 `partial_result`, 없으면 `PROCESSING_ERROR` | 없음 | 부분 결과 사용 또는 수동 재시도 |
| worker lease 만료 | 자동 0회 | recovery가 `INSTANCE_INTERRUPTED`으로 종결 | 없음 | 수동 재시도; 3회째면 재시도 비활성 |

### UI 규칙

- 메시지 제출 직후에는 `queued` 상태만 표시한다.
- polling 중에는 서버가 반환한 `job_status`만 표시하고 완료 예정 시간·가짜 진행률을 만들지 않는다.
- `completed`에서만 역할별 카드, 원격 썸네일, 원본 Pin 링크, 추가 질문을 표시한다.
- `failed`에서는 `failure.user_message`과 재시도 가능 여부만 표시한다. 오류 원문·비밀값·내부 trace는 표시하지 않는다.

## AC

**AC-01 · 비동기 job 생성**
- GIVEN: 유효 세션과 1~500자 입력
- WHEN: 메시지 endpoint를 호출한다.
- THEN: HTTP `202`, 새 `job_id`, `job_status=queued`, `poll_after_ms=1000`을 반환한다.

**AC-02 · 정보 부족은 완료 결과**
- GIVEN: 탐색 축을 특정하지 않은 입력
- WHEN: worker가 해석한다.
- THEN: job은 `completed`, `agent_status=needs_clarification`, 질문 하나, `reference_plan=null`으로 종결한다.

**AC-03 · 부분 검색 결과**
- GIVEN: 활성 카드가 있으나 일부 provider 검색이 실패한다.
- WHEN: worker가 결과를 조립한다.
- THEN: job은 `completed`, `agent_status=partial_result`이며 가능한 카드와 실패 사유만 표시한다.

**AC-04 · worker 실패 복구**
- GIVEN: worker lease가 만료된 실행 중 job
- WHEN: recovery가 해당 job을 확인한다.
- THEN: job은 `failed`, `failure_code=INSTANCE_INTERRUPTED`, `result=null`으로 한 번만 종결한다.

**AC-05 · 수동 재시도 한도**
- GIVEN: `failed`, `retryable=true`, `attempt < 3`인 job
- WHEN: 사용자가 재시도를 누른다.
- THEN: 새 job을 `queued`로 만들고, 자동 재시도 없이 3회째 실패 뒤 `retryable=false`로 종결한다.

**AC-06 · 썸네일 경계**
- GIVEN: provider가 `thumbnail_url`을 반환한다.
- WHEN: `completed` 결과를 표시한다.
- THEN: UI는 원격 썸네일을 원본 Pin 링크로만 표시하고 이미지·썸네일 URL·Pin 메타데이터를 저장하거나 재게시하지 않는다.
