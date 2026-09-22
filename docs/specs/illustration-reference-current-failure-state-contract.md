# 일러스트 레퍼런스 Agent 현행 실패 상태 계약

## Why

- **사용자**: 체형·포즈·시점·원근·구도 용어가 낯선 캐주얼 캐릭터 일러스트 초보자.
- **상황**: 사용자는 자연어로 원하는 레퍼런스를 설명하고, Agent는 팀이 검수한 TERM_CARD에서만 전문 용어와 Pinterest 탐색 계획을 만든다.
- **문제**: 단서 부족, MVP 범위 밖 요청, 카드 검증 실패, 검색 장애를 같은 오류로 처리하면 사용자는 더 설명해야 하는지, 일부 결과를 사용할 수 있는지, 재시도해야 하는지 알 수 없다.
- **측정 지표**: 30건 품질 평가에서 기대 상태·사유 코드·링크 노출 규칙 일치율 100%, 100건 계약 평가에서 허용 상태값·필수 필드 통과율 100%를 목표로 한다. 실제 측정값은 구현 후 `EVAL_REPORT.md`에 기록한다.

## Goal

- Getty API·SPARQL 호출·Getty 데이터 조회·임시 LLM 용어 폴백 없이, 팀이 관리하는 자체 TERM_CARD DB에 맞는 사용자 상태를 고정한다.
- 정보 부족, 범위 밖, 안전 거부, 부분 결과, 서비스 장애를 서로 다른 화면 행동으로 연결한다.
- LLM은 의미 해석 JSON만 만들고, 최종 상태·사유 코드·카드 검증·Pinterest 검색 계획은 서버가 결정하도록 분리한다.

공개 Agent endpoint는 `POST /api/agent`이며, 요청 하나에 대한 최종 `AgentResponse`를 동기적으로 반환한다. 요청 필드는 `frontend-api-contract.md`가, 이 문서는 그 API가 공유해야 할 **응답 상태·결과 구조·상태 결정 규칙**을 정의한다. 비동기 job과 `/api/jobs` polling은 현재 MVP 범위가 아니다.

## What

### 1. 공통 응답 계약

구현 시 `AgentResponse`는 아래 필드를 Pydantic으로 검증한다. `request_id`는 서버가 생성하며 사용자 식별자나 입력 원문을 넣지 않는다.

```json
{
  "request_id": "opaque-request-id",
  "status": "success | needs_clarification | out_of_scope | unsafe_input | partial_result | service_unavailable",
  "reason_codes": ["ZERO_OR_MORE_REASON_CODES"],
  "result": "ReferencePlan | null",
  "clarifying_question": null,
  "user_message": "사용자에게 보여 줄 짧은 안내",
  "next_action": "none | reply | human_review | manual_retry",
  "retryable": false,
  "retry_after_ms": null
}
```

- `success`, `partial_result`는 아래 `ReferencePlan`을 `result`에 반드시 넣는다.
- `needs_clarification`, `out_of_scope`, `unsafe_input`, `service_unavailable`는 `result=null`이다.
- `needs_clarification`만 `clarifying_question`을 반드시 하나 가진다. 질문은 한 번에 하나의 축 또는 충돌만 확인한다.
- `reason_codes`는 아래 허용 enum만 사용한다. 외부 서비스 원문 오류, 사용자 원문, 비밀값은 넣지 않는다.

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
          "thumbnail_url": "https://provider-returned-thumbnail/...",
          "status": "available | thumbnail_unavailable | deleted"
        }
      ]
    }
  ],
  "unresolved_roles": ["body | pose | view | perspective | layout"]
}
```

- `terms`는 역할 순서 `body → pose → view → perspective → layout`를 지키며, 역할당 최대 하나의 검증된 활성 카드만 가진다.
- `pins`는 역할당 최대 8개다. `pin_url`은 원본 Pin으로 이동하는 링크이고, `thumbnail_url`은 검색 provider가 반환한 원격 표시 URL이다.
- 구현 시 `role`과 `status`는 각각 허용 enum으로, `thumbnail_url`은 검증된 URL 또는 `null`로 Pydantic 검증한다.
- UI는 `thumbnail_url`이 있을 때만 원격 썸네일을 표시하고 원본 `pin_url`을 클릭 대상으로 사용한다. 이미지 바이트·썸네일 URL·Pin 메타데이터를 DB나 세션에 저장하거나 재게시하지 않는다.
- `thumbnail_url=null` 또는 `status=thumbnail_unavailable`이면 원본 Pin 링크만 표시한다. `deleted` Pin은 썸네일과 링크를 표시하지 않는다.

### 2. 사용자 상태 표

| 상태 | HTTP | 대표 사유 코드 | `result` | 화면 행동 | 다음 행동 |
| --- | ---: | --- | --- | --- | --- |
| `success` | 200 | 없음 | 필수 | 선택된 역할의 팀 검수 용어·설명·확인 지점과 역할별 검색 결과를 표시 | `none` |
| `needs_clarification` | 200 | `ABSTRACT_INTENT_ONLY`, `INSUFFICIENT_VISUAL_EVIDENCE`, `CONFLICTING_CONSTRAINTS`, `TEAM_TERM_CARD_UNAVAILABLE` | `null` | 용어·검색 링크를 추측하지 않고 질문 하나만 표시 | `reply` 또는 `human_review` |
| `out_of_scope` | 200 | `IMAGE_GENERATION_REQUEST`, `IMAGE_ANALYSIS_REQUEST`, `STYLE_REPLICATION_REQUEST`, `PIN_COLLECTION_REQUEST`, `UNSUPPORTED_SUBJECT` | `null` | 텍스트 기반 체형·포즈·시점·원근·구도 해석 범위만 안내 | `reply` |
| `unsafe_input` | 200 | `PROMPT_INJECTION_ATTEMPT`, `SECRET_EXTRACTION_ATTEMPT`, `HARMFUL_OR_ILLICIT_REQUEST` | `null` | 입력 원문을 되풀이하지 않고 안전한 사용 범위를 안내 | `none` |
| `partial_result` | 200 | `PIN_RESULTS_EMPTY`, `PIN_DELETED`, `PIN_THUMBNAIL_UNAVAILABLE`, `PIN_SEARCH_UNAVAILABLE`, `SEARCH_URL_BUILD_FAILED`, `TEAM_TERM_CARD_UNAVAILABLE` | 필수 | 사용 가능한 카드·썸네일·원본 링크를 표시하고, 빠진 역할·Pin·썸네일과 원인을 함께 표시 | `reply`, `human_review`, 또는 `manual_retry` |
| `service_unavailable` | 503 | `TERM_CARD_STORE_UNAVAILABLE`, `LLM_RESPONSE_UNAVAILABLE`, `LLM_SCHEMA_INVALID`, `APP_DEADLINE_EXCEEDED` | `null` | 결과·검색 링크를 만들지 않고 재시도 안내를 표시 | `manual_retry` |

요청 본문이 비었거나 `request_text`가 1~500자 제약을 위반하면 HTTP `422`를 반환한다. 이는 사용자 의미 상태가 아니므로 `AgentResponse.status`를 만들지 않으며 LLM·검색 도구를 호출하지 않는다.

`AgentResponse`는 서버가 HTTP 응답을 끝까지 쓸 수 있을 때만 반환한다. Cloud Run 인스턴스 종료, 게이트웨이 timeout, 브라우저 연결 단절처럼 응답 자체가 도착하지 않을 수 있는 전송 계층 실패는 이 enum이나 `reason_codes`로 표현하지 않는다. 클라이언트는 JSON이 아닌 5xx·네트워크 오류를 별도의 전송 실패 화면으로 표시하고 새 `POST /api/agent` 요청을 허용한다. 서버·플랫폼 관측에는 가능한 경우 `request_id`와 종료 원인을 기록하지만, 사용자 화면에 존재하지 않는 `AgentResponse`를 지어내지 않는다.

### 3. 사유 코드와 사용 조건

| 분류 | 코드 | 사용 조건 |
| --- | --- | --- |
| 해석 | `ABSTRACT_INTENT_ONLY` | “귀여운 포즈”처럼 탐색 축을 특정하지 않은 추상 표현만 있다. |
| 해석 | `INSUFFICIENT_VISUAL_EVIDENCE` | 체형·포즈·시점·원근·구도 중 사용자가 요구한 축을 카드로 고를 단서가 부족하다. |
| 해석 | `CONFLICTING_CONSTRAINTS` | 같은 축에 양립할 수 없는 조건이 함께 있어 우선순위를 확인해야 한다. |
| 카드 | `TEAM_TERM_CARD_UNAVAILABLE` | 활성 카드 사전에 요청 역할·용어가 없거나 resolver 검증을 통과한 카드가 없다. |
| 범위 | `IMAGE_GENERATION_REQUEST` | 그림·이미지 생성 또는 편집 요청이다. |
| 범위 | `IMAGE_ANALYSIS_REQUEST` | 업로드 이미지의 분석·분류 요청이다. |
| 범위 | `STYLE_REPLICATION_REQUEST` | 특정 작가의 화풍 복제 요청이다. |
| 범위 | `PIN_COLLECTION_REQUEST` | Pin·이미지의 대량 수집, 다운로드, 저장, 재게시 요청이다. |
| 범위 | `UNSUPPORTED_SUBJECT` | 캐릭터 레퍼런스의 다섯 역할 해석과 무관한 요청이다. |
| 안전 | `PROMPT_INJECTION_ATTEMPT` | 내부 지시를 무시·변경하게 하려는 입력이다. |
| 안전 | `SECRET_EXTRACTION_ATTEMPT` | 시스템 프롬프트, API 키, 내부 설정을 요구한다. |
| 안전 | `HARMFUL_OR_ILLICIT_REQUEST` | 유해하거나 불법적인 실행을 요구한다. |
| 검색 결과 | `PIN_RESULTS_EMPTY` | 검색은 성공했지만 해당 역할의 표시 가능한 Pin URL이 0개다. |
| 검색 결과 | `PIN_DELETED` | 검색 provider가 원본 Pin이 삭제됐거나 더 이상 열 수 없다고 반환했다. |
| 검색 결과 | `PIN_THUMBNAIL_UNAVAILABLE` | 원본 Pin 링크는 있으나 검색 provider가 표시 가능한 원격 썸네일 URL을 주지 못했다. |
| 검색 도구 | `PIN_SEARCH_UNAVAILABLE` | 검색 provider가 timeout·5xx·인증 오류 등으로 결과를 주지 못했다. |
| URL | `SEARCH_URL_BUILD_FAILED` | 검증된 카드가 있지만 URL builder가 안전한 검색 링크를 만들지 못했다. |
| 서비스 | `TERM_CARD_STORE_UNAVAILABLE` | 자체 TERM_CARD DB에 연결할 수 없거나, DB의 활성 카드 검증에 실패했다. 시드 JSON 오류는 배포·시드 적재 단계에서 이 상태로 기록한다. |
| 서비스 | `LLM_RESPONSE_UNAVAILABLE` | LLM timeout·5xx·429·미완료 응답으로 해석 JSON을 받지 못했다. |
| 서비스 | `LLM_SCHEMA_INVALID` | LLM 응답이 구조화 출력 또는 Pydantic 검증을 통과하지 못했다. |
| 요청 | `APP_DEADLINE_EXCEEDED` | 앱이 관리하는 처리 제한 시간을 응답 작성 전에 감지해 안전하게 중단했다. Cloud Run·게이트웨이 timeout은 이 코드로 단정하지 않는다. |

### 4. LLM 내부 출력 계약

LLM은 최종 `status`, `reason_codes`, `next_action`, Pin URL, 검색 도구 성공 여부를 만들지 않는다. 활성 TERM_CARD ID 후보와 의미 상태만 출력하고, 서버가 독립적으로 검증한다.

```json
{
  "interpretation_state": "resolved | needs_clarification | out_of_scope | unsafe_input",
  "selections": [
    {
      "role": "body | pose | view | perspective | layout",
      "term_id": "active_term_id_only",
      "evidence": ["사용자 문장의 짧은 근거"],
      "confidence": "high | medium | low"
    }
  ],
  "unresolved_constraints": [
    {
      "role": "body | pose | view | perspective | layout",
      "reason_code": "ABSTRACT_INTENT_ONLY | INSUFFICIENT_VISUAL_EVIDENCE | CONFLICTING_CONSTRAINTS"
    }
  ],
  "clarifying_question": null,
  "out_of_scope_code": null,
  "safety_reason_code": null
}
```

- `resolved`는 실제로 언급된 역할의 활성 `term_id`만 역할당 최대 하나 선택한다. 미언급 역할을 기본값으로 채우지 않는다.
- `needs_clarification`은 빈 `selections`, 하나의 미해결 조건, 하나의 질문을 가진다.
- `out_of_scope`, `unsafe_input`은 빈 `selections`를 가진다. 안전 입력은 사전 검사로 차단하는 것을 원칙으로 한다.
- resolver는 활성 여부, 역할 일치, `confidence_gate`, `requires_all_of`, `requires_any_of`를 다시 확인한다. 통과하지 못한 term ID·자유 검색어·URL은 폐기한다.

## How

### 1. 상태 결정 순서

1. 요청 형식과 길이를 검증한다. 실패하면 HTTP 422로 종료한다.
2. 프롬프트 주입·비밀값 추출·유해 요청을 사전 검사한다. 해당하면 `unsafe_input`으로 종료한다.
3. 이미지 생성·분석, 화풍 복제, Pin 수집·저장 등 MVP 비범위를 판별한다. 해당하면 `out_of_scope`로 종료한다.
4. LLM 구조화 출력과 활성 카드 사전을 검증한다. 단서가 부족하거나 상충하면 `needs_clarification`으로 질문 하나를 만든다.
5. 검증된 카드가 하나도 없고 팀 카드에 없는 표현이라면 `needs_clarification`과 `TEAM_TERM_CARD_UNAVAILABLE`을 반환한다. 질문으로 해결할 수 없으면 `next_action=human_review`를 사용한다.
6. 검증된 카드가 있으면 자체 TERM_CARD DB의 설명·확인 지점·검색 조각만으로 검색 계획을 만든다. 자유 검색어·Getty 데이터·외부 API·외부 어휘 폴백은 만들지 않는다.
7. 일부 역할의 URL 생성·Pin 검색·원격 썸네일 URL 확보만 실패했지만 검증된 카드 결과가 하나 이상 있으면 `partial_result`를 반환한다.
8. 자체 TERM_CARD DB 또는 LLM 해석 자체를 사용할 수 없거나 작업이 중단됐으면 `service_unavailable`으로 종료한다. 외부 API·Getty 데이터로 보완하지 않는다.

### 2. 재시도 정책

자동 재시도는 하지 않는다. 모든 실패는 `request_id`, attempt=`1`, error_type, model, prompt_version, latency를 기록하고, 사용자가 누른 재시도만 새 작업으로 처리한다.

| 실패 유형 | 최초 뒤 추가 시도 | 재시도 전략 | 백오프 | 사용자 응답 |
| --- | ---: | --- | --- | --- |
| LLM 구조화 출력/Pydantic 위반 | 0회 | 현재 출력 폐기 | 없음 | `service_unavailable`, `LLM_SCHEMA_INVALID`, 수동 재시도 |
| LLM timeout | 0회 | 현재 작업 종료 | 없음 | `service_unavailable`, `LLM_RESPONSE_UNAVAILABLE`, 수동 재시도 |
| LLM 5xx | 0회 | 현재 작업 종료 | 없음 | `service_unavailable`, `LLM_RESPONSE_UNAVAILABLE`, 수동 재시도 |
| LLM 429 | 0회 | 현재 작업 종료 | 없음 | `service_unavailable`, `LLM_RESPONSE_UNAVAILABLE`, 수동 재시도 |
| 검색 provider 오류 | 0회 | 카드 결과를 보존 | 없음 | 검증된 카드가 있으면 `partial_result`, 없으면 `service_unavailable` |

### 3. UI와 요청 상태 연결

- UI는 `POST /api/agent`가 끝날 때까지 로딩 상태만 표시하고 결과·진행률을 지어내지 않는다. 응답을 받은 뒤에만 역할별 카드, 원격 썸네일, 원본 Pin 링크를 표시한다.
- timeout·인스턴스 종료·DB·LLM 장애는 이 계약의 `service_unavailable`으로 변환한다. 자동 재시도는 하지 않는다.
- `partial_result`는 적어도 하나의 검증된 카드 결과가 있을 때만 사용한다. 카드 결과가 전혀 없으면 `service_unavailable` 또는 `needs_clarification`으로 처리한다.

## AC

**AC-01 · 단서 부족**

- GIVEN: 사용자가 “귀여운 포즈 찾아줘”처럼 탐색 축을 정하지 않은 입력을 보낸다.
- WHEN: 의미 해석과 resolver 검증을 수행한다.
- THEN: HTTP 200, `status=needs_clarification`, `reason_codes=[ABSTRACT_INTENT_ONLY]`, 카드·검색 링크 없이 질문 하나를 반환한다.

**AC-02 · 자체 카드 밖 요청**

- GIVEN: 사용자가 현재 활성 카드로 해석할 수 없는 체형·포즈 조합을 요청한다.
- WHEN: 활성 카드 사전을 검증한다.
- THEN: 자유 term ID·검색어를 만들지 않고 `TEAM_TERM_CARD_UNAVAILABLE`과 추가 질문 또는 `next_action=human_review`를 반환한다.

**AC-03 · 부분 검색 실패**

- GIVEN: 하나 이상의 활성 카드가 검증됐고, 한 역할의 검색 provider가 실패한다.
- WHEN: 결과를 조립한다.
- THEN: HTTP 200, `status=partial_result`, `PIN_SEARCH_UNAVAILABLE`과 남은 카드 결과를 함께 반환한다.

**AC-04 · 자체 DB 저장소 장애**

- GIVEN: 자체 TERM_CARD DB에 연결할 수 없거나 활성 카드 검증에 실패한다.
- WHEN: Card repository를 시작한다.
- THEN: HTTP 503, `status=service_unavailable`, `reason_codes=[TERM_CARD_STORE_UNAVAILABLE]`, `result=null`, `retryable=true`을 반환한다. 시드 JSON의 카드 수·중복 ID 오류는 런타임 요청 전에 적재를 중단하고 같은 운영자 장애로 기록한다.

**AC-05 · 안전·범위 밖 요청**

- GIVEN: 이미지 생성·화풍 복제·Pin 대량 수집 또는 내부 지시·비밀값 추출 요청이 들어온다.
- WHEN: 사전 검사를 수행한다.
- THEN: LLM·검색 도구를 호출하지 않고 각각 `out_of_scope` 또는 `unsafe_input`을 반환한다.

**AC-06 · LLM 경계**

- GIVEN: LLM이 구조화 출력을 만든다.
- WHEN: 최종 API 응답을 조립한다.
- THEN: LLM은 활성 `term_id` 후보와 의미 상태만 제공하고, 상태·사유 코드·URL·검색 성공 여부는 서버가 결정한다.

**AC-07 · 썸네일 결과 계약**

- GIVEN: 검색 provider가 검증된 역할에 `pin_url`과 `thumbnail_url`을 반환한다.
- WHEN: 서버가 `ReferencePlan`을 조립한다.
- THEN: 역할별 최대 8개의 `{pin_url, thumbnail_url, status}`만 응답에 넣고, UI는 원격 썸네일을 원본 Pin 링크로 표시한다. 이미지 바이트·썸네일 URL·Pin 메타데이터는 영속 저장하지 않는다.
